"""
v2_data_engineer.py — Stage 1 (MD), Stage 2 (PDF supplement), Stage 3 (JSON extension)
Produces clean, prose-only section JSONs ready for v2_chunk_builder.py
"""
import os, json, re, glob, hashlib
import pdfplumber
from dotenv import load_dotenv
import httpx, asyncio

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_DIR   = os.path.join(BASE_DIR, "data", "datalab md")
PDF_DIR  = os.path.join(BASE_DIR, "data", "pdfs")
KB_DIR   = os.path.join(BASE_DIR, "data", "knowledge_base")

OUT_MD   = os.path.join(BASE_DIR, "data", "v2_engineered_md");  os.makedirs(OUT_MD, exist_ok=True)
OUT_PDF  = os.path.join(BASE_DIR, "data", "v2_pdf_supplements"); os.makedirs(OUT_PDF, exist_ok=True)
OUT_JSON = os.path.join(BASE_DIR, "data", "v2_extended_jsons");  os.makedirs(OUT_JSON, exist_ok=True)

VERCEL_URL = "https://ai-gateway.vercel.sh/v1/chat/completions"
VERCEL_KEY = os.getenv("VERCEL_AI_KEY_5") or os.getenv("OPENROUTER_API_KEY")
GEN_MODEL  = "google/gemini-2.0-flash-001"

# ─── LLM Helper ──────────────────────────────────────────────────────────────
def llm_call(prompt: str, max_tokens: int = 4000) -> str:
    headers = {"Authorization": f"Bearer {VERCEL_KEY}", "Content-Type": "application/json"}
    data = {"model": GEN_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
    try:
        r = httpx.post(VERCEL_URL, headers=headers, json=data, timeout=120)
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"    [LLM ERROR] {e}")
        return ""

# ─── TEXT SIMILARITY (for duplicate detection) ────────────────────────────────
def text_fingerprint(text: str) -> str:
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    return hashlib.md5(normalized.encode()).hexdigest()

def similarity_ratio(a: str, b: str) -> float:
    """Quick word-overlap similarity."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb: return 0.0
    return len(wa & wb) / max(len(wa), len(wb))

# ─── STAGE 1: MD ENGINEERING ─────────────────────────────────────────────────
def parse_md_sections(md_text: str) -> list:
    """Split MD file into sections by ## / ### headers."""
    sections = []
    current = {"header": "Introduction", "level": 1, "lines": []}
    for line in md_text.split("\n"):
        if line.startswith("### "):
            if current["lines"]: sections.append(current)
            current = {"header": line.lstrip("# ").strip(), "level": 3, "lines": []}
        elif line.startswith("## "):
            if current["lines"]: sections.append(current)
            current = {"header": line.lstrip("# ").strip(), "level": 2, "lines": []}
        else:
            current["lines"].append(line)
    if current["lines"]: sections.append(current)
    return sections

def has_markdown_table(lines: list) -> bool:
    return any("|" in l and "---" not in l for l in lines)

def has_bullet_list(lines: list) -> bool:
    return any(re.match(r'^\s*[-*•]\s', l) for l in lines)

def engineer_section(section: dict, source_name: str) -> dict:
    """Convert a raw MD section into clean engineered prose using LLM."""
    raw = "\n".join(section["lines"]).strip()
    if not raw or len(raw) < 30:
        return None

    has_table  = has_markdown_table(section["lines"])
    has_bullet = has_bullet_list(section["lines"])

    if not has_table and not has_bullet:
        # Pure prose — minor cleanup only
        clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', raw)  # strip MD links
        clean = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', clean)     # strip images
        clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean)        # strip bold
        clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
        return {"header": section["header"], "level": section["level"], "text": clean,
                "engineered": False, "has_table": False, "has_bullet": False}

    # Needs LLM conversion
    rules = []
    if has_table:
        rules.append("- Convert EVERY markdown table row into a complete natural language sentence. Example: '| Zoho | 450 | 6 LPA |' → 'Zoho recruited 450 students with a package of 6 LPA.'")
        rules.append("- Start with a context sentence: 'The following data is from the [table topic] table:'")
        rules.append("- Keep all rows of one table in one paragraph. Never split mid-table.")
    if has_bullet:
        rules.append("- Convert ALL bullet/hyphen lists into connected prose sentences.")
        rules.append("- Example: '- Python\\n- IBM certified' → 'The department provides Python training and offers IBM certified courses.'")
    rules.append("- Remove ALL markdown syntax: no pipes, no hyphens, no asterisks, no headers.")
    rules.append("- Output ONLY the clean prose text. No explanations.")

    prompt = (
        f"You are a RAG Data Engineer processing institutional data from '{source_name}'.\n"
        f"Section: '{section['header']}'\n\n"
        f"RULES:\n" + "\n".join(rules) + "\n\n"
        f"RAW CONTENT:\n{raw}\n\n"
        f"OUTPUT (clean prose only):"
    )
    engineered_text = llm_call(prompt, max_tokens=2000)
    return {"header": section["header"], "level": section["level"],
            "text": engineered_text.strip(), "engineered": True,
            "has_table": has_table, "has_bullet": has_bullet}

