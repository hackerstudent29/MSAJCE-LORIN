"""
v2_rebuild_bm25.py — Rebuild BM25 index at data/bm25_index_v2/
Indexes on chunk["text"] + chunk["keywords"] for exact name/number matching.
"""
import os, json, glob
import bm25s, Stemmer

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKS_DIR = os.path.join(BASE_DIR, "data", "v2_chunks")
OUT_DIR    = os.path.join(BASE_DIR, "data", "bm25_index_v2"); os.makedirs(OUT_DIR, exist_ok=True)

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Lorin AI v2 — BM25 Index Rebuild                    ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    all_corpus_texts = []
    all_metadata     = []

    chunk_files = glob.glob(os.path.join(CHUNKS_DIR, "*.json"))
    print(f"Loading {len(chunk_files)} chunk files...")

    for jpath in chunk_files:
        with open(jpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        chunks = data.get("chunks", []) if isinstance(data, dict) else data

        for chunk in chunks:
            text     = chunk.get("text", "")
            keywords = " ".join(chunk.get("keywords", []))
            # BM25 indexes on text + keywords for full coverage
            bm25_text = f"{text} {keywords}".strip()
            if not bm25_text: continue

            all_corpus_texts.append(bm25_text)
            # Slim metadata for BM25 corpus (avoid huge memory footprint)
            all_metadata.append({
                "chunk_id":   chunk.get("chunk_id",""),
                "chunk_type": chunk.get("chunk_type","paragraph"),
                "section":    chunk.get("section",""),
                "department": chunk.get("department","General"),
                "priority":   chunk.get("priority","medium"),
                "page_title": chunk.get("page_title",""),
                "text":       text[:2000],  # limit stored text
                "entity_name":  str(chunk.get("entities",{}).get("name","")),
                "entity_role":  str(chunk.get("entities",{}).get("role","")),
                "entity_bus_no":str(chunk.get("entities",{}).get("bus_no","")),
            })

    print(f"  Total corpus documents : {len(all_corpus_texts)}")
    print(f"  Building BM25 index...")

    stemmer = Stemmer.Stemmer("english")
    corpus_tokens = bm25s.tokenize(all_corpus_texts, stemmer=stemmer)

    retriever = bm25s.BM25()
    retriever.index(corpus_tokens)
    retriever.save(OUT_DIR, corpus=all_metadata)

    print(f"\n✅ BM25 v2 index saved → data/bm25_index_v2/")
    print(f"   Documents indexed : {len(all_corpus_texts)}")
    print(f"   Catches exact matches for:")
    print(f"     - Names: 'Weslin', 'Srinivasan'")
    print(f"     - Bus numbers: '102', '570', 'AR8'")
    print(f"     - Packages: '12 LPA', '6 LPA'")
    print(f"     - Events: 'Sathak Thiruvizha', 'HABIBI'")
