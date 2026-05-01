import asyncio
import os
import sys

# Add project root to sys.path
sys.path.append(os.getcwd())

from core.engine import RAGEngine

async def test_lorin():
    print("Initializing Master Engine...")
    engine = RAGEngine()
    
    # Test queries
    queries = [
        "Who is Dr. Weslin D?",
        "Tell me about the Principal.",
        "What are the research areas in IT department?"
    ]
    
    for query in queries:
        print(f"\n--- TESTING QUERY: {query} ---")
        answer = await engine.query(query)
        print(f"LORIN RESPONSE:\n{answer}")
        print("-" * 30)

if __name__ == "__main__":
    asyncio.run(test_lorin())
