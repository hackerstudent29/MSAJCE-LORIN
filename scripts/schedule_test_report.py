import time
import asyncio
from datetime import datetime
from sunday_intelligence import SundayIntelligence

async def wait_until_440_pm():
    target_hour = 16
    target_minute = 40
    
    print(f"Lorin Scheduler: Waiting for 4:40:00 PM (16:40:00) to prove dispatch confidence...")
    
    while True:
        now = datetime.now()
        if now.hour == target_hour and now.minute == target_minute:
            print(f"TRIGGER: Time reached {now.strftime('%H:%M:%S')}. Launching Strategic Audit...")
            audit = SundayIntelligence()
            await audit.run()
            print("TEST COMPLETE: 4:40 PM Dispatch Successful.")
            break
        
        # Check every 10 seconds to avoid CPU load
        if now.minute < target_minute or now.hour < target_hour:
            time.sleep(10)
        else:
            # If we somehow missed it, trigger immediately
            print("Lorin Scheduler: Time window detected. Triggering now.")
            audit = SundayIntelligence()
            await audit.run()
            break

if __name__ == "__main__":
    asyncio.run(wait_until_440_pm())
