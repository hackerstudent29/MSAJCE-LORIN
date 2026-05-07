import os
import sys

# Add project root to sys.path
sys.path.append(os.getcwd())

from core.engine import RAGEngine

def main():
    print("Initializing Lorin Engine for BM25 rebuild...")
    engine = RAGEngine()
    
    # Paths
    chunks_path = os.path.join("data", "knowledge_base", "unified_master_chunks.json")
    index_dir = os.path.join("data", "bm25_index")
    
    if not os.path.exists(chunks_path):
        print(f"Error: Could not find {chunks_path}")
        return
        
    print(f"Rebuilding BM25 index from {chunks_path}...")
    engine._rebuild_bm25(chunks_path, index_dir)
    print("LOCAL BM25 REBUILD COMPLETE!")

if __name__ == "__main__":
    main()
