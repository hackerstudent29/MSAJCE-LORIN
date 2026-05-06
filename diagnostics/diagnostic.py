import os
from dotenv import load_dotenv

load_dotenv()

# Set output to UTF-8 for Windows compatibility
sys.stdout.reconfigure(encoding='utf-8')

async def check_bot():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[ERROR] TELEGRAM_BOT_TOKEN not found in environment!")
        return
    url = f"https://api.telegram.org/bot{token}/getMe"
    
    print(f"--- DIAGNOSTIC START ---")
    print(f"Testing Token: {token[:15]}...")
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                print(f"[SUCCESS] Token is VALID!")
                print(f"Bot Name: {data['result']['first_name']}")
                print(f"Username: @{data['result']['username']}")
                
                # Check for active Webhooks
                print("\nChecking for Webhooks...")
                webhook_url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
                wh_resp = await client.get(webhook_url, timeout=15)
                wh_data = wh_resp.json()
                if wh_data['result']['url']:
                    print(f"[WARNING] Webhook is ACTIVE on: {wh_data['result']['url']}")
                    print("This will block Polling (Hugging Face) from working!")
                else:
                    print("[OK] No Webhook detected. Polling should work.")

            else:
                print(f"[ERROR] Token is INVALID! Telegram says: {resp.text}")
        except Exception as e:
            print(f"[FATAL] Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(check_bot())
