import os
import asyncpg
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def run():
    db_url = os.getenv('DATABASE_URL')
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    await conn.execute("""
        INSERT INTO interactions (timestamp, user_id, user_name, query, intent, response, latency_ms, tokens_used) 
        VALUES (NOW(), 7770158141, 'Antigravity', 'Production Test', 'DIAGNOSTIC', 'Success', 100, 1000)
    """)
    print("Test Record Injected.")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
