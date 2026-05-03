import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure core can be imported
# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

async def test_retrieval():
    load_dotenv()
    engine = RAGEngine()
    query = "Weslin"
    print(f"Testing retrieval for: {query}")
    
    # Check BM25
    if engine.bm25:
        import bm25s
        tokens = bm25s.tokenize(query, stemmer=engine.stemmer)
        chunks, scores = engine.bm25.retrieve(tokens, k=5)
        print(f"BM25 Hits: {len(chunks[0])}")
        for i, c in enumerate(chunks[0]):
            print(f"Hit {i+1}: {c.get('text')[:100]}...")
    else:
        print("BM25 not loaded!")

    # Check context
    context = await engine.get_context(query, engine.langfuse.trace(name="Test"))
    print(f"\nFinal Combined Context Hits: {len(context)}")
    for i, c in enumerate(context):
        print(f"Context {i+1}: {c.get('text')[:100]}...")

if __name__ == "__main__":
    asyncio.run(test_retrieval())
