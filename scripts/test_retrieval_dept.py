import asyncio
import sys
import os
sys.path.append(os.getcwd())
from core.engine import RAGEngine

async def test_retrieval():
    e = RAGEngine()
    query = "list all departments and programs in MSAJCE"
    print(f"\nTesting Retrieval for: {query}")
    
    # Check BM25
    import bm25s
    tokens = bm25s.tokenize(query, stemmer=e.stemmer)
    chunks, scores = e.bm25.retrieve(tokens, k=10)
    print("\n--- BM25 Top Hits ---")
    for c, s in zip(chunks[0], scores[0]):
        print(f"[{s:.4f}] {c['chunk_id']} - {c['metadata'].get('source_file')} - {c['text'][:100]}...")
    
    # Check Pinecone
    e_res = await e.get_context(query, None)
    print("\n--- Combined (Reranked) Top Hits ---")
    for r in e_res:
        print(f"[{r.get('f_score', 0):.4f}] {r['id']} - {r['metadata'].get('source_file')} - {r['text'][:100]}...")

if __name__ == "__main__":
    asyncio.run(test_retrieval())
