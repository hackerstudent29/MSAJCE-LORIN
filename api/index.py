import os
import sys
import logging
import json
import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv

# Ensure engine.py in core can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

load_dotenv()

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("lorin_bot")
global_logger = logger # Explicitly global

# Initialize Engine
engine = RAGEngine()

# Flask App
app = Flask(__name__)

# Initialize Application
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
application = ApplicationBuilder().token(TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Simple direct start."""
    await update.message.reply_text("MSAJCE Institutional Brain Active. Ask me anything about the college.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle queries with perceived streaming response."""
    user_query = update.message.text
    user_id = update.effective_user.id
    
    # 1. Manage Persistent Conversation History (Redis)
    redis_key = f"user_{user_id}_history"
    history_raw = engine.redis.get(redis_key)
    history = json.loads(history_raw) if history_raw else []
    
    history_str = "\n".join([f"User: {h['q']}\nBot: {h['a']}" for h in history])
    
    # 2. Initial "Thinking" message
    message = await update.message.reply_text("🔍 Analyzing institutional database...")
    
    # 3. Setup Feedback Buttons
    keyboard = [[
        InlineKeyboardButton("👍 Accurate", callback_data=f"fb:up:{user_id}"),
        InlineKeyboardButton("👎 Hallucination", callback_data=f"fb:down:{user_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        # Get answer from Engine (Synchronous call with history)
        answer = engine.query(user_query, history=history_str)
        
        # Update History in Redis (Keep last 5 turns, 24h expiry)
        history.append({"q": user_query, "a": answer})
        new_history = history[-5:]
        engine.redis.set(redis_key, json.dumps(new_history), ex=86400)
        
        # Simple animation/chunked update for better UX
        words = answer.split()
        chunk_size = 15 
        display_text = ""
        
        for i in range(0, len(words), chunk_size):
            display_text = " ".join(words[:i+chunk_size])
            if i + chunk_size < len(words):
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=message.message_id,
                        text=f"{display_text}..."
                    )
                    await asyncio.sleep(0.05) 
                except: pass
            
        # Final Final Update with Buttons
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=message.message_id,
            text=answer,
            reply_markup=reply_markup
        )
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        global_logger.error(f"Error handling message:\n{error_trace}")
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=message.message_id,
            text=f"System Error: {str(e)}"
        )

async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Capture Step 21 Feedback."""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split(":")
    action = parts[1]
    user_id = parts[2]
    
    import time
    feedback_entry = {
        "user_id": user_id,
        "action": action,
        "timestamp": time.time(),
        "query": "Feedback on response"
    }
    
    engine.redis.rpush("feedback_logs", json.dumps(feedback_entry))
    await query.edit_message_text(text=f"{query.message.text}\n\n✅ Thank you for the feedback!")

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(handle_feedback))
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

@app.route('/api/webhook', methods=['POST'])
def webhook():
    """Handle incoming Telegram updates via Webhook."""
    if request.method == "POST":
        try:
            update = Update.de_json(request.get_json(force=True), application.bot)
            
            async def process():
                await application.initialize()
                await application.process_update(update)
            
            asyncio.run(process())
            return "OK", 200
        except Exception as e:
            global_logger.error(f"Webhook error: {e}")
            return str(e), 500
    return "Method Not Allowed", 405

@app.route('/')
def index():
    return "Lorin RAG Bot is Online", 200

if __name__ == '__main__':
    print("Bot is starting in FULL 29-STEP PRODUCTION MODE (Polling)...")
    application.run_polling(drop_pending_updates=True)

