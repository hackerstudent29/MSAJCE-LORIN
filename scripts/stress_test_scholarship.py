import os
import asyncio
from core.engine import RAGEngine
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def stress_test():
    print("INITIALIZING SCHOLARSHIP STRESS TEST...")
    engine = RAGEngine()
    
    query = "how many students got scholarships, provided by alumni ??"
    print(f"\nQUERYING: {query}")
    
    response = await engine.query(query)
    
    print("\n" + "="*50)
    print("LORIN RESPONSE:")
    print("="*50)
    print(response)
    print("="*50)

if __name__ == "__main__":
    asyncio.run(stress_test())
