import os
import json
from upstash_redis import Redis
from dotenv import load_dotenv

load_dotenv()

redis = Redis(url=os.getenv("UPSTASH_REDIS_REST_URL"), token=os.getenv("UPSTASH_REDIS_REST_TOKEN"))

def check_recent_queries():
    # Feedback logs might have some info, but let's check if there are other logs
    # Actually, let's check the last few entries in Redis if any trace info is stored
    # The code doesn't store trace info in Redis, only history and feedback.
    
    # Let's check the history for user queries
    # We don't have a list of all users, but we can check common patterns
    print("Checking Redis keys...")
    keys = redis.keys("user_*_history")
    for key in keys:
        history = redis.get(key)
        print(f"Key: {key}, History: {history}")

if __name__ == "__main__":
    check_recent_queries()
