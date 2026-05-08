import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import RAGEngine

async def diagnose_query(q):
    load_dotenv()
    engine = RAGEngine()
    
    print(f"\n--- DIAGNOSING: '{q}' ---")
    
    # 1. Test Pre-processor
    p = None
    # Skip simple check to force pre-processor diagnostic
    gt_context = "\n".join([f"- {k.upper()}: {v}" for k, v in engine.ground_truth.items()])
    data_pre = {
        "model": "google/gemini-2.0-flash-exp:free",
        "messages": [
            {"role": "system", "content": f"Classify intent. Ground Truth: {gt_context}"},
            {"role": "user", "content": q}
        ]
    }
    print(f"Checking Ground Truth mapping...")
    
    # 2. Test Retrieval & Scores
    print(f"Checking Retrieval Scores...")
    queries = [q]
    context_chunks = await engine.get_context(queries, None)
    
    if not context_chunks:
        print("  [FAIL] No chunks found at all.")
    else:
        top = context_chunks[0]
        score = top.get("f_score", 0)
        conf_low = top.get("confidence_low", False)
        print(f"  Top Score: {score:.4f}")
        print(f"  Confidence Low Flag: {conf_low}")
        print(f"  Top Source: {top.get('metadata', {}).get('source_file', 'Unknown')}")
        print(f"  Text Snippet: {top.get('text', '')[:100]}...")

    # 3. Test Full Output
    print(f"\nFinal Bot Response:")
    async for chunk in engine.query_stream(q):
        if isinstance(chunk, str):
            print(chunk, end="", flush=True)
    print("\n---------------------------\n")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        asyncio.run(diagnose_query(query))
    else:
        # Default test cases
        asyncio.run(diagnose_query("who is the csi vp?"))
        asyncio.run(diagnose_query("what is the college code?"))
