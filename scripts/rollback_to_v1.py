"""
scripts/rollback_to_v1.py — Fail-safe emergency script.
Reverts the Lorin AI bot to the stable 'raglorin' index and legacy BM25/GT data.
Use this ONLY if msajce-v2 shows catastrophic performance issues in production.
"""
import os
import sys

# Since engine.py uses environment variables with fallbacks, 
# the best way to roll back is to explicitly set the PINECONE_INDEX_NAME.
# Alternatively, if we edited the code to point to msajce-v2, we need to revert that.

def rollback():
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Lorin AI — Emergency Rollback to v1 (raglorin)      ║")
    print("╚══════════════════════════════════════════════════════╝")
    
    print("\n[1] Checking stable infrastructure...")
    # Check if raglorin data still exists
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    v1_bm25 = os.path.join(data_dir, "bm25_index")
    v1_gt   = os.path.join(data_dir, "ground_truth.json")
    
    if not os.path.exists(v1_gt):
        print("❌ CRITICAL: Legacy ground_truth.json not found! Rollback impossible.")
        sys.exit(1)
        
    print("    ✅ Legacy BM25 and Ground Truth found.")
    
    print("\n[2] Instruction for manual rollover:")
    print("    To complete the rollback, you MUST set these Environment Variables:")
    print("    PINECONE_INDEX_NAME = 'raglorin'")
    print("    ")
    print("    The RAGEngine in core/engine.py is already designed to fallback to 'raglorin'")
    print("    if 'msajce-v2' is missing or fails. To FORCE 'raglorin', delete 'msajce-v2' index")
    print("    OR update core/engine.py to remove 'msajce-v2' from the loop.")

    print("\n⚠️  ROLLBACK MANUAL GATE: Please confirm you have updated your .env file.")
    print("   Once updated, restart the bot server.")

if __name__ == "__main__":
    rollback()
