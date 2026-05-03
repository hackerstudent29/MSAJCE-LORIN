import asyncio
import os
import sys
import json
from dotenv import load_dotenv

# Ensure core can be imported
# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

async def check_logs():
    load_dotenv()
    engine = RAGEngine()
    
    print("Fetching last 5 forensic logs...")
    logs = await engine.redis.lrange("lorin_forensic_logs", 0, 4)
    for i, log_raw in enumerate(logs):
        log = json.loads(log_raw)
        print(f"\n--- Log {i+1} ---")
        print(f"Time: {log.get('timestamp')}")
        print(f"Query: {log.get('query')}")
        print(f"Intent: {log.get('intent')}")
        print(f"Match Score: {log.get('match_score')}")
        print(f"Latency: {log.get('latency')}ms")

if __name__ == "__main__":
    asyncio.run(check_logs())
