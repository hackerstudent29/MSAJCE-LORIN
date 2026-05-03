import os
import asyncio
import hashlib
from dotenv import load_dotenv
import asyncpg

load_dotenv()

async def setup_cache_table():
    print("--- DEPLOYING SEMANTIC CACHE TABLE ---")
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    
    try:
        # Create cache table if it doesn't exist
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_cache (
                query_hash TEXT PRIMARY KEY,
                user_query TEXT NOT NULL,
                bot_response TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Index for faster lookups
            CREATE INDEX IF NOT EXISTS idx_query_hash ON semantic_cache(query_hash);
        """)
        print("SUCCESS: 'semantic_cache' table is live.")
    except Exception as e:
        print(f"ERROR: Failed to deploy cache table: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(setup_cache_table())
