import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from core.engine import RAGEngine

async def test_hostel():
    print("--- HOSTEL OUTING FORENSIC TEST ---")
    engine = RAGEngine()
    q = "How is the hostel security for girls, and what are the outing rules?"
    
    print(f"Querying: {q}")
    full_text = ""
    async for chunk in engine.query_stream(q):
        if isinstance(chunk, str):
            full_text += chunk
            print(chunk, end="", flush=True)
    
    print("\n\n--- TEST COMPLETE ---")
    if "HOD" in full_text and "Warden" in full_text:
        print("SUCCESS: Hostel Outing Rules correctly delivered.")
    else:
        print("FAIL: Still missing outing details.")

if __name__ == "__main__":
    asyncio.run(test_hostel())
