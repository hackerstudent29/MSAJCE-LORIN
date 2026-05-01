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
    return f"""
    <h1>🚀 Lorin Bot is ONLINE (Bypass Mode)</h1>
    <p>The institutional brain is active, but the server IP may be blocked by Telegram.</p>
    <hr>
    <h3>Step 1: The Magic Bypass</h3>
    <p>If the bot isn't responding, click this button. It uses <b>YOUR</b> internet connection to tell Telegram to talk to this server.</p>
    <button onclick="setWebhook()" style="padding: 15px; background: #6366F1; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 16px;">
        ⚡ Force Webhook via Browser
    </button>

    <script>
    function setWebhook() {{
        const token = "{TOKEN}";
        const url = "{SPACE_URL}/telegram-webhook";
        const tgUrl = `https://api.telegram.org/bot${{token}}/setWebhook?url=${{url}}`;
        
        fetch(tgUrl)
            .then(r => r.json())
            .then(data => {{
                if (data.ok) {{
                    alert("✅ SUCCESS! Telegram is now pointing to this Space. Try the bot now!");
                }} else {{
                    alert("❌ FAILED: " + data.description);
                }}
            }})
            .catch(e => alert("❌ ERROR: " + e));
    }}
    </script>

    <hr>
    <h3>Step 2: Diagnostics</h3>
    <ul>
        <li><a href="/health">Health Check</a></li>
        <li><a href="/debug">Environment Debug</a></li>
        <li><a href="/test-telegram">Test Telegram Connection</a></li>
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
# Set to 300s (5 minutes) to wait out cloud-tier IP throttling
request_obj = HTTPXRequest(
    connect_timeout=300.0, 
    read_timeout=300.0, 
    write_timeout=300.0,
    pool_timeout=300.0
)
application = ApplicationBuilder().token(TOKEN).request(request_obj).build()

def start_bot():
    logger.info("--- STARTING LORIN IN BYPASS MODE ---")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Initialize Application & Set Webhook (Non-Fatal)
    loop = asyncio.get_event_loop()
    try:
        logger.info("Attempting server-side initialization...")
        loop.run_until_complete(application.initialize())
        loop.run_until_complete(application.start())
        # We try to set it, but we won't crash if it fails
        loop.run_until_complete(application.bot.set_webhook(url=f"{SPACE_URL}/telegram-webhook"))
        logger.info("✅ Server-side Webhook Set Success!")
    except Exception as e:
        logger.warning(f"⚠️ Server-side init failed (IP likely blocked): {e}")
        logger.info("Web server will stay online. Use the 'Magic Bypass' button on the home page.")

    # Start Flask (Blocks)
    app.run(host='0.0.0.0', port=PORT)

if __name__ == '__main__':
    start_bot()
