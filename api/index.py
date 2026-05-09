# Forced rebuild for Telegram Bot
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
CORS(app, resources={r"/api/*": {"origins": "*"}})

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
        if len(w) > 8:
            vowels = len(re.findall(r'[aeiouAEIOU]', w))
            if vowels / len(w) < 0.15: return True
        if len(w) > 20: return True
    return False

async def check_security(user_id, text, engine):
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
    if daily_count and int(daily_count) >= 30: return False, "DAILY_LIMIT", 30

    min_key = f"user_{user_id}_min_count_{now_ts // 60}"
    min_count = await engine.redis.get(min_key)
    if min_count and int(min_count) >= 6: return False, "MINUTE_LIMIT", 6

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
    await engine.redis.incr(min_key); await engine.redis.expire(min_key, 60)
    await engine.redis.set(last_msg_key, json.dumps({"time": now_ts, "text": text}), ex=300)
    return True, None, 0

async def handle_telegram_direct(payload):
    """Direct, high-speed Telegram handler for Serverless environments."""
    try:
        if "message" not in payload: return
        msg = payload["message"]
        user_id = msg["from"]["id"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        user_name = msg["from"].get("first_name", "User")

        if not text: return

        # 1. FAST-PATH Greeting Detection
        greetings = ["hi", "hello", "hey", "hey lorin", "greetings", "good morning", "good afternoon"]
        is_greeting = text.lower().strip() in greetings or (len(text.split()) < 3 and any(g in text.lower() for g in greetings))
        
        engine = await get_engine()
        
        # 2. Security & Rate Limiting
        is_allowed, reason, val = await check_security(user_id, text, engine)
        if not is_allowed:
            async with httpx.AsyncClient() as client:
                await client.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                                 json={"chat_id": chat_id, "text": f"⏳ {reason}: {val}"})
            return

        # 3. Direct Send "Typing"
        async with httpx.AsyncClient() as client:
            await client.post(f"https://api.telegram.org/bot{TOKEN}/sendChatAction", 
                             json={"chat_id": chat_id, "action": "typing"})

        # 4. Process Query
        redis_key = f"user_{user_id}_history"
        hist_raw = await engine.redis.get(redis_key)
        history = json.loads(hist_raw) if hist_raw else []
        history_str = "\n".join([f"User: {h['q']}\nBot: {h['a']}" for h in history])

        full_response = ""
        telemetry = {}
        
        async for chunk in engine.query_stream(text, history=history_str):
            if isinstance(chunk, dict) and chunk.get("type") == "telemetry":
                telemetry = chunk
                continue
            full_response += chunk

        # 5. Send Final Response
        async with httpx.AsyncClient() as client:
            # Try Markdown, fallback to plain text
            res = await client.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                                   json={"chat_id": chat_id, "text": full_response, "parse_mode": "Markdown"})
            if res.status_code != 200:
                await client.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                                 json={"chat_id": chat_id, "text": full_response})

        # 6. Post-Processing (Log to Supabase)
        try:
            await log_to_supabase(user_id, user_name, text, full_response, telemetry)
            history.append({"q": text, "a": full_response})
            await engine.redis.set(redis_key, json.dumps(history[-3:]), ex=86400)
        except: pass

    except Exception as e:
        logger.error(f"TELEGRAM DIRECT FAIL: {e}")


@app.route('/')
def home(): return "<h1>🚀 Lorin Bot Active</h1>", 200

@app.route('/api/chat', methods=['POST'])
async def chat_api():
    try:
        data = request.get_json(force=True)
        user_query = data.get("message")
        user_id = data.get("user_id", "web_default")
        thinking = data.get("thinking", False)
        
        if not user_query:
            return {"response": "Empty message"}, 400
        
        engine = await get_engine()
        
        # Consistent History Management (Synced with Telegram)
        redis_key = f"user_{user_id}_history"
        hist_raw = await engine.redis.get(redis_key)
        history = json.loads(hist_raw) if hist_raw else []
        history_str = "\n".join([f"User: {h['q']}\nBot: {h['a']}" for h in history])
        
        full_response = ""
        telemetry_data = {}
        # The engine.query_stream uses history to maintain context
        async for chunk in engine.query_stream(user_query, history=history_str):
            if isinstance(chunk, str):
                full_response += chunk
            elif isinstance(chunk, dict) and chunk.get("type") == "telemetry":
                telemetry_data = chunk
        
        # Save to Redis history (limit to 5 turns to stay fast)
        history.append({"q": user_query, "a": full_response})
        await engine.redis.set(redis_key, json.dumps(history[-5:]), ex=86400)
        
        # Log to interaction DB (Supabase)
        try:
            await log_to_supabase(user_id, "Web User", user_query, full_response, telemetry_data)
        except: pass
        
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
