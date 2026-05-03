import os
import requests
from dotenv import load_dotenv

load_dotenv()

def delete_webhook():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    api_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
    response = requests.get(api_url)
    print(response.json())

if __name__ == "__main__":
    delete_webhook()
