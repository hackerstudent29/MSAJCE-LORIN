import json
import asyncio
import re
import os
import hashlib
from collections import defaultdict

# ── Constants (Master Rule Section 2B) ───────────────────────────────────────
MIN_TOKENS = 80       # Skip regular facts below this
MAX_TOKENS = 450      # Split above this
LIST_MIN_TOKENS = 10  # VIP retention for group_list chunks

def sanitize_id(text):
    """Keeps only alphanumeric and underscores for Pinecone compatibility."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', text.replace(' ', '_'))[:80]

def estimate_tokens(text):
    """Fast token estimate: word count * 1.3"""
    return int(len(text.split()) * 1.3)

def split_at_sentence(text, max_tokens):
    """Split a long text into two halves at the nearest sentence boundary."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    first, second = [], []
    count = 0
    target = max_tokens // 2
    for s in sentences:
        tok = estimate_tokens(s)
        if count < target or not second:
            first.append(s)
            count += tok
        else:
            second.append(s)
    return ' '.join(first).strip(), ' '.join(second).strip()

def get_text_hash(text):
    """Generate SHA-256 hash for deduplication."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

class MasterIngestor:
    def __init__(self):
        self.data_dir = "data"
        self.json_dir = os.path.join(self.data_dir, "jsons")
        self.unified_knowledge = []

    async def run(self):
        print("Lorin Master Ingestion: Starting from scratch...")

        # 1. Load Data
        self._load_all_jsons()
        self._load_txt_profile()

        # 2. Deduplication (Master Rule Section 4A)
        self._deduplicate()

        # 3. Save Source of Truth
        output_path = os.path.join(self.data_dir, "unified_master_chunks.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.unified_knowledge, f, indent=2, ensure_ascii=False)

        print(f"DONE: Created {len(self.unified_knowledge)} diamond-grade chunks at {output_path}")

    def _load_all_jsons(self):
        files = sorted([f for f in os.listdir(self.json_dir) if f.endswith('.json')])
        print(f"PROGRESS: Reading {len(files)} JSON source files...")

        for file in files:
            # Skip duplicates and stale files (Master Rule Section 2A)
            if file.endswith("_v2.json") or file == "unified_chunks.json":
                continue

            path = os.path.join(self.json_dir, file)
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Special format: master_stats
            if "master_stats" in data:
                stats = data["master_stats"]
                lines = ["MASTER INSTITUTIONAL STATISTICS — GROUND TRUTH\n"]
                for key, val in stats.items():
                    lines.append(f"SECTION: {key.replace('_', ' ').upper()}")
                    if isinstance(val, dict):
                        for k2, v2 in val.items():
                            lines.append(f"  - {k2.replace('_', ' ').title()}: {v2}")
                    lines.append("")
                text = "\n".join(lines)
                self.unified_knowledge.append({
                    "chunk_id": "AAA_MASTER_STATS_GROUND_TRUTH",
                    "text": text,
                    "embed_text": text,
                    "chunk_type": "fact",
                    "metadata": {
                        "chunk_id": "AAA_MASTER_STATS_GROUND_TRUTH",
                        "source_file": file,
                        "section": "Master Stats",
                        "text": text,
                        "chunk_type": "fact",
                        "keywords": ["stats", "numbers", "counts"],
                        "token_count": estimate_tokens(text)
                    }
                })
                continue

            raw_chunks = data.get("chunks", [])
            source_name = file

            for chunk in raw_chunks:
                text = chunk.get("text", "").strip()
                if not text: continue

                chunk_type = chunk.get("chunk_type", "fact")
                token_count = estimate_tokens(text)

                # Skip Threshold (Master Rule Section 2B)
                min_threshold = LIST_MIN_TOKENS if chunk_type == "group_list" else MIN_TOKENS
                if token_count < min_threshold:
                    continue

                # Standard fields
                chunk_id = chunk.get("chunk_id") or sanitize_id(f"{source_name}_{chunk.get('section','')[:30]}")
                pq_list = chunk.get("possible_questions", [])
                kw_list = chunk.get("keywords", [])
                
                # Enriched Embed Text (Master Rule Section 2B Step 3)
                embed_text = f"{text} {' '.join(pq_list)} {' '.join(kw_list)}".strip()

                def create_final_chunk(cid, ctext, cetext):
                    return {
                        "chunk_id": cid,
                        "text": ctext,
                        "embed_text": cetext,
                        "metadata": {
                            "chunk_id": cid,
                            "source_file": source_name,
                            "section": chunk.get("section", "General"),
                            "text": ctext,
                            "chunk_type": chunk_type,
                            "keywords": kw_list,
                            "token_count": estimate_tokens(ctext)
                        }
                    }

                # Split Rule (Master Rule Section 2B)
                if token_count > MAX_TOKENS:
                    part_a, part_b = split_at_sentence(text, MAX_TOKENS)
                    if part_a: self.unified_knowledge.append(create_final_chunk(chunk_id+"_a", part_a, f"{part_a} {' '.join(pq_list)}"))
                    if part_b: self.unified_knowledge.append(create_final_chunk(chunk_id+"_b", part_b, f"{part_b} {' '.join(pq_list)}"))
                else:
                    self.unified_knowledge.append(create_final_chunk(chunk_id, text, embed_text))

    def _load_txt_profile(self):
        profile_path = os.path.join(self.data_dir, "ramanathan_profile.txt")
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8') as f:
                text = f.read().strip()
                self.unified_knowledge.append({
                    "chunk_id": "PROFILE_RAMANATHAN_S",
                    "text": text,
                    "embed_text": text,
                    "metadata": {
                        "chunk_id": "PROFILE_RAMANATHAN_S",
                        "source_file": "ramanathan_profile.txt",
                        "section": "Developer Bio",
                        "text": text,
                        "chunk_type": "profile",
                        "keywords": ["ramanathan", "ram", "developer", "architect"],
                        "token_count": estimate_tokens(text)
                    }
                })

    def _deduplicate(self):
        seen = set()
        clean = []
        for c in self.unified_knowledge:
            thash = get_text_hash(c["text"])
            if thash not in seen:
                clean.append(c)
                seen.add(thash)
        self.unified_knowledge = clean

if __name__ == "__main__":
    ingestor = MasterIngestor()
    asyncio.run(ingestor.run())
