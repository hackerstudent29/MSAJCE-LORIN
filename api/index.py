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

# Initialize Telegram Application
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
request_obj = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0, connection_pool_size=10)

print("--- RECONSTRUCTING LORIN BOT ---")
application = ApplicationBuilder().token(TOKEN).request(request_obj).build()

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
    server = HTTPServer(('0.0.0.0', 7860), HealthCheckHandler)
    server.serve_forever()

if __name__ == '__main__':
    from threading import Thread
    Thread(target=run_health_server, daemon=True).start()
    
    print("Bot is starting (Async Polling)...")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()
