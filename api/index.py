import os
import sys
import logging
import json
import asyncio
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("MSAJCE Institutional Brain Active (Vercel Serverless). I am ready.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_query = update.message.text
    user_id = update.effective_user.id
    
    global _engine
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
            text=f"Oops! Snag: {str(e)}"
        )

async def get_bot_app():
    """Serverless-safe application getter."""
    global _application, _engine, _app_ready
    
    if _engine is None:
        _engine = RAGEngine()
        
    if _application is None:
        request_obj = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
        _application = ApplicationBuilder().token(TOKEN).request(request_obj).build()
        _application.add_handler(CommandHandler("start", start))
        _application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
    # Always ensure initialization state if the loop was reset
    if not _app_ready:
        await _application.initialize()
        _app_ready = True
    
    return _application

# --- Vercel Routes ---
@app.route('/')
def home():
    return "<h1>🚀 Lorin Bot (Vercel Serverless)</h1><p>Bot is active via Webhook.</p>", 200

@app.route('/debug-vercel')
def debug_vercel():
    vars_to_check = ["TELEGRAM_BOT_TOKEN", "PINECONE_API_KEY", "OPENROUTER_API_KEY"]
    return {v: "OK" if os.getenv(v) else "MISSING" for v in vars_to_check}, 200

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
        # Use a fresh request to set webhook to avoid loop issues
        await bot_app.bot.set_webhook(url=webhook_url)
        info = await bot_app.bot.get_webhook_info()
        return {
            "success": True,
            "url": info.url,
            "pending_updates": info.pending_update_count,
            "last_error": info.last_error_message
        }, 200
    except Exception as e:
        return f"❌ FAILED: {str(e)}", 500

# Export for Vercel
app_handler = app
