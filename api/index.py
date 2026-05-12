import os
import sys
import logging
import json
import asyncio
import time
import hashlib
import re
from datetime import datetime, timedelta
import httpx
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from telegram.request import HTTPXRequest

# Ensure core and scripts can be imported correctly
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

load_dotenv()
os.environ['LANGSMITH_TRACING'] = 'false'

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("lorin_bot")

# --- Global Config ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "7770158141").split(",") if i.strip()]
CRON_SECRET = os.getenv("CRON_SECRET")

from flask_cors import CORS

# Initialize Flask
app = Flask(__name__)
CORS(app, resources={r"/api/*": {
    "origins": ["https://frontend-lorinai.vercel.app", "http://localhost:3000"],
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}})

# --- Global State ---
_engine = None
_db_pool = None
_telegram_app = None

async def get_db_pool():
    global _db_pool
    if _db_pool is None:
        db_url = os.getenv("DATABASE_URL")
        if not db_url or "127.0.0.1" in db_url or "localhost" in db_url:
            return None
        import asyncpg
        # Supabase/PgBouncer requires statement_cache_size=0
        _db_pool = await asyncpg.create_pool(db_url, statement_cache_size=0)
    return _db_pool

async def get_engine():
    global _engine
    if _engine is None:
        from core.engine import RAGEngine
        _engine = RAGEngine()
    return _engine

async def get_telegram_app():
    global _telegram_app
    if _telegram_app is None:
        request_obj = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
        _telegram_app = ApplicationBuilder().token(TOKEN).request(request_obj).build()
        _telegram_app.add_handler(CommandHandler("start", start))
        _telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        await _telegram_app.initialize()
    return _telegram_app

