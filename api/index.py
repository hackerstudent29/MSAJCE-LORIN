import os
import sys
import logging
import json
import asyncio
import time
import re
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from telegram.request import HTTPXRequest

# Ensure engine.py in core can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

load_dotenv()

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("lorin_bot")

# Initialize Flask
app = Flask(__name__)

# --- Global State ---
_engine = None

def get_clean_env(key, default=""):
    val = os.getenv(key, default)
    if val: return val.strip().replace("\n", "").replace("\r", "")
    return default

TOKEN = get_clean_env("TELEGRAM_BOT_TOKEN")

# --- Security Config ---
ABUSIVE_WORDS = ["badword1", "badword2"]

async def check_security(user_id, text, engine):
    now_ts = int(time.time())
    quota_now = datetime.now() - timedelta(hours=4, minutes=30)
    quota_day_str = quota_now.strftime('%Y-%m-%d')
    
    block_key = f"user_{user_id}_blocked_until"
    blocked_until = await engine.redis.get(block_key)
    if blocked_until and int(blocked_until) > now_ts:
        return False, "BLOCKED", (int(blocked_until) - now_ts) // 60 + 1

    day_key = f"user_{user_id}_daily_count_{quota_day_str}"
    daily_count = await engine.redis.get(day_key)
    if daily_count and int(daily_count) >= 30:
        return False, "DAILY_LIMIT", 30

    min_key = f"user_{user_id}_min_count_{now_ts // 60}"
    min_count = await engine.redis.get(min_key)
    if min_count and int(min_count) >= 6:
        return False, "MINUTE_LIMIT", 6

    is_abusive = any(re.search(rf"\b{word}\b", text, re.I) for word in ABUSIVE_WORDS)
    last_msg_key = f"user_{user_id}_last_msg"
    last_data = await engine.redis.get(last_msg_key)
    is_spam = False
    if last_data:
        last_data = json.loads(last_data)
        if now_ts - last_data['time'] < 2 or text == last_data['text']: is_spam = True

    if is_abusive or is_spam:
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 MSAJCE Lorin Active. I'm ready for your questions!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_query = update.message.text
    user_id = update.effective_user.id
    global _engine
    
    is_allowed, reason, val = await check_security(user_id, user_query, _engine)
    if not is_allowed:
        msgs = {"BLOCKED": f"⏳ Wait {val} min.", "MINUTE_LIMIT": "🐢 6 msg/min limit.", "DAILY_LIMIT": "🛑 30/day limit reached.", "BANNED": f"🚫 Blocked {val}h.", "WARNING": f"⚠️ Warning {val}/10."}
        await update.message.reply_text(msgs.get(reason, "Access denied."))
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    thinking_msg = await update.message.reply_text("...")
    
    try:
        redis_key = f"user_{user_id}_history"
        hist_raw = await _engine.redis.get(redis_key)
        history = json.loads(hist_raw) if hist_raw else []
        history_str = "\n".join([f"User: {h['q']}\nBot: {h['a']}" for h in history])
        
        answer = await _engine.query(user_query, history=history_str)
        history.append({"q": user_query, "a": answer})
        await _engine.redis.set(redis_key, json.dumps(history[-5:]), ex=86400)
        
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=thinking_msg.message_id, text=answer)
    except Exception as e:
        logger.error(f"Error: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=thinking_msg.message_id, text="The system is busy. Please try again.")

async def create_app():
    """Create a FRESH application for every request to avoid 'Closed Loop' errors."""
    global _engine
    if _engine is None: _engine = RAGEngine()
    
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
        # 1. Create fresh app for this request
        application = await create_app()
        # 2. Process update
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
        # 3. Shutdown app cleanly (to free the loop)
        await application.shutdown()
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
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

app_handler = app
