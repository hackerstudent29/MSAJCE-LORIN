import asyncio
import os
import sys
import json

# Add the project root to sys.path
sys.path.append(os.getcwd())

from core.engine import RAGEngine

async def run_tests():
    engine = RAGEngine()
    
    test_queries = [
        "List all 2024-2028 batch scholarship students",
        "Who are the IT department scholarship recipients?",
        "Who is the principal of MSAJCE?",
        "What are the hostel timings?",
        "Tell me about Ramanathan S",
        "NIRF ranking of MSAJCE",
        "Who runs the college?",
        "How many students got placed in 2023?",
        "Does MSAJCE have a library?",
        "List all clubs and societies"
    ]
    
    print("\n" + "="*50)
    print("LORIN PRODUCTION VERIFICATION SUITE")
    print("="*50 + "\n")
    
    for i, query in enumerate(test_queries, 1):
        print(f"TEST {i}: '{query}'")
        print("-" * 30)
        
        answer = ""
        async for chunk in engine.query_stream(query):
            answer += chunk
            print(chunk, end="", flush=True)
            
        print("\n\n" + "-"*30 + "\n")

if __name__ == "__main__":
    asyncio.run(run_tests())
