import asyncio
import sys
import os
sys.path.append(os.getcwd())
from core.engine import RAGEngine

async def test():
    e = RAGEngine()
    query = "hi"
    print(f"\nQuery: {query}")
    async for c in e.query_stream(query):
        if isinstance(c, str):
            print(c, end="", flush=True)
    print("\n")

if __name__ == "__main__":
    asyncio.run(test())
