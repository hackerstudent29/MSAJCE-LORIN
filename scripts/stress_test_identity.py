import os
import asyncio
from core.engine import RAGEngine
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def identity_test():
    print("INITIALIZING IDENTITY STRESS TEST...")
    engine = RAGEngine()
    
    queries = [
        "who is ram",
        "tell me more abt him",
        "who is srinivasan"
    ]
    
    history = ""
    for q in queries:
        print(f"\nQUERYING: {q}")
        response = ""
        async for chunk in engine.query_stream(q, history=history):
            response += chunk
        
        print("\n" + "="*50)
        print(f"LORIN RESPONSE to '{q}':")
        print("="*50)
        print(response)
        print("="*50)
        history += f"User: {q}\nBot: {response}\n"

if __name__ == "__main__":
    asyncio.run(identity_test())
