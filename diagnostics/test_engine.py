import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

def test():
    engine = RAGEngine()
    print("RAGEngine initialized.")
    
    query = "need contact number of velu driver"
    print(f"\nQuery: '{query}'")
    try:
        res = engine.query(query)
        print(f"Answer:\n{res}\n")
    except Exception as e:
        import traceback
        print(f"ERROR: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test()
