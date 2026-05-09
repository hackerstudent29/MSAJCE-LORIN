import asyncio
import os
import sys

# Add root directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import RAGEngine

async def main():
    engine = RAGEngine()
    q = "Who is Yogesh?"
    print(f"\nQuestion: {q}")
    print("-" * 50)
    full_ans = ""
    async for chunk in engine.query_stream(q):
        if isinstance(chunk, str):
            print(chunk, end="", flush=True)
            full_ans += chunk
    print("\n" + "-" * 50)

if __name__ == "__main__":
    asyncio.run(main())
