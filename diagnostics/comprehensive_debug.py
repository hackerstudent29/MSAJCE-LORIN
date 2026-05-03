from core.engine import RAGEngine
import os
from dotenv import load_dotenv

load_dotenv()

def debug_query(query_text):
    print(f"\n=== DEBUGGING QUERY: {query_text} ===")
    engine = RAGEngine()
    
    # 1. Pre-Processor Check
    print("Step 1: Pre-Processor")
    category, search_query, complexity = engine.unified_pre_process(query_text, "", engine.langfuse.trace(name="Debug"))
    print(f"  Category: {category} | Search Query: {search_query}")
    
    # 2. Retrieval Check
    print("Step 2: Retrieval")
    relevant_chunks, max_score = engine.get_context_v41(search_query, "SIMPLE", engine.langfuse.trace(name="Debug"))
    print(f"  Num Results: {len(relevant_chunks)} | Max Rerank Score: {max_score}")
    
    for i, c in enumerate(relevant_chunks):
        print(f"  Hit {i+1}: {c['filename']} | Chunk: {c['chunk_id']} | Score: {max_score if i==0 else 'N/A'}")
        print(f"    Snippet: {c['text'][:150]}...")

if __name__ == "__main__":
    debug_query("who is usha")
    debug_query("What is the higher education committee?")
