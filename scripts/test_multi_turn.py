import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

def test_multi_turn():
    engine = RAGEngine()
    
    print("\n--- [TURN 1] ---")
    q1 = "who is usha"
    a1 = engine.query(q1)
    print(f"User: {q1}\nLorin: {a1}")
    
    # Simulate history
    history = f"User: {q1}\nBot: {a1}"
    
    print("\n--- [TURN 2] ---")
    q2 = "member of which team ??"
    a2 = engine.query(q2, history=history)
    print(f"User: {q2}\nLorin: {a2}")

if __name__ == "__main__":
    test_multi_turn()
