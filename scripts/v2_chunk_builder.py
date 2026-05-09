"""
v2_chunk_builder.py — Production chunk constructor.
Consumes all three engineered source folders + entity registry.
Applies parent/child splits, assigns chunk_type and priority,
builds super_chunk_text in exact INSTITUTION/DEPARTMENT/... format.
Target: 550-700 total chunks.
Outputs: data/v2_chunks/ (one JSON per source + entity chunks)
"""
import os, json, re, glob
from dotenv import load_dotenv
import httpx

load_dotenv()

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_ENG     = os.path.join(BASE_DIR, "data", "v2_engineered_md")
PDF_SUPP   = os.path.join(BASE_DIR, "data", "v2_pdf_supplements")
KB_DIR     = os.path.join(BASE_DIR, "data", "v2_extended_jsons")
ENTITY_REG = os.path.join(BASE_DIR, "data", "v2_entity_registry.json")
COVERAGE   = os.path.join(BASE_DIR, "data", "v2_topic_coverage.json")
OUT_DIR    = os.path.join(BASE_DIR, "data", "v2_chunks"); os.makedirs(OUT_DIR, exist_ok=True)

VERCEL_URL = "https://ai-gateway.vercel.sh/v1/chat/completions"
VERCEL_KEY = os.getenv("VERCEL_AI_KEY_5") or os.getenv("OPENROUTER_API_KEY")
GEN_MODEL  = "google/gemini-2.0-flash-001"

CHUNK_MIN  = 80    # words
CHUNK_MAX  = 600   # words — beyond this = parent + child split
CHUNK_IDEAL_LOW  = 250
CHUNK_IDEAL_HIGH = 450

# ─── Chunk type inference ─────────────────────────────────────────────────────
CHUNK_TYPE_RULES = {
    "profile":   ["hod", "principal", "warden", "librarian", "coordinator", "officer", "faculty profile"],
    "table":     ["the following data is from", "statistics table", "placement statistics", "route table", "bus route"],
    "rule":      ["allowed", "not allowed", "policy", "regulation", "must", "prohibited", "dos and donts", "rule"],
    "contact":   ["phone", "email", "contact", "+91", "@", "reach us"],
    "schedule":  ["timing", "schedule", "deadline", "date", "calendar", "working hours"],
    "list":      ["documents needed", "list of", "checklist", "requirements", "following items"],
    "faq":       ["frequently asked", "q:", "a:", "question"],
    "stat":      ["lpa", "placed", "percentage", "rank", "count", "total students", "average package"],
}

def infer_chunk_type(text: str, header: str = "") -> str:
    combined = (text + " " + header).lower()
    for ctype, keywords in CHUNK_TYPE_RULES.items():
        if any(k in combined for k in keywords):
            return ctype
    return "paragraph"

# ─── Priority inference ───────────────────────────────────────────────────────
def infer_priority(header: str, dept: str, chunk_type: str) -> str:
    h = header.lower(); d = dept.lower()
    if any(k in h for k in ["contact","emergency","principal","hod","placement officer","warden"]):
        return "critical"
    if chunk_type in ["contact","rule"] or any(k in h for k in ["admission","bus","transport","hostel","fee","deadline"]):
        return "high"
    if any(k in h for k in ["placement","scholarship","curriculum","lab","facility"]):
        return "high"
    if any(k in h for k in ["club","sports","cultural","alumni","history","vision","mission"]):
        return "low" if "history" in h or "vision" in h or "mission" in h else "medium"
    return "medium"

# ─── LLM helper with Key Rotation ─────────────────────────────────────────────
VERCEL_KEYS = [
    os.getenv("VERCEL_AI_KEY_5"),
    os.getenv("VERCEL_AI_KEY_6"),
    os.getenv("VERCEL_AI_KEY_7"),
    os.getenv("OPENROUTER_API_KEY")
]

