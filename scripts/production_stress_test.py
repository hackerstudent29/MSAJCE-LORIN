import asyncio
import os
import logging
from core.engine import RAGEngine
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.WARNING, format='%(message)s')

async def stress_test():
    engine = RAGEngine()
    queries = [
        "what stops does AR8 cover",      # Should be ROUTE_QUERY
        "who is the CSE HOD",             # Different dept same pattern
        "can girls go out of hostel",     # RULE_QUERY with informal phrasing  
        "fees for first year",            # FACT_QUERY
        "yenna pannalam college la",      # Tamil-English mixed query (Tanglish)
    ]
    
    print("\n" + "="*80)
    print("LORIN PRODUCTION STRESS TEST — 5 EDGE CASES")
    print("="*80 + "\n")
    
    for i, q in enumerate(queries, 1):
        print(f"[{i}] QUERY: {q}")
        print("-" * 40)
        
        full_answer = ""
        async for chunk in engine.query_stream(q):
            if isinstance(chunk, str):
                full_answer += chunk
        
        print(f"ANSWER: {full_answer[:800]}...") 
        print("\n" + "."*40 + "\n")

if __name__ == "__main__":
    asyncio.run(stress_test())
