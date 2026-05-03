import os
import sys
import logging
import json
import asyncio
import time
import hashlib
import re
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from telegram.request import HTTPXRequest

# Ensure core and scripts can be imported correctly
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from core.engine import RAGEngine
from scripts.sunday_intelligence import SundayIntelligence

load_dotenv()

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("lorin_bot")

# Initialize Flask
app = Flask(__name__)

# --- Global State ---
_engine = None
_db_pool = None

async def get_db_pool():
    global _db_pool
    if _db_pool is None:
        db_url = os.getenv("DATABASE_URL")
        # Strict Cloud Check: Prevent localhost attempts
        if not db_url or "127.0.0.1" in db_url or "localhost" in db_url:
            logger.warning("Supabase DATABASE_URL missing or local. Skipping cloud logging.")
            return None
        import asyncpg
        _db_pool = await asyncpg.create_pool(db_url)
    return _db_pool

async def log_to_supabase(user_id, user_name, query, response, tel):
    try:
        pool = await get_db_pool()
        intent = tel.get("intent", "FACT")
        sources = tel.get("sources", [])
        latency = tel.get("latency_ms", 0)
        tokens = tel.get("tokens", 0)
        cost = (tokens / 1000) * 0.0001 # Estimated cost for Flash 2.0
        
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO interactions 
                   (user_id, user_name, query, intent, response, sources, latency_ms, tokens_used, cost_usd) 
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                user_id, user_name, query, intent, response, sources, latency, tokens, cost
            )
    except Exception as e:
        logger.error(f"DB Logging Error: {e}")

def get_clean_env(key, default=""):
    val = os.getenv(key, default)
    if val: return val.strip().replace("\n", "").replace("\r", "")
    return default

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "7770158141").split(",") if i.strip()]

# GLOBAL PRODUCTION ENGINE
_engine = RAGEngine()

# --- Security Config ---
ABUSIVE_WORDS = ["badword1", "badword2"]

def is_gibberish(text):
    if len(text) < 4: return False
    words = text.split()
    for w in words:
        # Ignore numbers, dates, and batch ranges (e.g., 2024-2028)
        if re.search(r'\d', w): continue
        
        # Only check vowel ratio for long alphabetic words
        if len(w) > 8:
            vowels = len(re.findall(r'[aeiouAEIOU]', w))
            if vowels / len(w) < 0.15: return True
        if len(w) > 20: return True # Increased threshold for technical words
    return False

async def check_security(user_id, text, engine):
    now_ts = int(time.time())
    quota_now = datetime.now() - timedelta(hours=4, minutes=30)
    quota_day_str = quota_now.strftime('%Y-%m-%d')
    
    # 1. Check if currently blocked
    block_key = f"user_{user_id}_blocked_until"
    blocked_until = await engine.redis.get(block_key)
    if blocked_until and int(blocked_until) > now_ts:
        return False, "BLOCKED", (int(blocked_until) - now_ts) // 60 + 1

    # --- CONTENT CHECKS (Applies to EVERYONE including Admins) ---
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

    # --- ADMIN BYPASS FOR QUOTAS & SPAM ---
    if user_id in ADMIN_IDS:
        return True, None, 0

    # --- FREQUENCY CHECKS (Students Only) ---
    day_key = f"user_{user_id}_daily_count_{quota_day_str}"
    daily_count = await engine.redis.get(day_key)
    if daily_count and int(daily_count) >= 30:
        return False, "DAILY_LIMIT", 30

    min_key = f"user_{user_id}_min_count_{now_ts // 60}"
    min_count = await engine.redis.get(min_key)
    if min_count and int(min_count) >= 6:
        return False, "MINUTE_LIMIT", 6

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
        else:
            await engine.redis.set(dup_count_key, 0)

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

    # Update states for students
    await engine.redis.incr(day_key); await engine.redis.expire(day_key, 90000)
    await engine.redis.incr(min_key); await engine.redis.expire(min_key, 60)
    await engine.redis.set(last_msg_key, json.dumps({"time": now_ts, "text": text}), ex=300)
    
    return True, None, 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_status = "👑 Admin Access" if user_id in ADMIN_IDS else "🎓 Student Access"
    await update.message.reply_text(f"👋 Lorin Active.\nMode: {admin_status}", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_query = update.message.text
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name or update.effective_user.username or "Anonymous"
    global _engine
    
    is_allowed, reason, val = await check_security(user_id, user_query, _engine)
    if not is_allowed:
        msgs = {"BLOCKED": f"⏳ Wait {val} min.", "MINUTE_LIMIT": "🐢 6 msg/min limit.", "DAILY_LIMIT": "🛑 30/day limit reached.", "BANNED": f"🚫 Blocked {val}h.", "WARNING": f"⚠️ Warning {val}/10: Abuse, Spam, or Gibberish detected."}
        await update.message.reply_text(msgs.get(reason, "Access denied."))
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    thinking_msg = await update.message.reply_text("🔍 Analyzing...")
    
    try:
        # 1. SEMANTIC CACHE (DISABLED for final string to allow for Structural Variety)
        # We now rely on the RAGEngine's internal caching and 0.7 temperature for variety.
        query_hash = hashlib.sha256(user_query.lower().strip().encode()).hexdigest()

        redis_key = f"user_{user_id}_history"
        hist_raw = await _engine.redis.get(redis_key)
        history = json.loads(hist_raw) if hist_raw else []
        history_str = "\n".join([f"User: {h['q']}\nBot: {h['a']}" for h in history])
        
        # High-Precision Character Typing Effect
        full_response = ""
        displayed_text = ""
        last_update_time = time.time()
        telemetry = {}
        
        async for chunk in _engine.query_stream(user_query, history=history_str):
            if isinstance(chunk, dict) and chunk.get("type") == "telemetry":
                telemetry = chunk
                continue
                
            full_response += chunk
            
            # Warp Speed Character drip-feed logic
            while len(displayed_text) < len(full_response):
                # Add 5 characters at a time for 'Warp Speed' (approx 125 chars/sec)
                displayed_text = full_response[:len(displayed_text) + 5]
                
                # Update Telegram every ~0.25s
                if time.time() - last_update_time > 0.25:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id, 
                            message_id=thinking_msg.message_id, 
                            text=displayed_text + " ▌"
                        )
                        last_update_time = time.time()
                    except: 
                        await asyncio.sleep(0.1)
                
                # Rapid micro-sleep (0.04s)
                await asyncio.sleep(0.04)

        # Warp Drain: Instantly flush remaining text
        while len(displayed_text) < len(full_response):
            displayed_text = full_response[:len(displayed_text) + 10] 
            if time.time() - last_update_time > 0.25:
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id, 
                        message_id=thinking_msg.message_id, 
                        text=displayed_text + " ▌"
                    )
                    last_update_time = time.time()
                except: pass
            await asyncio.sleep(0.02)

        # Final Update (Perfect Markdown & No Cursor)
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id, 
                message_id=thinking_msg.message_id, 
                text=full_response,
                parse_mode="Markdown"
            )
        except:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id, 
                message_id=thinking_msg.message_id, 
                text=full_response
            )
        
        # 2. SILENT BACKGROUND PERSISTENCE (Doesn't crash the UI)
        try:
            pool = await get_db_pool()
            if pool:
                await pool.execute(
                    "INSERT INTO semantic_cache (query_hash, user_query, bot_response) VALUES ($1, $2, $3) ON CONFLICT (query_hash) DO NOTHING",
                    query_hash, user_query, full_response
                )
                asyncio.create_task(log_to_supabase(user_id, user_name, user_query, full_response, telemetry))
            
            history.append({"q": user_query, "a": full_response})
            await _engine.redis.set(redis_key, json.dumps(history[-5:]), ex=86400)
        except Exception as log_err:
            logger.error(f"Background Logging Error: {log_err}")

    except Exception as e:
        logger.error(f"Critical UI Error: {e}")
        # Only show busy if the generation itself failed
        if not full_response:
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=thinking_msg.message_id, text="The system is busy.", parse_mode="Markdown")

