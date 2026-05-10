import os
import asyncio
import asyncpg
from upstash_redis import Redis
from dotenv import load_dotenv

load_dotenv()

async def wipe_all():
    print("--- INITIATING TOTAL SYSTEM PURGE ---")
    
    # 1. Database Purge
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        try:
            # Pgbouncer often needs statement_cache_size=0
            conn = await asyncpg.connect(db_url, statement_cache_size=0)
            await conn.execute("TRUNCATE TABLE semantic_cache;")
            await conn.close()
            print("[OK] Database semantic_cache purged.")
        except Exception as e:
            print(f"[ERROR] Database error: {e}")
    
    # 2. Redis Purge
    try:
        # Use simple environment variables for Redis
        url = os.getenv("UPSTASH_REDIS_REST_URL")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        if url and token:
            redis = Redis(url=url, token=token)
            redis.flushdb()
            print("[OK] Redis cache flushed (History, Strikes, and Sessions cleared).")
        else:
            print("[SKIP] Redis credentials missing.")
    except Exception as e:
        print(f"[ERROR] Redis error: {e}")

if __name__ == "__main__":
    asyncio.run(wipe_all())
