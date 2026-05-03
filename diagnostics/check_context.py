import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Add project root to path
sys.path.append(os.getcwd())

from core.engine import RAGEngine

engine = RAGEngine()
query = "how many it students of 2024-2028 batch received the scholarships"
search_query = "alumni scholarship beneficiaries 2024-2028 IT students names"

trace = engine.langfuse.trace(name="Context Check")
relevant_chunks, max_score = engine.get_context_v41(search_query, query, "SIMPLE", trace)
print(f"NUM CHUNKS: {len(relevant_chunks)}")
for i, c in enumerate(relevant_chunks):
    print(f"--- SOURCE {i+1} (ID: {c['chunk_id']}) ---")
    print(c['text'][:500])
    print("...")
