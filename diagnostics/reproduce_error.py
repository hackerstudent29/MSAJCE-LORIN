import os
import sys
import json
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

load_dotenv()

def reproduce():
    # Force quotes to test if they cause Errno 22
    url = '"https://joint-bobcat-97753.upstash.io"'
    token = '"gQAAAAAAAX3ZAAIgcDE0NjI0YmFhZTZlYmE0ZDA1YTdmYmVhNTg3MmE2YTg0ZA"'
    from upstash_redis import Redis
    redis = Redis(url=url, token=token)
    
    engine = RAGEngine()
    engine.redis = redis # Overwrite with quoted one
    
    user_id = "test_user_123"
    redis_key = f"user_{user_id}_history"
    try:
        print("Fetching history...")
        history_raw = engine.redis.get(redis_key)
        history = [] # simulate empty
        history_str = ""
        
        print("Running query...")
        answer = engine.query("hey", history=history_str)
        print(f"Answer: {answer}")
        
        print("Updating history...")
        history.append({"q": "hey", "a": answer})
        engine.redis.set(redis_key, json.dumps(history), ex=86400)
        print("History updated.")
    except Exception as e:
        import traceback
        print(f"Caught exception: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    reproduce()
