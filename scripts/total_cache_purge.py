import os
import asyncio
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def wipe_semantic_cache():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not found.")
        return

    print("--- INITIATING TOTAL CACHE PURGE ---")
    try:
        conn = await asyncpg.connect(db_url)
        await conn.execute("TRUNCATE TABLE semantic_cache;")
        await conn.close()
        print("SUCCESS: Semantic Cache has been completely purged.")
    except Exception as e:
        print(f"Error during purge: {e}")

if __name__ == "__main__":
    asyncio.run(wipe_semantic_cache())
