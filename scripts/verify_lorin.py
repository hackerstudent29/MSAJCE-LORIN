import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import RAGEngine

async def test_bot():
    load_dotenv()
    print("Initializing Lorin Enterprise Engine (V3)...")
    engine = RAGEngine()
    
    test_queries = ["Hi", "What is the fee for CSE?", "Who is the lead architect?"]
    
    for query in test_queries:
        print(f"\nUSER: {query}")
        print("LORIN: ", end="", flush=True)
        
        full_response = ""
        async for chunk in engine.query_stream(query):
            if isinstance(chunk, str):
                print(chunk, end="", flush=True)
                full_response += chunk
            elif isinstance(chunk, dict) and chunk.get("type") == "telemetry":
                print(f"\n\n📊 [TELEMETRY] Intent: {chunk['intent']}, Provider: {chunk.get('provider', 'N/A')}, Latency: {chunk['latency_ms']}ms")
        
        if not 'full_answer' in locals() or not full_answer:
            print("❌ FAILURE: No response generated.")
        else:
            del full_answer

if __name__ == "__main__":
    asyncio.run(test_bot())
