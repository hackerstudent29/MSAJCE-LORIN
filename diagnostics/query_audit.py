import os
import asyncpg
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def run():
    db_url = os.getenv('DATABASE_URL')
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    
    # Get column names
    columns = await conn.fetch("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'interactions'
    """)
    print("Columns:", [c['column_name'] for c in columns])
    
    # Get total count
    count = await conn.fetchval("SELECT count(*) FROM interactions")
    print(f"Total Records: {count}")
    
    # Get last 5
    rows = await conn.fetch("""
        SELECT * FROM interactions 
        ORDER BY timestamp DESC 
        LIMIT 5
    """)
    
    print("\n--- INDIVIDUAL QUERY AUDIT ---")
    for row in rows:
        print(row)
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
