import asyncio
import os
import sys
import json

# Add root directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import RAGEngine

async def main():
    engine = RAGEngine()
    q = "Who is Ramanathan S and what projects has he built?"
    print(f"\nQuestion: {q}")
    print("-" * 50)
    
    # Manually get context to see what's being retrieved
    context_chunks = await engine.get_context([q], None)
    print(f"Retrieved {len(context_chunks)} chunks.")
    for i, c in enumerate(context_chunks):
        metadata = c.get('metadata', {}) or {}
        text = metadata.get('text', 'NO TEXT FOUND')
        print(f"\nChunk {i+1} (Score: {c.get('rrf_score', 'N/A')}):")
        print(f"ID: {c.get('id')}")
        print(f"Text Snippet: {text[:300]}...")

    print("-" * 50)
    print("Final Answer:")
    async for chunk in engine.query_stream(q):
        if isinstance(chunk, str):
            print(chunk, end="", flush=True)
    print("\n" + "-" * 50)

if __name__ == "__main__":
    asyncio.run(main())
