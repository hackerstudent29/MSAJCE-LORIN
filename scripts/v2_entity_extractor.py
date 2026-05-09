"""
v2_entity_extractor.py — Cross-file entity registry builder.
Scans ALL engineered MD sections for HODs, Principal, Wardens, Club Office Bearers,
Placement Officers, and any person/entity meeting the threshold rule.
Outputs: data/v2_entity_registry.json
"""
import os, json, re, glob
from dotenv import load_dotenv
import httpx

load_dotenv()

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_ENG    = os.path.join(BASE_DIR, "data", "v2_engineered_md")
KB_DIR    = os.path.join(BASE_DIR, "data", "v2_extended_jsons")
PDF_SUPP  = os.path.join(BASE_DIR, "data", "v2_pdf_supplements")
OUT_PATH  = os.path.join(BASE_DIR, "data", "v2_entity_registry.json")

VERCEL_URL = "https://ai-gateway.vercel.sh/v1/chat/completions"
VERCEL_KEY = os.getenv("VERCEL_AI_KEY_5") or os.getenv("OPENROUTER_API_KEY")
GEN_MODEL  = "google/gemini-2.0-flash-001"

# ─── Priority entity targets (must always be extracted) ───────────────────────
PRIORITY_ROLES = [
    "principal", "hod", "head of department", "warden", "placement officer",
    "tpo", "training and placement", "chief librarian", "librarian",
    "transport coordinator", "nss coordinator", "yrc coordinator",
    "iqac director", "iqac coordinator", "anti-ragging",
    "president", "secretary", "treasurer", "vice president",
    "club coordinator", "society coordinator", "office bearer",
    "iic president", "incubation", "research coordinator"
]

