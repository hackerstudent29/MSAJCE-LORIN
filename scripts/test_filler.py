import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

def test_filler_query():
    engine = RAGEngine()
    
    # Simulate turn 1
    history = "User: how many clubs are there??\nBot: There are 10 clubs under the ENVISTA umbrella."
    
    # Turn 2 with filler
    query = "oh thats nice, list all clubs with one line summary"
    
    print(f"\n--- Testing Query with Filler: {query} ---")
    answer = engine.query(query, history=history)
    print(f"Lorin: {answer}\n")

if __name__ == "__main__":
    test_filler_query()