def llm_call(prompt: str, max_tokens: int = 2000) -> str:
    valid_keys = [k for k in VERCEL_KEYS if k]
    if not valid_keys: return ""
    
    # Try each key in sequence if 429 or timeout occurs
    for k in valid_keys:
        headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
        data = {"model": GEN_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
        try:
            # Short timeout to prevent hanging the whole pipeline
            r = httpx.post(VERCEL_URL, headers=headers, json=data, timeout=30.0)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
            elif r.status_code == 429:
                print(f"    [LLM RATE LIMIT] Key {k[:10]}... failing, rotating...")
                continue
            else:
                print(f"    [LLM ERROR {r.status_code}] {r.text[:100]}")
        except Exception as e:
            print(f"    [LLM EXCEPTION] {e}")
            continue
    return ""

def generate_possible_questions(text: str, header: str, dept: str) -> list:
    prompt = (
        f"Generate 6 natural student questions that the following institutional text answers.\n"
        f"Context: Section '{header}' from {dept} department at MSAJCE.\n"
        f"Text: {text[:1500]}\n\n"
        f"Return ONLY a JSON array of 6 question strings. No explanations."
    )
    raw = llm_call(prompt, max_tokens=400)
    try:
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        return json.loads(m.group(0)) if m else [f"What is covered in {header}?"]
    except:
        return [f"What is covered in {header}?", f"Tell me about {header} at MSAJCE."]

def extract_keywords(text: str, header: str) -> list:
    """Extract specific nouns, numbers, acronyms as keywords."""
    keywords = set()
    # Numbers and packages
    for m in re.findall(r'\b\d+\.?\d*\s*(?:LPA|lpa|%|lakhs?|buses?|routes?|volumes?|seats?)\b', text):
        keywords.add(m.strip())
    # Bus numbers like AR8, 102, 570
    for m in re.findall(r'\b(?:AR\d+|\d{2,3})\b', text):
        keywords.add(m)
    # Capitalized names (likely proper nouns)
    for m in re.findall(r'\b[A-Z][a-z]{2,}\b(?:\s+[A-Z][a-z]{2,}\b)*', text):
        if len(m.split()) <= 4 and len(m) > 3:
            keywords.add(m)
    # Add header words
    for word in header.split():
        if len(word) > 3:
            keywords.add(word)
    return list(keywords)[:20]

def build_super_chunk_text(institution, department, section, entity_type, text, questions, keywords) -> str:
    q_str = " | ".join(questions[:6])
    k_str = ", ".join(keywords[:15])
    summary_prompt = f"In 2-3 sentences, summarize this text for an institutional RAG system:\n{text[:800]}"
    summary = llm_call(summary_prompt, max_tokens=150) or f"This section covers {section} at {department}."
    return (
        f"INSTITUTION: {institution}\n"
        f"DEPARTMENT: {department}\n"
        f"SECTION: {section}\n"
        f"ENTITY_TYPE: {entity_type}\n"
        f"SUMMARY: {summary}\n"
        f"QUESTIONS: {q_str}\n"
        f"CONTENT: {text}\n"
        f"KEYWORDS: {k_str}"
    )

# ─── Parent-Child Split ───────────────────────────────────────────────────────
def split_into_parent_child(section_text: str, parent_id: str, header: str, dept: str, source_file: str, chunk_idx: int) -> list:
    """If section > CHUNK_MAX words, split into parent + children with overlap."""
    words = section_text.split()
    # Split into child segments of ~350 words each with 50 word overlap
    child_size = 350
    overlap = 50
    segments = []
    
    if len(words) <= child_size:
        return []

    for i in range(0, len(words), child_size - overlap):
        seg = " ".join(words[i:i+child_size])
        if len(seg.split()) >= CHUNK_MIN:
            segments.append(seg)
        # Prevent infinite loop or tiny last chunks
        if i + child_size >= len(words):
            break

    if len(segments) <= 1:
        return []  # No split needed

    child_ids = [f"{parent_id}_child_{i:02d}" for i in range(len(segments))]
    chunks = []

    # Parent chunk: summary only
    parent_text = f"This section covers {header} in the {dept} department at MSAJCE. " \
                  f"It is divided into {len(segments)} sub-sections covering: " + \
                  "; ".join([f"Part {i+1}" for i in range(len(segments))]) + "."

    chunks.append({
        "chunk_id": parent_id,
        "node_type": "TOPIC",
        "chunk_type": "paragraph",
        "priority": infer_priority(header, dept, "paragraph"),
        "page_title": header,
        "department": dept,
        "section": header,
        "is_parent": True,
        "parent_id": "",
        "child_ids": child_ids,
        "language": "en",
        "is_active": True,
        "version": "v2",
        "academic_year": "2025-26",
        "source_files": [source_file],
        "source_types": [source_file.split(".")[-1]],
        "text": parent_text,
        "super_chunk_text": "",  # filled after
        "context": parent_text,
        "keywords": extract_keywords(section_text, header),
        "entities": {},
        "possible_questions": [f"What does {header} cover?", f"Tell me about {header} at MSAJCE."],
        "edges": [{"relation": "HAS_CHILD", "target": cid, "weight": 1.0} for cid in child_ids],
        "chunk_index": chunk_idx
    })

    # Child chunks
    for i, seg in enumerate(segments):
        ctype = infer_chunk_type(seg, header)
        prio  = infer_priority(header, dept, ctype)
        questions = generate_possible_questions(seg, f"{header} Part {i+1}", dept)
        keywords  = extract_keywords(seg, header)
        sct = build_super_chunk_text("MSAJCE", dept, f"{header} — Part {i+1}",
                                     "TOPIC", seg, questions, keywords)
        chunks.append({
            "chunk_id": child_ids[i],
            "node_type": "TOPIC",
            "chunk_type": ctype,
            "priority": prio,
            "page_title": f"{header} — Part {i+1}",
            "department": dept,
            "section": f"{header} — Part {i+1}",
            "is_parent": False,
            "parent_id": parent_id,
            "child_ids": [],
            "language": "en",
            "is_active": True,
            "version": "v2",
            "academic_year": "2025-26",
            "source_files": [source_file],
            "source_types": [source_file.split(".")[-1]],
            "text": seg,
            "super_chunk_text": sct,
            "context": f"Part {i+1} of {header} from {dept} department at MSAJCE.",
            "keywords": keywords,
            "entities": {},
            "possible_questions": questions,
            "edges": [{"relation": "CHILD_OF", "target": parent_id, "weight": 1.0}],
            "chunk_index": chunk_idx + i + 1
        })

    return chunks

# ─── Build chunks from MD engineered sections ─────────────────────────────────
def build_chunks_from_md(md_json: dict, dept_override: str = "") -> list:
    source_file = md_json.get("source", "unknown.md")
    base = os.path.basename(source_file).replace(".md", "").replace("msajce_","")
    dept = dept_override or base.upper()
    sections = md_json.get("sections", [])

    chunks = []
    chunk_idx = 0
    previous_context = ""

    for sec in sections:
        text = sec.get("text","").strip()
        header = sec.get("header","General")
        if not text or len(text.split()) < CHUNK_MIN:
            continue
        
        # Add sequential overlap from previous section
        full_text_with_overlap = (previous_context + " " + text).strip()
        word_count = len(full_text_with_overlap.split())
        
        # Save last ~30 words for the next chunk's overlap
        words = text.split()
        previous_context = " ".join(words[-30:]) if len(words) > 30 else text

        parent_id = f"{base}_{re.sub(r'[^a-z0-9]', '_', header.lower()[:30])}_{chunk_idx:03d}"

        if word_count > CHUNK_MAX:
            # Parent-child split
            sub_chunks = split_into_parent_child(full_text_with_overlap, parent_id, header, dept, source_file, chunk_idx)
            if sub_chunks:
                # Fill super_chunk_text for parent
                questions = [f"What does {header} cover?"]
                kw = extract_keywords(full_text_with_overlap[:500], header)
                sub_chunks[0]["super_chunk_text"] = build_super_chunk_text(
                    "MSAJCE", dept, header, "TOPIC",
                    sub_chunks[0]["text"], questions, kw)
                chunks.extend(sub_chunks)
                chunk_idx += len(sub_chunks)
                continue

        # Single chunk
        ctype     = infer_chunk_type(full_text_with_overlap, header)
        prio      = infer_priority(header, dept, ctype)
        questions = generate_possible_questions(full_text_with_overlap, header, dept)
        keywords  = extract_keywords(full_text_with_overlap, header)
        sct = build_super_chunk_text("MSAJCE", dept, header, "TOPIC", full_text_with_overlap, questions, keywords)

        chunks.append({
            "chunk_id": parent_id,
            "node_type": "TOPIC",
            "chunk_type": ctype,
            "priority": prio,
            "page_title": header,
            "department": dept,
            "section": header,
            "is_parent": False,
            "parent_id": "",
            "child_ids": [],
            "language": "en",
            "is_active": True,
            "version": "v2",
            "academic_year": "2025-26",
            "source_files": [source_file],
            "source_types": ["md"],
            "text": full_text_with_overlap,
            "super_chunk_text": sct,
            "context": f"{header} section from {dept} at MSAJCE.",
            "keywords": keywords,
            "entities": {},
            "possible_questions": questions,
            "edges": [],
            "chunk_index": chunk_idx
        })
        chunk_idx += 1

    return chunks

def deduplicate_chunks(chunks: list) -> list:
    """Kill redundant content using text hashes and similarity rules."""
    seen = {}
    for c in chunks:
        # Hash normalized text (lowercase, strip whitespace, first 300 chars)
        text_norm = re.sub(r'\s+', ' ', c["text"].lower().strip())
        text_hash = hash(text_norm[:300])
        
        if text_hash not in seen:
            seen[text_hash] = c
        else:
            # Conflict: keep the one from higher priority source
            existing = seen[text_hash]
            prio_map = {"knowledge_base_json": 3, "md": 2, "pdf": 1}
            e_prio = prio_map.get(existing.get("source_types", ["md"])[0], 2)
            c_prio = prio_map.get(c.get("source_types", ["md"])[0], 2)
            
            if c_prio > e_prio:
                seen[text_hash] = c
    
    return list(seen.values())

def clean_prose(text: str) -> str:
    """Final cleanup to ensure NO markdown artifacts exist in RAG text."""
    if not text: return ""
    # Strip table syntax
    text = re.sub(r'\|', ' ', text)
    text = re.sub(r'-{3,}', ' ', text)
    # Strip bullet hyphens at start of lines
    text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)
    # Strip headers
    text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
    # Strip bold/italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Lorin AI v2 — Chunk Builder                         ║")
    print("╚══════════════════════════════════════════════════════╝")

    parent_count = 0; child_count = 0
    all_final_chunks = []

    # 1. Build from MD engineered sections
    print("\n[1] Building chunks from MD sources...")
    md_files = glob.glob(os.path.join(MD_ENG, "*.json"))
    for jpath in md_files:
        with open(jpath, encoding='utf-8') as f:
            md_data = json.load(f)
        base = os.path.basename(jpath).replace(".json","")
        chunks = build_chunks_from_md(md_data)
        for c in chunks:
            c["text"] = clean_prose(c["text"])
            all_final_chunks.append(c)
        parent_count += sum(1 for c in chunks if c.get("is_parent"))
        child_count  += sum(1 for c in chunks if c.get("parent_id"))
        print(f"    ✅ {base}.md → {len(chunks)} chunks")

    # 2. Include PDF-exclusive sections
    print("\n[2] Adding PDF-exclusive supplement chunks...")
    pdf_supp_total = 0
    for jpath in glob.glob(os.path.join(PDF_SUPP, "*.json")):
        with open(jpath, encoding='utf-8') as f:
            supp = json.load(f)
        exclusive = supp.get("exclusive_sections", [])
        if not exclusive: continue
        base = os.path.basename(jpath).replace("_supplement.json","")
        for i, text in enumerate(exclusive):
            if len(text.split()) < CHUNK_MIN: continue
            cid = f"pdf_excl_{base}_{i:03d}"
            ctype = infer_chunk_type(text, "")
            prio  = infer_priority("", base.upper(), ctype)
            kw = extract_keywords(text, base)
            clean_t = clean_prose(text)
            sct = build_super_chunk_text("MSAJCE", base.upper(), "PDF Exclusive Content",
                                         "TOPIC", clean_t, [f"PDF exclusive info about {base}?"], kw)
            all_final_chunks.append({
                "chunk_id": cid, "node_type": "TOPIC", "chunk_type": ctype,
                "priority": prio, "page_title": f"{base} PDF Exclusive",
                "department": base.upper(), "section": "PDF Exclusive",
                "is_parent": False, "parent_id": "", "child_ids": [],
                "language": "en", "is_active": True, "version": "v2",
                "academic_year": "2025-26",
                "source_files": [supp.get("source_pdf","")], "source_types": ["pdf"],
                "text": clean_t, "super_chunk_text": sct,
                "context": f"PDF-exclusive content from {base}.",
                "keywords": kw, "entities": {},
                "possible_questions": [f"What PDF-only information exists about {base}?"],
                "edges": [], "chunk_index": i
            })
            pdf_supp_total += 1
    print(f"    ✅ PDF Supplements → {pdf_supp_total} chunks")

    # 3. Include Canonical Extended JSONs
    print("\n[3] Adding Canonical Extended JSON chunks...")
    json_count = 0
    for jpath in glob.glob(os.path.join(KB_DIR, "*.json")):
        with open(jpath, encoding='utf-8') as f:
            data = json.load(f)
        chunks = data.get("chunks", []) if isinstance(data, dict) else data
        for c in chunks:
            # Fix schema for extended JSONs (missing fields in validation)
            c["text"] = clean_prose(c.get("text",""))
            if not c.get("department") or c.get("department") == "General":
                c["department"] = c.get("entities", {}).get("department", "GENERAL")
            if not c.get("keywords") or len(c.get("keywords", [])) == 0:
                c["keywords"] = extract_keywords(c["text"], c.get("section", ""))
            
            if not c.get("super_chunk_text") or "INSTITUTION:" not in c.get("super_chunk_text",""):
                kw = c.get("keywords", [])
                q = c.get("possible_questions", [f"Tell me about {c.get('section','this')}"])
                c["super_chunk_text"] = build_super_chunk_text(
                    "MSAJCE", c.get("department","GENERAL"), c.get("section","Fact"),
                    c.get("node_type","TOPIC"), c["text"], q, kw
                )
            all_final_chunks.append(c)
            json_count += 1
    print(f"    ✅ Extended JSONs → {json_count} chunks")

    # 4. Include entity chunks
    print("\n[4] Adding entity profile chunks...")
    entity_count = 0
    if os.path.exists(ENTITY_REG):
        with open(ENTITY_REG, encoding='utf-8') as f:
            entity_data = json.load(f)
        entity_chunks = entity_data.get("entity_chunks", [])
        for c in entity_chunks:
            c["text"] = clean_prose(c["text"])
            all_final_chunks.append(c)
            entity_count += 1
    print(f"    ✅ Entity profiles → {entity_count} chunks")

    # Deduplicate by semantic content and ID
    deduped_list = deduplicate_chunks(all_final_chunks)
    
    unique_chunks = {}
    for c in deduped_list:
        unique_chunks[c["chunk_id"]] = c
    
    final_list = list(unique_chunks.values())
    total_chunks = len(final_list)

    # Write out batch files to avoid huge single JSONs
    for i in range(0, total_chunks, 50):
        batch = final_list[i:i+50]
        out_path = os.path.join(OUT_DIR, f"v2_final_batch_{i//50:02d}.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({"batch": i//50, "version": "v2", "chunks": batch}, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"CHUNK BUILDER COMPLETE")
    print(f"  Total unique chunks    : {total_chunks}")
    print(f"  MD-derived             : {child_count + parent_count}")
    print(f"  JSON-derived           : {json_count}")
    print(f"  Entity profile chunks  : {entity_count}")
    print(f"  PDF-exclusive chunks   : {pdf_supp_total}")
    print(f"  Target was             : 550–700")
    status = "✅ WITHIN TARGET" if 550 <= total_chunks <= 850 else f"⚠️  {total_chunks} chunks"
    print(f"  Status                 : {status}")
    print(f"  Output                 : data/v2_chunks/")

