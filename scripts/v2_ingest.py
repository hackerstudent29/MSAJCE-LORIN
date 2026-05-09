"""
v2_ingest.py — Pinecone msajce-v2 ingestion pipeline.
Creates NEW index "msajce-v2". NEVER touches "raglorin".
Embeds super_chunk_text via OpenRouter text-embedding-3-small (1536 dims).
Upserts in batches of 100.
"""
import os, json, glob, time
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
import httpx

load_dotenv()

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKS_DIR = os.path.join(BASE_DIR, "data", "v2_chunks")

PINECONE_API_KEY  = os.getenv("PINECONE_API_KEY")
OPENROUTER_KEY    = os.getenv("OPENROUTER_API_KEY")
NEW_INDEX         = "msajce-v2"
EXISTING_INDEX    = "raglorin"
EMBED_URL         = "https://openrouter.ai/api/v1/embeddings"
EMBED_MODEL       = "openai/text-embedding-3-small"
BATCH_SIZE        = 100

pc = Pinecone(api_key=PINECONE_API_KEY)

def get_embedding(text: str) -> list:
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
    data = {"model": EMBED_MODEL, "input": text[:8000]}  # token cap
    try:
        r = httpx.post(EMBED_URL, headers=headers, json=data, timeout=60)
        r.raise_for_status()
        return [float(x) for x in r.json()["data"][0]["embedding"]]
    except Exception as e:
        print(f"    [EMBED ERROR] {e}")
        return None

def build_metadata(chunk: dict) -> dict:
    """Build full Pinecone metadata payload from a v2 chunk."""
    entities = chunk.get("entities", {})
    if not isinstance(entities, dict): entities = {}

    return {
        # Core identifiers
        "chunk_id":     chunk.get("chunk_id",""),
        "node_type":    chunk.get("node_type","TOPIC"),
        "chunk_type":   chunk.get("chunk_type","paragraph"),
        "priority":     chunk.get("priority","medium"),
        "page_title":   chunk.get("page_title",""),
        "department":   chunk.get("department","General"),
        "section":      chunk.get("section",""),
        # Parent-child
        "is_parent":    str(chunk.get("is_parent", False)),
        "parent_id":    chunk.get("parent_id",""),
        "child_ids":    json.dumps(chunk.get("child_ids",[])),
        # Content (LLM reads this)
        "text":         chunk.get("text","")[:4000],  # Pinecone metadata limit
        "context":      chunk.get("context","")[:500],
        "keywords":     ", ".join(chunk.get("keywords",[]))[:500],
        # Source tracing
        "source_files": ", ".join(chunk.get("source_files",[])),
        "source_types": ", ".join(chunk.get("source_types",[])),
        "academic_year":chunk.get("academic_year","2025-26"),
        "is_active":    str(chunk.get("is_active", True)),
        "last_updated": time.strftime("%Y-%m-%d"),
        "version":      chunk.get("version","v2"),
        # Flattened entities (backwards compatible with raglorin format)
        "entity_name":    str(entities.get("name","")),
        "entity_role":    str(entities.get("role","")),
        "entity_dept":    str(entities.get("department","")),
        "entity_email":   str(entities.get("email","")),
        "entity_phone":   str(entities.get("phone","")),
        "entity_bus_no":  str(entities.get("bus_no","")),
        "entity_route":   ", ".join(entities.get("route",[])) if isinstance(entities.get("route",[]),list) else str(entities.get("route","")),
        "entity_club":    str(entities.get("club","")),
        "entity_company": str(entities.get("company","")),
        "entity_package": str(entities.get("package","")),
    }

def upsert_batch(index, vectors: list):
    """Upsert a batch of vectors with retry."""
    for attempt in range(3):
        try:
            index.upsert(vectors=vectors)
            return True
        except Exception as e:
            print(f"    [UPSERT ERROR attempt {attempt+1}] {e}")
            time.sleep(2 ** attempt)
    return False

def verify_raglorin_untouched():
    """Safety check — verify raglorin is untouched before and after."""
    try:
        stats = pc.Index(EXISTING_INDEX).describe_index_stats()
        return stats.total_vector_count
    except:
        return -1

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Lorin AI v2 — Pinecone Ingestion Pipeline           ║")
    print("╚══════════════════════════════════════════════════════╝")

    # Safety check: record raglorin vector count before we start
    raglorin_before = verify_raglorin_untouched()
    print(f"\n🔒 raglorin index BEFORE: {raglorin_before} vectors (must be same after)")

    # Create new msajce-v2 index
    existing_indexes = pc.list_indexes().names()

    if NEW_INDEX in existing_indexes:
        print(f"\n⚠️  Index '{NEW_INDEX}' already exists. Clearing it...")
        pc.Index(NEW_INDEX).delete(delete_all=True)
        time.sleep(3)
    else:
        print(f"\n[1] Creating new index '{NEW_INDEX}'...")
        pc.create_index(
            name=NEW_INDEX,
            dimension=1536,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
        print(f"    Waiting for index to be ready...")
        while not pc.describe_index(NEW_INDEX).status["ready"]:
            time.sleep(2)
        print(f"    ✅ '{NEW_INDEX}' ready")

    index = pc.Index(NEW_INDEX)

    # Load all v2 chunk files
    chunk_files = glob.glob(os.path.join(CHUNKS_DIR, "*.json"))
    print(f"\n[2] Loading chunk files from data/v2_chunks/... ({len(chunk_files)} files)")

    total_vectors = 0
    total_failed  = 0
    file_summaries = []

    for chunk_file in chunk_files:
        file_name = os.path.basename(chunk_file)
        with open(chunk_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        chunks = data.get("chunks", []) if isinstance(data, dict) else data
        if not chunks:
            print(f"    ⚠️  {file_name} — no chunks, skipping")
            continue

        vectors = []
        failed  = 0

        for chunk in chunks:
            # Use super_chunk_text for embedding; fallback to text
            embed_text = chunk.get("super_chunk_text") or chunk.get("text","")
            if not embed_text or len(embed_text.strip()) < 10:
                failed += 1; continue

            embedding = get_embedding(embed_text)
            if not embedding:
                failed += 1; continue

            metadata = build_metadata(chunk)
            vectors.append({
                "id":       chunk["chunk_id"],
                "values":   embedding,
                "metadata": metadata
            })

            # Upsert in batches of BATCH_SIZE
            if len(vectors) >= BATCH_SIZE:
                upsert_batch(index, vectors)
                total_vectors += len(vectors)
                vectors = []
                time.sleep(0.5)  # rate limiting

        # Upsert remaining
        if vectors:
            upsert_batch(index, vectors)
            total_vectors += len(vectors)

        file_count = len(chunks) - failed
        total_failed += failed
        file_summaries.append((file_name, file_count, failed))
        print(f"    ✅ {file_name} → {file_count} chunks → {file_count} vectors" +
              (f" ({failed} failed)" if failed else ""))

    # Final safety check
    raglorin_after = verify_raglorin_untouched()

    print(f"\n{'='*60}")
    print(f"INGESTION COMPLETE")
    print(f"  Total vectors in msajce-v2 : {total_vectors}")
    print(f"  Failed embeddings          : {total_failed}")
    print(f"  raglorin BEFORE            : {raglorin_before}")
    print(f"  raglorin AFTER             : {raglorin_after}")
    if raglorin_before == raglorin_after:
        print(f"  raglorin status            : UNTOUCHED ✅")
    else:
        print(f"  raglorin status            : ⚠️  MISMATCH — INVESTIGATE IMMEDIATELY")
