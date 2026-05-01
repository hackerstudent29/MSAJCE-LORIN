import json
import asyncio
import re
import os
import httpx
from datetime import datetime
from collections import defaultdict

def sanitize_id(text):
    """Keeps only alphanumeric and underscores for Pinecone compatibility."""
    return re.sub(r'[^a-zA-Z0-9_]', '', text.replace(' ', '_'))

class MasterIngestor:
    def __init__(self):
        self.data_dir = "data"
        self.json_dir = os.path.join(self.data_dir, "jsons")
        self.entities = defaultdict(list)
        self.categories = defaultdict(list)
        self.unified_knowledge = []
        
        # OpenRouter config for enrichment
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.embed_url = "https://openrouter.ai/api/v1/embeddings"
        self.embedding_model = "openai/text-embedding-3-small"

    async def run(self):
        print("Lorin Master Ingestion: Starting from scratch...")
        
        # 1. Load all structured data
        self._load_all_jsons()
        
        # 2. Entity Resolution & Merging
        self._merge_entities()
        
        # 3. Create High-Fidelity Chunks
        self._create_unified_chunks()
        
        # 4. Final Validation & Deduplication
        self._deduplicate()
        
        # 5. Save the 'Source of Truth'
        output_path = os.path.join(self.data_dir, "unified_master_chunks.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.unified_knowledge, f, indent=2)
            
        print(f"DONE: Created {len(self.unified_knowledge)} diamond-grade chunks at {output_path}")

    def _load_all_jsons(self):
        files = [f for f in os.listdir(self.json_dir) if f.endswith('.json')]
        for file in files:
            path = os.path.join(self.json_dir, file)
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                chunks = data.get('chunks', [])
                for chunk in chunks:
                    text = chunk.get('text', '')
                    category = chunk.get('section', 'General')
                    
                    # Store by category
                    self.categories[category].append(text)
                    
                    # Extract entities mentioned in chunk metadata
                    persons = chunk.get('entities', {}).get('persons', [])
                    for p in persons:
                        # Clean name (e.g., "Dr. WESLIN D — Associate Professor" -> "Dr. WESLIN D")
                        name = p.split(' — ')[0].strip()
                        self.entities[name].append({
                            "source": file,
                            "context": chunk.get('context'),
                            "text": text,
                            "role": p.split(' — ')[1] if ' — ' in p else None
                        })

    def _merge_entities(self):
        """Fuses data from multiple sources for the same entity."""
        print(f"PROGRESS: Fusing {len(self.entities)} unique entities...")
        for name, records in self.entities.items():
            # Build a unified profile
            profile_text = f"ENTITY PROFILE: {name}\n"
            roles = set(r['role'] for r in records if r['role'])
            if roles:
                profile_text += f"Roles/Designations: {', '.join(roles)}\n\n"
            
            # Group unique facts
            unique_contexts = set()
            for r in records:
                # Add context but avoid massive repetition
                if r['context'] not in unique_contexts:
                    profile_text += f"--- {r['context']} ---\n{r['text']}\n\n"
                    unique_contexts.add(r['context'])
            
            self.unified_knowledge.append({
                "chunk_id": sanitize_id(f"entity_{name}"),
                "entity_name": name,
                "text": profile_text,
                "metadata": {
                    "type": "PERSON_PROFILE",
                    "sources": list(set(r['source'] for r in records))
                }
            })

    def _create_unified_chunks(self):
        """Processes remaining categorical data not tied to specific persons."""
        print("PROGRESS: Processing Departmental and Administrative knowledge...")
        for cat, texts in self.categories.items():
            combined_text = f"CATEGORY: {cat}\n\n" + "\n\n".join(set(texts))
            # If text is too long, we would chunk here, but for now we keep it unified
            self.unified_knowledge.append({
                "chunk_id": sanitize_id(f"cat_{cat[:20]}"),
                "section": cat,
                "text": combined_text,
                "metadata": {"type": "CATEGORY_DATA"}
            })

    def _deduplicate(self):
        """Ensures no identical text blocks are stored."""
        seen = set()
        clean_knowledge = []
        for c in self.unified_knowledge:
            text_hash = hash(c['text'][:500]) # Quick hash check
            if text_hash not in seen:
                clean_knowledge.append(c)
                seen.add(text_hash)
        self.unified_knowledge = clean_knowledge

if __name__ == "__main__":
    ingestor = MasterIngestor()
    asyncio.run(ingestor.run())
