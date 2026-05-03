import asyncio
import os
import sys
import json
from dotenv import load_dotenv

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

async def test_retrieval():
    load_dotenv()
    engine = RAGEngine()
    
    # Get query from command line or default
    query = sys.argv[1] if len(sys.argv) > 1 else "admission process"
    print(f"--- DIAGNOSTIC START: {query} ---")
    
    # 1. Intent Classification Check
    trace = engine.langfuse.trace(name="Diagnostic")
    span = trace.span(name="Pre-Processor")
    data = {
        "model": engine.generation_model,
        "messages": [{"role": "system", "content": engine._get_system_prompt_pre()}, {"role": "user", "content": f"Query: {query}"}],
        "max_tokens": 400
    }
    res = await engine._safe_vercel_request(data, label="Pre-Processor", span=span)
    p = engine._safe_json_parse(res)
    search_q = p.get("search_query", query) if p else query
    print(f"Intent Category: {p.get('category') if p else 'N/A'}")
    print(f"Generated Search Query: {search_q}")

    # 2. BM25 Raw Check
    if engine.bm25:
        import bm25s
        tokens = bm25s.tokenize(search_q, stemmer=engine.stemmer)
        chunks, scores = engine.bm25.retrieve(tokens, k=5)
        print(f"\nBM25 Hits Found: {len(chunks[0])}")
        for i, c in enumerate(chunks[0]):
            print(f"  [{i+1}] {c.get('chunk_id')}: {c.get('text')[:100]}...")
    
    # 3. Final Context
    context = await engine.get_context(search_q, trace)
    print(f"\nFinal Merged Context Hits: {len(context)}")
    for i, c in enumerate(context):
        print(f"  [C{i+1}] {c.get('chunk_id')}: {c.get('text')[:100]}...")

    # 4. Generate Answer
    system_gen = engine._get_system_prompt_gen("\n\n".join([f"[S{i+1}]: {c['text']}" for i, c in enumerate(context)]))
    data_gen = {
        "model": engine.generation_model,
        "messages": [{"role": "system", "content": system_gen}, {"role": "user", "content": f"Query: {query}"}],
        "max_tokens": 800
    }
    answer = await engine._safe_vercel_request(data_gen, label="Generator", span=trace.span(name="Generation"))
    print(f"\n--- FINAL ANSWER ---\n{answer}\n")

# Mock the internal methods if they don't exist yet (for older engine versions)
if not hasattr(RAGEngine, '_get_system_prompt_pre'):
    def _get_system_prompt_pre(self):
        return """Classify intent and rewrite for search. Return JSON: {category, search_query, direct_response}"""
    RAGEngine._get_system_prompt_pre = _get_system_prompt_pre

if not hasattr(RAGEngine, '_get_system_prompt_gen'):
    def _get_system_prompt_gen(self, context_text):
        return f"You are Lorin, the institutional assistant. Answer based on: {context_text}"
    RAGEngine._get_system_prompt_gen = _get_system_prompt_gen

if __name__ == "__main__":
    asyncio.run(test_retrieval())
