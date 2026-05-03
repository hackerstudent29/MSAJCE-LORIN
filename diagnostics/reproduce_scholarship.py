import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Add project root to path
sys.path.append(os.getcwd())

from core.engine import RAGEngine

engine = RAGEngine()
query = "how much money alumni contributed for scholarships and how many 2nd year IT students received these scholarships?? list their names here"

print(f"--- TESTING QUERY: {query} ---")
# Manually run parts to see context
trace = engine.langfuse.trace(name="Repro Debug")
relevant_chunks, max_score = engine.get_context_v41("alumni scholarship contributions 2nd year IT students names", query, "SIMPLE", trace)
context_text = "\n\n".join([f"[Source {i+1}]: {c['text']}" for i, c in enumerate(relevant_chunks)])
print(f"CONTEXT RETRIEVED:\n{context_text}\n")
confidence, answer = engine.generate_balanced(query, context_text, trace)
print(f"ANSWER:\n{answer}")
