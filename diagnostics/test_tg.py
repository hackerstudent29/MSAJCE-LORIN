import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    resp = requests.get(url)
    print(f"getWebhookInfo status: {resp.status_code}")
    print(f"getWebhookInfo response:\n{resp.text}")

if __name__ == "__main__":
    test()
