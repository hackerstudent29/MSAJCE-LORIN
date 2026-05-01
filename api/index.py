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

# --- Global State for Serverless Persistence ---
_engine = None
_application = None

def get_clean_env(key, default=""):
    val = os.getenv(key, default)
    if val: return val.strip().replace("\n", "").replace("\r", "")
    return default

TOKEN = get_clean_env("TELEGRAM_BOT_TOKEN")

async def get_bot_app():
    global _application, _engine
    if _engine is None:
        _engine = RAGEngine()
    
    if _application is None:
        # High timeouts for initial cold starts
        request_obj = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
        _application = ApplicationBuilder().token(TOKEN).request(request_obj).build()
        
        # Register Handlers
        _application.add_handler(CommandHandler("start", start))
        _application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        await _application.initialize()
        await _application.start()
    return _application, _engine

# --- Telegram Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("MSAJCE Institutional Brain Active (Vercel Serverless). I am ready.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_query = update.message.text
    user_id = update.effective_user.id
    
    # We need the engine here. In serverless, we get it from global state.
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

# --- Vercel Routes ---
@app.route('/')
def home():
    return "<h1>🚀 Lorin Bot (Vercel Serverless)</h1><p>Bot is active via Webhook.</p>", 200

@app.route('/favicon.ico')
@app.route('/favicon.png')
def favicon():
    return '', 204

@app.route('/debug-vercel')
def debug_vercel():
    """Check if environment variables are actually present in Vercel."""
    vars_to_check = [
        "TELEGRAM_BOT_TOKEN", "PINECONE_API_KEY", "OPENROUTER_API_KEY", 
        "COHERE_API_KEY", "UPSTASH_REDIS_REST_URL", "VERCEL_AI_KEY_6"
    ]
    status = {}
    for v in vars_to_check:
        val = os.getenv(v)
        if val:
            status[v] = f"OK ({val[:4]}...{val[-4:]})"
        else:
            status[v] = "MISSING ❌"
    return status, 200

@app.route('/api/webhook', methods=['POST'])
async def webhook():
    """Receiver for Telegram updates on Vercel."""
    try:
        bot_app, _ = await get_bot_app()
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        await bot_app.process_update(update)
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return "Error", 500

@app.route('/set-webhook')
async def set_webhook():
    """Utility to set the webhook from browser."""
    # Vercel URLs are usually PROJECT_NAME.vercel.app
    # But since we don't know the name yet, we ask the user to provide it.
    host = request.headers.get('Host')
    if not host: return "Error: Could not determine host.", 400
    
    webhook_url = f"https://{host}/api/webhook"
    try:
        bot_app, _ = await get_bot_app()
        await bot_app.bot.set_webhook(url=webhook_url)
        return f"✅ SUCCESS! Webhook set to: {webhook_url}", 200
    except Exception as e:
        return f"❌ FAILED: {e}", 500

# Required for Vercel
app_handler = app
