import os
import sys
import logging
import json
import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
from http.server import BaseHTTPRequestHandler, HTTPServer
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

# Flask App for Health Checks
app = Flask(__name__)

@app.route('/health')
def health():
    return "OK", 200

@app.route('/debug')
def debug():
    required = [
        "TELEGRAM_BOT_TOKEN", "PINECONE_API_KEY", "OPENROUTER_API_KEY", 
        "COHERE_API_KEY", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN",
        "VERCEL_AI_KEY_6", "ADMIN_IDS"
    ]
    status = {}
    for r in required:
        val = os.getenv(r)
        if val:
            # Mask most of the key for safety, show only first 4 and last 4
            masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "SET"
            status[r] = f"OK ({masked})"
        else:
            status[r] = "MISSING ❌"
    return json.dumps(status, indent=4), 200, {'Content-Type': 'application/json'}

# Initialize Telegram Application with extreme timeouts for HF
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
request_obj = HTTPXRequest(
    connect_timeout=100.0, 
    read_timeout=100.0, 
    write_timeout=100.0,
    pool_timeout=100.0,
    connection_pool_size=20
)

print("--- RECONSTRUCTING LORIN BOT ---")

async def post_init(app):
    admin_ids = os.getenv("ADMIN_IDS", "").split(",")
    for admin_id in admin_ids:
        if admin_id.strip():
            try:
                await app.bot.send_message(chat_id=admin_id.strip(), text="🚀 Lorin Engine is ONLINE (Hugging Face)")
                print(f"Startup notification sent to {admin_id}")
            except Exception as e:
                print(f"Could not notify admin {admin_id}: {e}")

application = ApplicationBuilder().token(TOKEN).request(request_obj).post_init(post_init).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("MSAJCE Institutional Brain Reconstructed. I am ready.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    user_query = update.message.text
    user_id = update.effective_user.id
    print(f"User {user_id}: {user_query}")
    
    # 1. Thinking message
    thinking_msg = await update.message.reply_text("🔍 Analyzing institutional database...")
    
    try:
        # 2. Redis History (Async)
        redis_key = f"user_{user_id}_history"
        history_raw = await engine.redis.get(redis_key)
        history = json.loads(history_raw) if history_raw else []
        history_str = "\n".join([f"User: {h['q']}\nBot: {h['a']}" for h in history])
        
        # 3. Await Engine Query (Async)
        answer = await engine.query(user_query, history=history_str)
        
        # 4. Update History
        history.append({"q": user_query, "a": answer})
        await engine.redis.set(redis_key, json.dumps(history[-5:]), ex=86400)
        
        # 5. Final Response
        keyboard = [[
            InlineKeyboardButton("👍 Accurate", callback_data=f"fb:up:{user_id}"),
            InlineKeyboardButton("👎 Hallucination", callback_data=f"fb:down:{user_id}")
        ]]
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=thinking_msg.message_id,
            text=answer,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        print(f"Responded to {user_id}")
        
    except Exception as e:
        print(f"Error: {e}")
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=thinking_msg.message_id,
            text=f"Oops! I hit a snag: {str(e)}"
        )

# Health Check Server
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    # Use Flask to serve both health and debug routes
    app.run(host='0.0.0.0', port=7860, debug=False, use_reloader=False)

if __name__ == '__main__':
    from threading import Thread
    # Start Flask in a background thread
    Thread(target=run_health_server, daemon=True).start()
    
    print("Bot is starting (Async Polling)...")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()
