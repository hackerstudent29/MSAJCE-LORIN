import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from core.engine import RAGEngine

async def test_override():
    print("--- PRIORITY OVERRIDE PROBE ---")
    engine = RAGEngine()
    q = "Is the NBA Accreditation valid for all departments, or just a few?"
    
    print(f"Querying: {q}")
    full_text = ""
    async for chunk in engine.query_stream(q):
        if isinstance(chunk, str):
            full_text += chunk
            print(chunk, end="", flush=True)
    
    print("\n\n--- PROBE COMPLETE ---")
    if "CSE" in full_text and "Mechanical" in full_text:
        print("SUCCESS: Priority Override achieved. Ground Truth used.")
    else:
        print("FAIL: Still refusing or using old data.")

if __name__ == "__main__":
    asyncio.run(test_override())
