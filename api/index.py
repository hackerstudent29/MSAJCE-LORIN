import os
import sys
import logging
import json
import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
import requests
from telegram.request import HTTPXRequest

# Ensure engine.py in core can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

load_dotenv()

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("lorin_bot")

# Initialize Engine
engine = RAGEngine()

# Flask App
app = Flask(__name__)

# --- Configuration & Sanitization ---
def get_clean_env(key, default=""):
    val = os.getenv(key, default)
    if val:
        return val.strip().replace("\n", "").replace("\r", "")
    return default

TOKEN = get_clean_env("TELEGRAM_BOT_TOKEN")
SPACE_URL = "https://ramzendrum-msajce-lorin.hf.space"
PORT = int(os.getenv("PORT", 7860))

# --- Routes ---
@app.route('/')
def home():
    return """
    <h1>🚀 Lorin Bot is ONLINE (Webhook Mode)</h1>
    <p>The institutional brain is active and receiving updates from Telegram.</p>
    <hr>
    <h3>Diagnostic Tools:</h3>
    <ul>
        <li><a href="/health">Health Check</a></li>
        <li><a href="/debug">Environment Debug</a></li>
        <li><a href="/test-telegram"><b>Test Telegram Connection (Send me a DM)</b></a></li>
    </ul>
    """, 200

@app.route('/health')
def health():
    return "OK", 200

@app.route('/debug')
def debug():
    required = ["TELEGRAM_BOT_TOKEN", "PINECONE_API_KEY", "OPENROUTER_API_KEY", "COHERE_API_KEY", "ADMIN_IDS"]
    status = {}
    for r in required:
        val = os.getenv(r)
        if val:
            status[r] = f"OK ({val[:4]}...{val[-4:]})"
        else:
            status[r] = "MISSING ❌"
    return json.dumps(status, indent=4), 200, {'Content-Type': 'application/json'}

@app.route('/telegram-webhook', methods=['POST'])
async def telegram_webhook():
    """Receiver for Telegram updates."""
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return "Error", 500

@app.route('/test-telegram')
async def test_telegram():
    admin_id = get_clean_env("ADMIN_IDS").split(",")[0].strip()
    try:
        await application.bot.send_message(chat_id=admin_id, text=f"✅ Webhook Test: Lorin is talking to you from Hugging Face!")
        return f"✅ SUCCESS! Webhook is active and talking to {admin_id}.", 200
    except Exception as e:
        return f"❌ FAILED! Error: {e}", 500

# --- Telegram Bot Logic ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("MSAJCE Institutional Brain Reconstructed. (Webhook Mode Active)")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_query = update.message.text
    user_id = update.effective_user.id
    thinking_msg = await update.message.reply_text("🔍 Analyzing institutional database...")
    try:
        redis_key = f"user_{user_id}_history"
        history_raw = await engine.redis.get(redis_key)
        history = json.loads(history_raw) if history_raw else []
        history_str = "\n".join([f"User: {h['q']}\nBot: {h['a']}" for h in history])
        answer = await engine.query(user_query, history=history_str)
        history.append({"q": user_query, "a": answer})
        await engine.redis.set(redis_key, json.dumps(history[-5:]), ex=86400)
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=thinking_msg.message_id,
            text=answer
        )
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=thinking_msg.message_id,
            text=f"Oops! I hit a snag: {str(e)}"
        )

# --- App Setup ---
request_obj = HTTPXRequest(connect_timeout=20.0, read_timeout=20.0)
application = ApplicationBuilder().token(TOKEN).request(request_obj).build()

def start_bot():
    logger.info("--- STARTING LORIN IN WEBHOOK MODE ---")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Initialize Application & Set Webhook
    loop = asyncio.get_event_loop()
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.start())
    loop.run_until_complete(application.bot.set_webhook(url=f"{SPACE_URL}/telegram-webhook"))
    logger.info(f"Webhook set to: {SPACE_URL}/telegram-webhook")

    # Start Flask
    app.run(host='0.0.0.0', port=PORT)

if __name__ == '__main__':
    start_bot()