async def create_app():
    request_obj = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    application = ApplicationBuilder().token(TOKEN).request(request_obj).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    await application.initialize()
    return application

@app.route('/')
def home(): return "<h1>🚀 Lorin Bot Active</h1>", 200

@app.route('/api/webhook', methods=['POST'])
async def webhook():
    try:
        application = await create_app()
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
        await application.shutdown()
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        # DIAGNOSTIC: Notify Admin of Crash
        try:
            application = await create_app()
            await application.bot.send_message(chat_id=ADMIN_IDS[0], text=f"⚠️ *Lorin Webhook Crash*\nError: `{str(e)}`", parse_mode="Markdown")
            await application.shutdown()
        except: pass
        return str(e), 500

@app.route('/set-webhook')
async def set_webhook():
    host = request.headers.get('Host')
    url = f"https://{host}/api/webhook"
    try:
        application = await create_app()
        await application.bot.set_webhook(url=url)
        await application.shutdown()
        return {"success": True, "url": url}, 200
    except Exception as e: return str(e), 500

@app.after_request
def add_security_headers(response):
    # Origin Lockdown: Only allow your frontend (or localhost for dev)
    # Change 'https://your-frontend-domain.com' to your actual domain
    response.headers['Access-Control-Allow-Origin'] = '*' # For initial launch, then lock to specific domain
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'POST,OPTIONS'
    return response

@app.route('/api/chat', methods=['POST', 'OPTIONS'])
async def secure_chat():
    if request.method == 'OPTIONS': return "OK", 200
    
    global _engine
    if _engine is None: _engine = RAGEngine()
    
    data = request.get_json(force=True)
    query = data.get("query", "")
    user_id = data.get("user_id", "WEB_USER")
    history = data.get("history", "")
    
    # 1. Security & Abuse Check
    is_allowed, reason, val = await check_security(user_id, query, _engine)
    if not is_allowed:
        return {"error": True, "reason": reason, "wait": val}, 403

    # 2. Secure Execution (No keys exposed to frontend)
    full_res = ""
    async def generate():
        nonlocal full_res
        async for chunk in _engine.query_stream(query, history=history):
            if isinstance(chunk, str):
                full_res += chunk
                yield chunk
    
    # For now, return a full response for simplicity in frontend integration
    # (Streaming can be added later if the frontend supports it)
    full_text = ""
    async for chunk in generate():
        if isinstance(chunk, str): full_text += chunk
        
    return {"response": full_text, "status": "SUCCESS"}, 200

@app.route('/api/sunday-report')
async def trigger_sunday_report():
    """Vercel Cron endpoint for Strategic Intelligence"""
    auth_header = request.headers.get("Authorization")
    cron_secret = os.getenv("CRON_SECRET")
    
    if not auth_header or auth_header != f"Bearer {cron_secret}":
        return {"error": "Unauthorized Access"}, 401
        
    try:
        logger.info("Vercel Cron: Starting Sunday Strategic Audit...")
        audit = SundayIntelligence()
        # Use asyncio.create_task to prevent Vercel timeout on the 30s limit
        asyncio.create_task(audit.run())
        return {"status": "SUCCESS", "message": "Strategic Audit Dispatched"}, 200
    except Exception as e:
        logger.error(f"Vercel Cron Error: {e}")
        return {"status": "ERROR", "message": str(e)}, 500

app_handler = app