async def log_to_supabase(user_id, user_name, query, response, tel):
    try:
        pool = await get_db_pool()
        if not pool: return
        intent = tel.get("intent", "FACT")
        sources = json.dumps(tel.get("sources", []))
        latency = tel.get("latency_ms", 0)
        tokens = tel.get("tokens", 0)
        cost = (tokens / 1000) * 0.0001
        
        async with pool.acquire() as conn:
            # We explicitly set timestamp to ensure the DB records it
            await conn.execute(
                """INSERT INTO interactions 
                   (timestamp, user_id, user_name, query, intent, response, sources, latency_ms, tokens_used, cost_usd) 
                   VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                str(user_id), user_name, query, intent, response, sources, latency, tokens, cost
            )
    except Exception as e:
        logger.error(f"DB Logging Error: {e}")
        # DIAGNOSTIC: Notify Telegram Admin of Logging Failure
        try:
            admin_id = str(ADMIN_IDS[0])
            error_msg = f"⚠️ *DB Logging Failed*\nError: `{str(e)}`"
            import httpx
            with httpx.Client() as t_client:
                t_client.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": admin_id, "text": error_msg, "parse_mode": "Markdown"})
        except:
            pass

# --- Security Config ---
ABUSIVE_WORDS = ["badword1", "badword2"]

def is_gibberish(text):
    if len(text) < 4: return False
    words = text.split()
    for w in words:
        if re.search(r'\d', w): continue
        if len(w) > 12: # Increased from 8 to 12
            vowels = len(re.findall(r'[aeiouAEIOU]', w))
            if vowels / len(w) < 0.1: return True # Reduced from 0.15 to 0.1
        if len(w) > 30: return True # Increased from 20 to 30
    return False

async def check_security(user_id, text, engine, is_thinking=False):
    if not engine.redis: return True, None, 0
    
    now_ts = int(time.time())
    quota_now = datetime.now() - timedelta(hours=4, minutes=30)
    quota_day_str = quota_now.strftime('%Y-%m-%d')
    
    block_key = f"user_{user_id}_blocked_until"
    blocked_until = await engine.redis.get(block_key)
    if blocked_until and int(blocked_until) > now_ts:
        return False, "BLOCKED", (int(blocked_until) - now_ts) // 60 + 1

    is_abusive = any(re.search(rf"\b{word}\b", text, re.I) for word in ABUSIVE_WORDS)
    is_gib = is_gibberish(text)
    
    if is_abusive or is_gib:
        strike_key = f"user_{user_id}_strikes"
        strikes = await engine.redis.incr(strike_key)
        duration = 0
        if strikes >= 10: duration = 7*24
        elif strikes >= 5: duration = 24
        elif strikes >= 3: duration = 6
        if duration > 0:
            await engine.redis.set(block_key, now_ts + (duration * 3600))
            return False, "BANNED", duration
        return False, "WARNING", strikes

    if user_id in ADMIN_IDS: return True, None, 0

    day_key = f"user_{user_id}_daily_count_{quota_day_str}"
    daily_count = await engine.redis.get(day_key)
    if daily_count and int(daily_count) >= 25: return False, "DAILY_LIMIT", 25

    if is_thinking:
        think_key = f"user_{user_id}_thinking_count_{quota_day_str}"
        think_count = await engine.redis.get(think_key)
        if think_count and int(think_count) >= 5: return False, "DEEP_THINK_LIMIT", 5

    min_key = f"user_{user_id}_min_count_{now_ts // 60}"
    min_count = await engine.redis.get(min_key)
    if min_count and int(min_count) >= 5: return False, "MINUTE_LIMIT", 5

    last_msg_key = f"user_{user_id}_last_msg"
    dup_count_key = f"user_{user_id}_dup_count"
    last_data = await engine.redis.get(last_msg_key)
    
    is_spam = False
    if last_data:
        last_data = json.loads(last_data)
        if now_ts - last_data['time'] < 2: is_spam = True
        elif text == last_data['text']:
            dups = await engine.redis.incr(dup_count_key)
            if dups >= 3: is_spam = True
        else: await engine.redis.set(dup_count_key, 0)

    if is_spam:
        strike_key = f"user_{user_id}_strikes"
        strikes = await engine.redis.incr(strike_key)
        duration = 0
        if strikes >= 10: duration = 7*24
        elif strikes >= 5: duration = 24
        elif strikes >= 3: duration = 6
        if duration > 0:
            await engine.redis.set(block_key, now_ts + (duration * 3600))
            return False, "BANNED", duration
        return False, "WARNING", strikes

    await engine.redis.incr(day_key); await engine.redis.expire(day_key, 90000)
    if is_thinking:
        think_key = f"user_{user_id}_thinking_count_{quota_day_str}"
        await engine.redis.incr(think_key); await engine.redis.expire(think_key, 90000)
    
    await engine.redis.incr(min_key); await engine.redis.expire(min_key, 60)
    await engine.redis.set(last_msg_key, json.dumps({"time": now_ts, "text": text}), ex=300)
    return True, None, 0

async def handle_telegram_direct(payload):
    """Direct, high-speed Telegram handler with command support and state management."""
    try:
        if "message" not in payload: return
        msg = payload["message"]
        user_id = msg["from"]["id"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        user_name = msg["from"].get("first_name", "User")

        if not text: return

        engine = await get_engine()

        # --- 1. COMMAND HANDLERS ---
        if text.startswith("/"):
            cmd = text.lower().split()[0]
            if cmd == "/help":
                resp = "🔍 *LORIN Help Guide*\n\n• *Pronouns:* I remember context! You can say 'tell me about him' or 'give more info on it'.\n• *Admissions:* Use college code *1301*.\n• *Bus Routes:* Ask for 'AR8 route' or 'Tambaram bus'.\n• *Faculty:* Ask for HODs or specific professors."
            else:
                return # Ignore other commands

            async with httpx.AsyncClient() as client:
                await client.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                                 json={"chat_id": chat_id, "text": resp, "parse_mode": "Markdown"})
            return

        # --- 2. FAST-PATH Greeting Detection ---
        greetings = ["hi", "hello", "hey", "hey lorin", "greetings", "good morning", "good afternoon"]
        is_greeting = text.lower().strip() in greetings or (len(text.split()) < 3 and any(g in text.lower() for g in greetings))
        
        # --- 3. Security & Rate Limiting ---
        is_allowed, reason, val = await check_security(user_id, text, engine, is_thinking=is_thinking)
        if not is_allowed:
            async with httpx.AsyncClient() as client:
                await client.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                                 json={"chat_id": chat_id, "text": f"⏳ *Security Alert*: {reason} ({val}).", "parse_mode": "Markdown"})
            return

        # --- 4. User Preferences (Defaults for Telegram) ---
        is_thinking = False
        user_level = "student"

        # --- 5. Status Feedback ---
        async with httpx.AsyncClient() as client:
            await client.post(f"https://api.telegram.org/bot{TOKEN}/sendChatAction", 
                             json={"chat_id": chat_id, "action": "typing"})
            
            ana_res = await client.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                                       json={"chat_id": chat_id, "text": "🔍 *Analyzing...*", "parse_mode": "Markdown"})
            ana_msg_id = ana_res.json().get("result", {}).get("message_id")

        # --- 6. Process Query ---
        redis_key = f"user_{user_id}_history"
        history = []
        if engine.redis:
            hist_raw = await engine.redis.get(redis_key)
            history = json.loads(hist_raw) if hist_raw else []
        
        history_str = "\n".join([f"User: {h['q']}\nBot: {h['a']}" for h in history])

        full_response = ""
        telemetry = {}
        
        try:
            async for chunk in engine.query_stream(text, history=history_str, thinking=is_thinking, user_level=user_level):
                if isinstance(chunk, dict) and chunk.get("type") == "telemetry":
                    telemetry = chunk
                    continue
                full_response += chunk
        except Exception as e:
            full_response = "I encountered an error while processing your request. Please try again."
            logger.error(f"ENGINE ERROR: {e}")

        # --- 7. Final Response Delivery ---
        async with httpx.AsyncClient() as client:
            if ana_msg_id:
                # Add sources footer if available
                final_text = full_response
                if telemetry.get("sources"):
                    src_str = ", ".join(telemetry["sources"][:2])
                    final_text += f"\n\n_Sources: {src_str}_"

                res = await client.post(f"https://api.telegram.org/bot{TOKEN}/editMessageText", 
                                       json={"chat_id": chat_id, "message_id": ana_msg_id, "text": final_text, "parse_mode": "Markdown"})
                if res.status_code != 200:
                    # Fallback to plain text if Markdown fails
                    await client.post(f"https://api.telegram.org/bot{TOKEN}/editMessageText", 
                                     json={"chat_id": chat_id, "message_id": ana_msg_id, "text": full_response})
            else:
                await client.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                                 json={"chat_id": chat_id, "text": full_response, "parse_mode": "Markdown"})

        # --- 8. History & Logging ---
        try:
            await log_to_supabase(user_id, user_name, text, full_response, telemetry)
            if engine.redis:
                history.append({"q": text, "a": full_response})
                await engine.redis.set(redis_key, json.dumps(history[-5:]), ex=86400)
        except: pass

    except Exception as e:
        logger.error(f"TELEGRAM DIRECT FAIL: {e}")
        # Final safety net message
        try:
            async with httpx.AsyncClient() as client:
                await client.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                                 json={"chat_id": chat_id, "text": "⚠️ System temporary unavailable. Please check back in a moment."})
        except: pass


@app.route('/api/history', methods=['GET'])
async def get_chat_history():
    try:
        user_id = request.args.get("user_id")
        if not user_id: return {"history": []}, 200
        
        pool = await get_db_pool()
        if not pool: return {"history": []}, 200
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT query as q, response as a, timestamp 
                   FROM interactions 
                   WHERE user_id = $1 
                   ORDER BY timestamp DESC LIMIT 10""",
                str(user_id)
            )
            
            # Reverse to get chronological order [old -> new]
            history = [{"role": "user", "content": r['q']} for r in reversed(rows)]
            # We add responses as separate messages
            interleaved = []
            for r in reversed(rows):
                interleaved.insert(0, {"id": f"bot_{r['timestamp'].timestamp()}", "role": "bot", "content": r['a']})
                interleaved.insert(0, {"id": f"user_{r['timestamp'].timestamp()}", "role": "user", "content": r['q']})
            
            return {"history": interleaved}, 200
    except Exception as e:
        logger.error(f"History Fetch Error: {e}")
        return {"history": []}, 200

