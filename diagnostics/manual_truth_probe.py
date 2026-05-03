import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure we import from the local core
sys.path.append(os.getcwd())
load_dotenv()

from core.engine import RAGEngine

async def test_truth():
    print("--- MANUAL TRUTH PROBE START ---")
    engine = RAGEngine()
    q = "What is the highest salary package for 2024?"
    
    print(f"Querying: {q}")
    full_text = ""
    async for chunk in engine.query_stream(q):
        if isinstance(chunk, str):
            full_text += chunk
            print(chunk, end="", flush=True)
    
    print("\n\n--- PROBE COMPLETE ---")
    if "12" in full_text:
        print("SUCCESS: Ground Truth detected.")
    else:
        print("FAIL: Ground Truth missing from response.")

if __name__ == "__main__":
    asyncio.run(test_truth())
