import os
import requests
from dotenv import load_dotenv

load_dotenv()

def set_webhook(url):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env")
        return

    webhook_url = f"{url.rstrip('/')}/api/webhook"
    api_url = f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}"
    
    print(f"Setting webhook to: {webhook_url}")
    response = requests.get(api_url)
    
    if response.status_code == 200:
        print("Success: Webhook updated!")
        print(response.json())
    else:
        print(f"Error: Failed to set webhook. Status code: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python scripts/activate_webhook.py <YOUR_VERCEL_URL>")
        print("Example: python scripts/activate_webhook.py https://msajce-bot.vercel.app")
    else:
        set_webhook(sys.argv[1])