@app.route('/')
def home(): return "<h1>🚀 Lorin Bot Active</h1>", 200

@app.route('/api/chat', methods=['POST'])
async def chat_api():
    try:
        data = request.get_json(force=True)
        user_query = data.get("message")
        user_id = data.get("user_id", "web_default")
        thinking = data.get("thinking", False)
        deep_search = data.get("deep_search", False)
        user_level = data.get("user_level", "student")
        
        if not user_query:
            return {"response": "Empty message"}, 400
        
        engine = await get_engine()
        
        # 1. SECURITY SHIELD (Strikes & Blocking)
        is_allowed, reason, val = await check_security(user_id, user_query, engine, is_thinking=(thinking or deep_search))
        if not is_allowed:
            msg = f"⚠️ Security Alert: {reason}. Status: {val} strikes/hours."
            if reason == "DEEP_THINK_LIMIT":
                msg = f"🚀 Deep Thinking Limit Reached: You have used your {val} daily messages for high-precision mode. Normal mode is still available!"
            elif reason == "DAILY_LIMIT":
                msg = f"⏳ Daily Limit Reached: You have used your {val} messages for today. Please come back tomorrow!"
            elif reason == "MINUTE_LIMIT":
                msg = f"⏱️ Rate Limit: Please wait a minute before sending another message."
                
            return {
                "response": msg,
                "blocked": True,
                "reason": reason,
                "value": val
            }, 403
            
        # Consistent History Management (Synced with Telegram)
        # We now allow the frontend to pass history directly for high reliability
        passed_history = data.get("history")
        history_str = ""
        
        if passed_history and isinstance(passed_history, list):
            # Convert list of {role, content} to the string format the engine expects
            history_str = "\n".join([
                f"{'User' if h['role'] == 'user' else 'Bot'}: {h['content']}" 
                for h in passed_history[-5:] # Last 5 turns
            ])
        elif engine.redis:
            redis_key = f"user_{user_id}_history"
            hist_raw = await engine.redis.get(redis_key)
            history = json.loads(hist_raw) if hist_raw else []
            history_str = "\n".join([f"User: {h['q']}\nBot: {h['a']}" for h in history])

        
        full_response = ""
        telemetry_data = {}
        # The engine.query_stream uses history to maintain context
        async for chunk in engine.query_stream(user_query, history=history_str, user_level=user_level, thinking=thinking, deep_search=deep_search):
            if isinstance(chunk, str):
                full_response += chunk
            elif isinstance(chunk, dict) and chunk.get("type") == "telemetry":
                telemetry_data = chunk
        
        # Save to Redis history (limit to 5 turns to stay fast)
        if engine.redis:
            redis_key = f"user_{user_id}_history"
            hist_raw = await engine.redis.get(redis_key)
            current_history = json.loads(hist_raw) if hist_raw else []
            current_history.append({"q": user_query, "a": full_response})
            await engine.redis.set(redis_key, json.dumps(current_history[-5:]), ex=86400)
        
        # Log to interaction DB (Supabase)
        try:
            await log_to_supabase(user_id, "Web User", user_query, full_response, telemetry_data)
        except: pass
        
        # Sanitize telemetry: flatten tokens to int (AI gateway may return {input, output, total})
        tokens_raw = telemetry_data.get("tokens", 0)
        if isinstance(tokens_raw, dict):
            telemetry_data["tokens"] = int(tokens_raw.get("total", 0))
        else:
            telemetry_data["tokens"] = int(tokens_raw) if tokens_raw is not None else 0
        
        return {
            "response": full_response,
            "telemetry": telemetry_data
        }, 200
    except Exception as e:
        logger.error(f"Chat API Error: {e}")
        return {"response": f"Error: {str(e)}"}, 500

@app.route('/api/webhook', methods=['POST'])
async def webhook():
    try:
        payload = request.get_json(force=True)
        await handle_telegram_direct(payload)
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook Route Error: {e}")
        return "OK", 200

@app.route('/api/sunday-report')
async def trigger_sunday_report():
    auth_header = request.headers.get("Authorization")
    vercel_cron = request.headers.get("x-vercel-cron")
    cron_secret = os.getenv("CRON_SECRET")
    
    # Allow if either the Bearer token matches OR it's a verified Vercel Cron internal request
    if not ((auth_header == f"Bearer {cron_secret}") or (vercel_cron == "1")):
        return {"error": "Unauthorized"}, 401
        
    try:
        from scripts.sunday_intelligence import SundayIntelligence
        audit = SundayIntelligence()
        asyncio.create_task(audit.run())
        return {"status": "SUCCESS", "message": "Sunday Intelligence Audit Dispatched"}, 200
    except Exception as e:
        logger.error(f"Cron Error: {e}")
        return {"status": "ERROR", "message": str(e)}, 500

app_handler = app
