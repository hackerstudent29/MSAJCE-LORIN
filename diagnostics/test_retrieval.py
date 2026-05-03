import asyncio
import os
from core.engine import RAGEngine
from langfuse import Langfuse

async def test():
    engine = RAGEngine()
    for query in ["who is yogesh", "wo is saqlin mustaq"]:
        print(f"\nDEBUG: Querying for '{query}'...")
        context_chunks = await engine.get_context(query, None)
        print(f"DEBUG: Found {len(context_chunks)} chunks.")
        for i, c in enumerate(context_chunks[:3]):
            safe_text = c['text'][:150].encode('ascii', 'ignore').decode('ascii')
            print(f"CHUNK {i+1} [ID: {c['id']}]: {safe_text}...")
        print(f"  SOURCE: {c['metadata'].get('source_file')}")
        print("-" * 20)

if __name__ == "__main__":
    asyncio.run(test())
