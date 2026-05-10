import asyncio
import os
import logging
from core.engine import RAGEngine
from dotenv import load_dotenv

load_dotenv()

# Configure logging to see the WARNING level diagnostics we added
logging.basicConfig(level=logging.WARNING, format='%(message)s')

async def test_queries():
    engine = RAGEngine()
    queries = [
        "Who is Yogesh?",
        "Tell me about Bus AR8 route",
        "Who is the principal?",
        "What are the hostel outing rules?",
        "What are the documents required for admission?",
        "Who built you?",
        "Tell me about the IT department",
        "Is there a 10% discount for female students?",
        "Who is the IT HOD?",
        "What is the college code?"
    ]
    
    print("\n" + "="*80)
    print("LORIN RAG HARDENING AUDIT — 10 TEST QUERIES")
    print("="*80 + "\n")
    
    for i, q in enumerate(queries, 1):
        print(f"[{i}] QUERY: {q}")
        print("-" * 40)
        
        full_answer = ""
        async for chunk in engine.query_stream(q):
            if isinstance(chunk, str):
                full_answer += chunk
        
        print(f"ANSWER: {full_answer[:500]}...") # Truncated for brevity
        print("\n" + "."*40 + "\n")

if __name__ == "__main__":
    asyncio.run(test_queries())
