import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

async def test_bus_followup():
    engine = RAGEngine()
    
    # Simulate Turn 1: Route AR 8
    history = "User: need ar8 bus full route\nBot: Here is the route for AR-8: 1. Manjambakkam... 19. College."
    
    # Turn 2: Follow up on timings
    query = "timings??"
    
    print(f"\n--- Testing Bus Follow-up: {query} ---")
    
    answer = ""
    async for chunk in engine.query_stream(query, history=history):
        if isinstance(chunk, dict):
            print(f"\n[Telemetry]: {chunk}")
            continue
        answer += chunk
        print(chunk, end="", flush=True)
    
    print(f"\n\nFull Answer: {answer}\n")

if __name__ == "__main__":
    asyncio.run(test_bus_followup())
