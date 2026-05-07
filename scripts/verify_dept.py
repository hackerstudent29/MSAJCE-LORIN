import asyncio
import sys
import os
sys.path.append(os.getcwd())
from core.engine import RAGEngine

async def test_departments():
    e = RAGEngine()
    query = "what are the departments does the college provides"
    print(f"\nQuery: {query}")
    async for c in e.query_stream(query):
        if isinstance(c, str):
            print(c, end="", flush=True)
    print("\n")

if __name__ == "__main__":
    asyncio.run(test_departments())
