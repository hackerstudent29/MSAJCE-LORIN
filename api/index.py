import os
import sys
import logging
import json
import asyncio
import time
import re
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
_application = None
_app_ready = False

def get_clean_env(key, default=""):
    val = os.getenv(key, default)
    if val: return val.strip().replace("\n", "").replace("\r", "")
    return default

TOKEN = get_clean_env("TELEGRAM_BOT_TOKEN")

# --- Security Config ---
ABUSIVE_WORDS = [
    "badword1", "badword2" # User: Add more here or use a library
]

async def check_security(user_id, text, engine):
    """Checks for abuse, spam, and blocks. Returns (is_allowed, reason, retry_after_hours)"""
    now = int(time.time())
    
    # 1. Check if currently blocked
    block_key = f"user_{user_id}_blocked_until"
    blocked_until = await engine.redis.get(block_key)
    if blocked_until and int(blocked_until) > now:
        remaining = (int(blocked_until) - now) // 3600
        return False, "BLOCKED", remaining if remaining > 0 else 1

    # 2. Check for Abuse/Profanity
    is_abusive = any(re.search(rf"\b{word}\b", text, re.I) for word in ABUSIVE_WORDS)
    
    # 3. Check for Spam (Rate Limiting + Duplicate)
    last_msg_key = f"user_{user_id}_last_msg"
    last_data = await engine.redis.get(last_msg_key)
    is_spam = False
    if last_data:
        last_data = json.loads(last_data)
        if now - last_data['time'] < 2: is_spam = True # Too fast
        if text == last_data['text']: is_spam = True # Duplicate/Copy-paste

    # 4. Handle Strikes if Abusive or Spam
    if is_abusive or is_spam:
        strike_key = f"user_{user_id}_strikes"
        strikes = await engine.redis.incr(strike_key)
        
        # Determine Block Duration
        duration = 0
        if strikes >= 10: duration = 7 * 24 # 1 Week
        elif strikes >= 5: duration = 24 # 1 Day
        elif strikes >= 3: duration = 6 # 6 Hours
        
        if duration > 0:
            await engine.redis.set(block_key, now + (duration * 3600))
            return False, f"BANNED_{duration}", duration
        
        return False, "WARNING", strikes

    # Update last message data
    await engine.redis.set(last_msg_key, json.dumps({"time": now, "text": text}), ex=300)
    return True, None, 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! I am Lorin, your college assistant. Ask me anything about MSAJCE!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_query = update.message.text
    user_id = update.effective_user.id
    
    global _engine
    
    # --- SECURITY CHECK ---
    is_allowed, reason, val = await check_security(user_id, user_query, _engine)
    
    if not is_allowed:
        if reason == "BLOCKED":
            return # Silent ignore if already blocked
        if reason.startswith("BANNED"):
            await update.message.reply_text(f"🛑 Access Denied. Due to repeated violations, you are blocked for {val} hours.")
            return
        if reason == "WARNING":
            await update.message.reply_text(f"⚠️ Warning {val}/10: Abuse or Spam detected. Your ID has been logged. Further violations will result in a block.")
            return

    thinking_msg = await update.message.reply_text("🔍 Analyzing institutional database...")
    
    try:
        redis_key = f"user_{user_id}_history"
        history_raw = await _engine.redis.get(redis_key)
        history = json.loads(history_raw) if history_raw else []
        history_str = "\n".join([f"User: {h['q']}\nBot: {h['a']}" for h in history])
        
        answer = await _engine.query(user_query, history=history_str)
        
        history.append({"q": user_query, "a": answer})
        await _engine.redis.set(redis_key, json.dumps(history[-5:]), ex=86400)
        
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=thinking_msg.message_id,
            text=answer
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=thinking_msg.message_id,
            text=f"The system is busy or encountered a brief error. Please try again in a moment."
        )

async def get_bot_app():
    global _application, _engine, _app_ready
    if _engine is None: _engine = RAGEngine()
    if _application is None:
        request_obj = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
        _application = ApplicationBuilder().token(TOKEN).request(request_obj).build()
        _application.add_handler(CommandHandler("start", start))
        _application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    if not _app_ready:
        await _application.initialize()
        _app_ready = True
    return _application

@app.route('/')
def home():
    return "<h1>🚀 Lorin Bot (Vercel Serverless)</h1><p>Bot is active via Webhook.</p>", 200

@app.route('/api/webhook', methods=['POST'])
async def webhook():
    try:
        bot_app = await get_bot_app()
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        await bot_app.process_update(update)
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return str(e), 500

@app.route('/set-webhook')
async def set_webhook():
    host = request.headers.get('Host')
    webhook_url = f"https://{host}/api/webhook"
    try:
        bot_app = await get_bot_app()
        await bot_app.bot.set_webhook(url=webhook_url)
        return {"success": True, "url": webhook_url}, 200
    except Exception as e:
        return f"❌ FAILED: {str(e)}", 500

app_handler = app
