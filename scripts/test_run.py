import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

def test_run():
    engine = RAGEngine()
    
    test_queries = [
        "Which professional societies are active in MSAJCE?",
        "Tell me about the Incubation Centre at the college.",
        "who is yogesj" # Testing fuzzy match / typo handling
    ]
    
    for query in test_queries:
        print(f"\n--- Testing Query: {query} ---")
        answer = engine.query(query)
        print(f"Answer: {answer}\n")

if __name__ == "__main__":
    test_run()