def engineer_md_file(md_path: str) -> list:
    source_name = os.path.basename(md_path)
    print(f"  [MD] Engineering {source_name}...")
    with open(md_path, 'r', encoding='utf-8') as f:
        text = f.read()

    sections = parse_md_sections(text)
    results = []
    for sec in sections:
        engineered = engineer_section(sec, source_name)
        if engineered and len(engineered.get("text","").split()) >= 20:
            results.append(engineered)
    return results

def run_stage1():
    print("\n" + "="*60)
    print("STAGE 1 — MD Engineering")
    print("="*60)
    md_files = glob.glob(os.path.join(MD_DIR, "*.md"))
    total_tables = 0; total_bullets = 0
    for md_path in md_files:
        base = os.path.basename(md_path).replace(".md", "")
        sections = engineer_md_file(md_path)
        total_tables  += sum(1 for s in sections if s.get("has_table"))
        total_bullets += sum(1 for s in sections if s.get("has_bullet"))
        out_path = os.path.join(OUT_MD, f"{base}.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({"source": os.path.basename(md_path), "sections": sections}, f, indent=2, ensure_ascii=False)
        print(f"    ✅ {base}.md → {len(sections)} sections saved")
    print(f"\n  Tables converted  : {total_tables}")
    print(f"  Bullets converted : {total_bullets}")
    return total_tables, total_bullets

# ─── STAGE 2: PDF SUPPLEMENT SCAN ────────────────────────────────────────────
def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from PDF, stripping boilerplate."""
    text_parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_texts = [p.extract_text() or "" for p in pdf.pages]

        # Detect repeated header/footer (appears on 3+ pages)
        line_freq = {}
        for pt in page_texts:
            for line in pt.split("\n"):
                l = line.strip()
                if l and len(l) > 5:
                    line_freq[l] = line_freq.get(l, 0) + 1
        boilerplate = {l for l, c in line_freq.items() if c >= 3}

        for pt in page_texts:
            clean_lines = []
            for line in pt.split("\n"):
                l = line.strip()
                if not l: continue
                if l in boilerplate: continue
                if re.match(r'^\d+$', l): continue                    # page numbers
                if re.match(r'^https?://', l): continue               # bare URLs
                if re.match(r'^www\.', l): continue
                # Fix common OCR artifacts
                l = re.sub(r'€', 'e', l)
                l = re.sub(r'[^\x00-\x7F]+', ' ', l)                 # non-ASCII
                l = re.sub(r'\s{3,}', '  ', l)
                clean_lines.append(l)
            text_parts.append("\n".join(clean_lines))
    except Exception as e:
        print(f"    [PDF ERROR] {e}")
    return "\n\n".join(text_parts)

def find_pdf_exclusive_sections(pdf_text: str, md_sections: list) -> list:
    """Find paragraphs in PDF not present in MD (>85% similarity = duplicate)."""
    md_combined = " ".join(s.get("text","") for s in md_sections)
    exclusive = []
    for para in re.split(r'\n{2,}', pdf_text):
        para = para.strip()
        if len(para.split()) < 30: continue  # too short
        ratio = similarity_ratio(para, md_combined)
        if ratio < 0.15:  # less than 15% word overlap = truly unique
            exclusive.append(para)
    return exclusive

def run_stage2():
    print("\n" + "="*60)
    print("STAGE 2 — PDF Supplement Scan")
    print("="*60)
    pdf_files = glob.glob(os.path.join(PDF_DIR, "*.pdf"))
    total_exclusive = 0
    for pdf_path in pdf_files:
        base = os.path.basename(pdf_path).replace(".pdf", "")
        # Load corresponding engineered MD sections
        md_json_path = os.path.join(OUT_MD, f"{base}.json")
        md_sections = []
        if os.path.exists(md_json_path):
            with open(md_json_path) as f:
                md_sections = json.load(f).get("sections", [])

        pdf_text = extract_pdf_text(pdf_path)
        exclusive = find_pdf_exclusive_sections(pdf_text, md_sections)
        total_exclusive += len(exclusive)

        out_path = os.path.join(OUT_PDF, f"{base}_supplement.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({
                "source_pdf": os.path.basename(pdf_path),
                "source_type": "pdf_exclusive",
                "exclusive_sections": exclusive
            }, f, indent=2, ensure_ascii=False)
        flag = f"({len(exclusive)} exclusive)" if exclusive else "(no exclusive content)"
        print(f"    ✅ {base}.pdf → scanned {flag}")
    print(f"\n  PDF-exclusive sections found: {total_exclusive}")
    return total_exclusive

# ─── STAGE 3: JSON SCHEMA EXTENSION ─────────────────────────────────────────
V2_DEFAULTS = {
    "node_type": "FACT",
    "chunk_type": "paragraph",
    "priority": "medium",
    "is_parent": False,
    "parent_id": "",
    "child_ids": [],
    "language": "en",
    "is_active": True,
    "version": "v2",
    "academic_year": "2025-26",
    "source_files": [],
    "source_types": [],
    "keywords": [],
    "context": "",
    "edges": []
}

def extend_chunk_schema(chunk: dict, global_meta: dict, source_file: str) -> dict:
    """Apply v2 schema defaults to an existing chunk."""
    extended = dict(chunk)
    for k, v in V2_DEFAULTS.items():
        if k not in extended:
            extended[k] = v if not isinstance(v, list) else list(v)

    # Ensure source_files populated
    if not extended.get("source_files"):
        extended["source_files"] = [source_file]
    if not extended.get("source_types"):
        ext = source_file.split(".")[-1] if "." in source_file else "json"
        extended["source_types"] = [ext]

    # Promote global metadata fields
    for field in ["institution", "department", "page_title", "academic_year"]:
        if field in global_meta and field not in extended:
            extended[field] = global_meta[field]

    # Flatten entities if nested
    entities_raw = extended.get("entities", {})
    if isinstance(entities_raw, dict):
        flattened = {}
        for k, v in entities_raw.items():
            key = f"entity_{k}" if not k.startswith("entity_") else k
            flattened[key] = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
        extended["entities"] = entities_raw
        extended.update(flattened)

    # Infer priority if not set
    if extended.get("priority") == "medium":
        title_lower = str(extended.get("page_title","")).lower()
        section_lower = str(extended.get("section","")).lower()
        if any(k in section_lower for k in ["contact","emergency","principal","hod"]):
            extended["priority"] = "critical"
        elif any(k in title_lower for k in ["placement","admission","bus","transport","hostel"]):
            extended["priority"] = "high"

    return extended

def run_stage3():
    print("\n" + "="*60)
    print("STAGE 3 — JSON Schema Extension")
    print("="*60)
    json_files = glob.glob(os.path.join(KB_DIR, "*.json"))
    total_chunks = 0
    for jpath in json_files:
        base = os.path.basename(jpath)
        with open(jpath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, list):
            chunks = data; global_meta = {}
        else:
            chunks = data.get("chunks", []); global_meta = data.get("metadata", {})

        extended_chunks = [extend_chunk_schema(c, global_meta, base) for c in chunks]
        total_chunks += len(extended_chunks)

        out = {"metadata": {**global_meta, "version": "v2", "source_file": base},
               "chunks": extended_chunks}
        out_path = os.path.join(OUT_JSON, base)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"    ✅ {base} → {len(extended_chunks)} chunks extended")
    print(f"\n  Total JSON chunks extended: {total_chunks}")
    return total_chunks

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Lorin AI v2 — Data Engineering Pipeline             ║")
    print("╚══════════════════════════════════════════════════════╝")
    t, b = run_stage1()
    e    = run_stage2()
    j    = run_stage3()
    print("\n" + "="*60)
    print("DATA ENGINEERING COMPLETE")
    print(f"  MD tables converted        : {t}")
    print(f"  MD bullet lists converted  : {b}")
    print(f"  PDF-exclusive sections     : {e}")
    print(f"  JSON chunks extended       : {j}")
    print("  Outputs:")
    print(f"    data/v2_engineered_md/   ← Stage 1")
    print(f"    data/v2_pdf_supplements/ ← Stage 2")
    print(f"    data/v2_extended_jsons/  ← Stage 3")
