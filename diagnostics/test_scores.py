import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import RAGEngine

load_dotenv()

def test_query(q):
    engine = RAGEngine()
    print(f"\nTesting Query: {q}")
    
    # 1. Pre-process
    system_prompt = (
        "You are the Intent Classifier and Query Optimizer for MSAJCE (Lorin).\n"
        "CATEGORIES: GREETING, NON_INSTITUTIONAL, INSTITUTIONAL.\n"
        "RULES: If name mentioned, ALWAYS INSTITUTIONAL. search_query should be the name.\n"
        "Return RAW JSON."
    )
    data = {
        "model": engine.generation_model,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": q}],
        "max_tokens": 200
    }
    res = engine._safe_vercel_request(data, label="Pre-Processor")
    print(f"Pre-Processor Response: {res}")
    p = engine._safe_json_parse(res)
    search_query = p.get("search_query", q) if p else q
    print(f"Search Query: {search_query}")

    # 2. Retrieval
    relevant_chunks, max_score = engine.get_context_v41(search_query, "SIMPLE", engine.langfuse.trace(name="test"))
    print(f"Max Score: {max_score}")
    print(f"Results Count: {len(relevant_chunks)}")
    
    # 3. Final Answer
    ans = engine.query(q)
    print(f"Final Answer: {ans}")

if __name__ == "__main__":
    test_query("who is usha")
