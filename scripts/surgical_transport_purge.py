import os
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

# CONFIG
INDEX_NAMES = ["final-secret-rag", "claude-md-files"]
# Old transport chunks IDs identified in original msajce_transport.md
OLD_IDS = [
    "msajce_page_04_chunk_01", "msajce_page_04_chunk_02", "msajce_page_04_chunk_03",
    "msajce_page_04_chunk_04", "msajce_page_04_chunk_05", "msajce_page_04_chunk_06",
    "msajce_page_04_chunk_07", "msajce_page_04_chunk_08", "msajce_page_04_chunk_09",
    "msajce_page_04_chunk_10", "msajce_page_04_chunk_11", "msajce_page_04_chunk_12"
]

def purge_old_transport():
    print("🧹 Starting Surgical Purge of old transport chunks...")
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    
    for idx_name in INDEX_NAMES:
        print(f"📡 Cleaning index: {idx_name}...")
        try:
            index = pc.Index(idx_name)
            # Pinecone allows deleting by ID
            index.delete(ids=OLD_IDS)
            print(f"✅ Deleted old transport IDs from {idx_name}")
        except Exception as e:
            print(f"❌ Error cleaning {idx_name}: {e}")

if __name__ == "__main__":
    purge_old_transport()