def llm_call(prompt: str, max_tokens: int = 3000) -> str:
    headers = {"Authorization": f"Bearer {VERCEL_KEY}", "Content-Type": "application/json"}
    data = {"model": GEN_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
    try:
        r = httpx.post(VERCEL_URL, headers=headers, json=data, timeout=120)
        content = r.json()["choices"][0]["message"]["content"]
        # Extract JSON from response
        m = re.search(r'\{.*\}|\[.*\]', content, re.DOTALL)
        return m.group(0) if m else content
    except Exception as e:
        print(f"    [LLM ERROR] {e}")
        return "[]"

# ─── Collect all text from all sources ───────────────────────────────────────
def collect_all_text() -> dict:
    """Returns {source_file: full_text} for all engineered sources."""
    sources = {}

    # MD engineered sections
    for jpath in glob.glob(os.path.join(MD_ENG, "*.json")):
        base = os.path.basename(jpath)
        with open(jpath) as f:
            data = json.load(f)
        text = "\n\n".join(s.get("text","") for s in data.get("sections", []))
        sources[base.replace(".json", ".md")] = text

    # Extended JSON chunks
    for jpath in glob.glob(os.path.join(KB_DIR, "*.json")):
        base = os.path.basename(jpath)
        with open(jpath) as f:
            data = json.load(f)
        chunks = data.get("chunks", []) if isinstance(data, dict) else data
        text = "\n\n".join(c.get("text","") for c in chunks)
        sources[f"kb/{base}"] = text

    # PDF supplements
    for jpath in glob.glob(os.path.join(PDF_SUPP, "*.json")):
        base = os.path.basename(jpath)
        with open(jpath) as f:
            data = json.load(f)
        text = "\n\n".join(data.get("exclusive_sections", []))
        if text.strip():
            sources[f"pdf/{base}"] = text

    return sources

# ─── Entity extraction per source ─────────────────────────────────────────────
def extract_entities_from_text(text: str, source_file: str) -> list:
    """Use LLM to extract named entities with roles from a block of text."""
    prompt = (
        "You are a Named Entity Extractor for an institutional knowledge base.\n"
        f"Source: '{source_file}'\n\n"
        "Extract ALL people with institutional roles from the text below.\n"
        "For each person, return a JSON array of objects with these fields:\n"
        "  name, role, department, email (or empty), phone (or empty), "
        "specialization (or empty), batch (if student), source_mention (1 sentence quote)\n\n"
        "ONLY include people with CLEAR institutional roles (HOD, Principal, Warden, "
        "Coordinator, Officer, Club Bearer, etc.).\n"
        "Do NOT include students mentioned in passing.\n"
        "Return ONLY a valid JSON array. No explanations.\n\n"
        f"TEXT:\n{text[:6000]}"
    )
    raw = llm_call(prompt)
    try:
        return json.loads(raw) if raw.strip().startswith("[") else []
    except:
        return []

# ─── Entity merging ───────────────────────────────────────────────────────────
def normalize_name(name: str) -> str:
    """Normalize name for deduplication."""
    return re.sub(r'\s+', ' ', name.lower().strip().replace("dr.", "dr").replace("mr.", "mr").replace("mrs.", "mrs"))

def merge_entity_mentions(all_mentions: list) -> dict:
    """Merge all mentions of the same person into one registry entry."""
    registry = {}  # normalized_name -> merged entity dict

    for mention in all_mentions:
        name = mention.get("name", "").strip()
        if not name or len(name) < 3: continue
        norm = normalize_name(name)

        if norm not in registry:
            registry[norm] = {
                "canonical_name": name,
                "role": mention.get("role", ""),
                "department": mention.get("department", ""),
                "email": mention.get("email", ""),
                "phone": mention.get("phone", ""),
                "specialization": mention.get("specialization", ""),
                "batch": mention.get("batch", ""),
                "mentions": []
            }
        
        entry = registry[norm]
        src = mention.get("_source_file", "")
        stype = "pdf_supplement" if src.startswith("pdf/") else ("knowledge_base_json" if src.startswith("kb/") else "datalab_md")
        
        entry["mentions"].append({
            "name": name,
            "role": mention.get("role", ""),
            "department": mention.get("department", ""),
            "email": mention.get("email", ""),
            "phone": mention.get("phone", ""),
            "specialization": mention.get("specialization", ""),
            "quote": mention.get("source_mention", ""),
            "source_type": stype
        })

    return registry

# ─── Apply Entity Threshold Rule ──────────────────────────────────────────────
SOURCE_PRIORITY = {
    "knowledge_base_json": 3,  # Highest: manually verified
    "datalab_md":          2,  # Middle: structured prose
    "pdf_supplement":      1   # Lowest: OCR risk
}

def merge_entities(registry: dict) -> dict:
    """Apply institutional priority rules to merged entities."""
    final_registry = {}
    for name, data in registry.items():
        mentions = data["mentions"]
        # Sort mentions by source priority (highest first)
        mentions.sort(key=lambda x: SOURCE_PRIORITY.get(x["source_type"], 0), reverse=True)
        
        # Take fields from the highest priority source
        primary = mentions[0]
        merged = {
            "canonical_name": primary["name"],
            "role": primary.get("role"),
            "department": primary.get("department"),
            "email": primary.get("email"),
            "phone": primary.get("phone"),
            "specialization": primary.get("specialization"),
            "source_type": primary["source_type"],
            "mention_count": len(mentions),
            "source_quotes": [m["quote"] for m in mentions if m.get("quote")]
        }
        
        # Fill missing fields from lower priority sources if primary is empty
        for m in mentions[1:]:
            for field in ["role", "department", "email", "phone", "specialization"]:
                if not merged.get(field) and m.get(field):
                    merged[field] = m[field]
        
        final_registry[name] = merged
    return final_registry

def apply_threshold_rule(registry: dict) -> list:
    """Apply the 'Institutional Authority' gate."""
    qualified = []
    
    merged_registry = merge_entities(registry)
    
    for name, entity in merged_registry.items():
        total_text = " ".join(entity["source_quotes"])
        word_count = len(total_text.split())
        role_lower = (entity.get("role") or "").lower()
        is_priority = any(r in role_lower for r in PRIORITY_ROLES)

        if is_priority or entity["mention_count"] >= 2 or word_count >= 150:
            qualified.append(entity)
            
    return qualified

# ─── Build profile chunks ─────────────────────────────────────────────────────
def build_entity_chunk(entity: dict, idx: int) -> dict:
    """Build a production-ready profile chunk from a merged entity."""
    name = entity["canonical_name"]
    role = entity.get("role", "Staff") or "Staff"
    dept = entity.get("department", "General") or "General"
    email = entity.get("email", "")
    phone = entity.get("phone", "")
    spec  = entity.get("specialization", "")

    chunk_id_base = re.sub(r'[^a-z0-9]', '_', name.lower())
    chunk_id = f"person_{chunk_id_base}_{idx:03d}"

    text_parts = [f"{name} serves as {role}"]
    if dept and dept != "General": text_parts[0] += f" in the {dept} department"
    text_parts[0] += " at MSAJCE."
    if spec: text_parts.append(f"Their area of specialization includes {spec}.")
    if phone: text_parts.append(f"They can be reached at {phone}.")
    if email: text_parts.append(f"Email: {email}.")
    for quote in entity.get("source_quotes", [])[:3]:
        if quote and quote not in text_parts:
            text_parts.append(quote)

    text = " ".join(text_parts)

    possible_questions = [
        f"Who is {name}?",
        f"What is the role of {name}?",
    ]
    if "hod" in role.lower() or "head" in role.lower():
        possible_questions += [
            f"Who is the HOD of {dept}?",
            f"Who heads the {dept} department at MSAJCE?",
            f"{dept} department head contact",
        ]
    if email: possible_questions.append(f"What is {name}'s email?")
    if phone: possible_questions.append(f"What is {name}'s phone number?")

    priority = "critical" if any(r in role.lower() for r in ["principal","hod","head of dept","warden","placement officer"]) else "high"

    super_chunk = (
        f"INSTITUTION: MSAJCE\n"
        f"DEPARTMENT: {dept}\n"
        f"SECTION: {role} Profile\n"
        f"ENTITY_TYPE: PERSON\n"
        f"SUMMARY: {name} is the {role} of {dept} at MSAJCE.\n"
        f"QUESTIONS: {' | '.join(possible_questions)}\n"
        f"CONTENT: {text}\n"
        f"KEYWORDS: {name}, {role}, {dept}, {email}, {phone}"
    )

    return {
        "chunk_id": chunk_id,
        "node_type": "PERSON",
        "chunk_type": "profile",
        "priority": priority,
        "page_title": f"{dept} — {role} Profile",
        "department": dept,
        "section": role,
        "is_parent": False,
        "parent_id": "",
        "child_ids": [],
        "language": "en",
        "is_active": True,
        "version": "v2",
        "academic_year": "2025-26",
        "source_files": entity.get("source_files", []),
        "source_types": ["md"] * len(entity.get("source_files", [])),
        "text": text,
        "super_chunk_text": super_chunk,
        "context": f"{name} is the {role} at the {dept} department of MSAJCE.",
        "keywords": [name, role, dept, email, phone],
        "entities": {
            "name": name, "role": role, "department": dept,
            "email": email, "phone": phone, "specialization": spec
        },
        "possible_questions": possible_questions,
        "edges": [{"relation": "WORKS_IN", "target": f"dept_{dept.lower().replace(' ','_')}", "weight": 1.0}]
    }

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Lorin AI v2 — Cross-File Entity Extractor           ║")
    print("╚══════════════════════════════════════════════════════╝")

    print("\n[1] Collecting all source text...")
    sources = collect_all_text()
    print(f"    Loaded {len(sources)} source files")

    print("\n[2] Extracting entities from each source...")
    all_mentions = []
    for source_file, text in sources.items():
        if len(text.strip()) < 100: continue
        print(f"    Scanning {source_file}...")
        mentions = extract_entities_from_text(text, source_file)
        for m in mentions:
            m["_source_file"] = source_file
        all_mentions.extend(mentions)
        print(f"      → {len(mentions)} entities found")

    print(f"\n[3] Total raw mentions: {len(all_mentions)}")
    print("[4] Merging cross-file mentions...")
    registry = merge_entity_mentions(all_mentions)

    print("[5] Applying Entity Threshold Rule...")
    qualified = apply_threshold_rule(registry)

    print("[6] Building entity profile chunks...")
    entity_chunks = []
    for i, entity in enumerate(qualified):
        chunk = build_entity_chunk(entity, i)
        entity_chunks.append(chunk)

    output = {
        "metadata": {
            "total_entities": len(entity_chunks),
            "generated_on": "2026-05-09",
            "version": "v2"
        },
        "entity_registry": qualified,
        "entity_chunks": entity_chunks
    }

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Entity Registry saved → {OUT_PATH}")
    print(f"   Total entities qualified : {len(qualified)}")
    print(f"   Profile chunks created   : {len(entity_chunks)}")
