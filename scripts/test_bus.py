import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

def test_bus_followup():
    engine = RAGEngine()
    
    # Simulate Turn 1: Route AR 8
    history = "User: need ar8 bus full route\nBot: Here is the route for AR-8: 1. Manjambakkam... 19. College."
    
    # Turn 2: Follow up on timings
    query = "timings??"
    
    print(f"\n--- Testing Bus Follow-up: {query} ---")
    answer = engine.query(query, history=history)
    print(f"Lorin: {answer}\n")

if __name__ == "__main__":
    test_bus_followup()
