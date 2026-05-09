"""
v2_topic_coverage_map.py — Step 2 of the prompt.
Scans ALL three source folders and prints the Topic Coverage Map.
MUST complete and print map before chunk building begins.
Outputs: data/v2_topic_coverage.json
"""
import os, json, re, glob
from dotenv import load_dotenv

load_dotenv()

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_ENG    = os.path.join(BASE_DIR, "data", "v2_engineered_md")
KB_DIR    = os.path.join(BASE_DIR, "data", "v2_extended_jsons")
PDF_SUPP  = os.path.join(BASE_DIR, "data", "v2_pdf_supplements")
OUT_PATH  = os.path.join(BASE_DIR, "data", "v2_topic_coverage.json")

# ─── Topics to map ────────────────────────────────────────────────────────────
TOPIC_KEYWORDS = {
    "Principal Details":        ["principal", "k.s. srinivasan", "srinivasan"],
    "Dr. Weslin D Profile":     ["weslin", "it hod", "information technology head"],
    "Bus Routes & Transport":   ["bus", "route", "transport", "tambaram", "ar8", "timing"],
    "Placement Statistics":     ["placement", "lpa", "recruiter", "package", "hired"],
    "CSE Department":           ["computer science", "cse department", "cse lab"],
    "IT Department":            ["information technology", "it department", "it lab"],
    "AIDS Department":          ["ai and data science", "aids department", "big data"],
    "AIML Department":          ["ai and machine learning", "aiml", "neural network"],
    "ECE Department":           ["electronics", "ece", "communication engineering"],
    "EEE Department":           ["electrical", "eee", "power systems"],
    "Cyber Security":           ["cyber security", "ethical hacking", "forensics"],
    "CSBS Department":          ["computer science business", "csbs", "tcs integrated"],
    "Admission Process":        ["admission", "tnea", "counselling", "application"],
    "Admission Documents":      ["documents needed", "certificate", "marksheet", "tc"],
    "Scholarship Schemes":      ["scholarship", "pragati", "saksham", "aicte"],
    "Hostel Rules":             ["hostel", "warden", "outing", "mess", "accommodation"],
    "Library Facilities":       ["library", "volumes", "delnet", "ndli", "journals"],
    "Sports & Athletics":       ["sports", "gym", "football", "cricket", "basketball"],
    "Incubation & Startup":     ["incubation", "siif", "startup", "patent", "iic"],
    "Research & PhD":           ["research", "phd", "publication", "funding"],
    "IQAC & Accreditation":     ["iqac", "naac", "accreditation", "aqar"],
    "Technology Centres":       ["technology centre", "nvidia", "intel", "cisco lab"],
    "Professional Societies":   ["ieee", "iste", "csi", "society", "iete"],
    "Clubs & Cultural":         ["club", "cultural", "nss", "yrc", "rotaract", "thiruvizha"],
    "Alumni Network":           ["alumni", "sathakians", "graduates"],
    "Science & Humanities":     ["science and humanities", "first year", "physics", "chemistry", "maths"],
    "Fee Structure":            ["fee", "tuition", "payment", "feepayr"],
    "Anti-Ragging Policy":      ["anti-ragging", "ragging", "zero tolerance"],
    "HOD Contacts (All Depts)": ["head of department", "hod contact", "department head"],
    "College Code & Affiliations": ["anna university", "aicte", "affiliated", "college code", "1301"],
    "NIRF Rankings":            ["nirf", "ranking", "rank", "ariia"],
}

def load_all_text() -> dict:
    """Returns {source_key: (full_text, source_type)} for all sources."""
    all_sources = {}

    for jpath in glob.glob(os.path.join(MD_ENG, "*.json")):
        base = os.path.basename(jpath).replace(".json", ".md")
        with open(jpath) as f:
            data = json.load(f)
        text = "\n".join(s.get("text","") for s in data.get("sections",[]))
        all_sources[base] = ("md", text)

    for jpath in glob.glob(os.path.join(KB_DIR, "*.json")):
        base = os.path.basename(jpath)
        with open(jpath) as f:
            data = json.load(f)
        chunks = data.get("chunks", []) if isinstance(data, dict) else data
        text = "\n".join(c.get("text","") for c in chunks)
        all_sources[f"kb/{base}"] = ("json", text)

    for jpath in glob.glob(os.path.join(PDF_SUPP, "*.json")):
        base = os.path.basename(jpath)
        with open(jpath) as f:
            data = json.load(f)
        text = "\n".join(data.get("exclusive_sections",[]))
        if text.strip():
            all_sources[f"pdf/{base}"] = ("pdf", text)

    return all_sources

def check_topic(keywords: list, text: str) -> bool:
    text_lower = text.lower()
    return any(k in text_lower for k in keywords)

def find_unique_source(topic: str, keywords: list, sources: dict) -> str:
    """Find which source type has the best/unique data."""
    hits = {"md": [], "json": [], "pdf": []}
    for src_key, (src_type, text) in sources.items():
        if check_topic(keywords, text):
            hits[src_type].append(src_key)
    # Determine unique source
    if hits["pdf"] and not hits["md"]:
        return f"PDF exclusive: {hits['pdf'][0]}"
    elif hits["md"] and not hits["json"]:
        return f"MD primary: {hits['md'][0]}"
    elif hits["json"] and not hits["md"]:
        return f"JSON only: {hits['json'][0]}"
    elif len(hits["md"]) > 0:
        return f"MD + JSON (merge)"
    return "Not found"

def determine_action(has_json, has_md, has_pdf, unique_source) -> str:
    if has_json and has_md and has_pdf:
        return "Merge all 3 sources"
    elif has_json and has_md:
        return "Merge JSON + MD"
    elif has_md and has_pdf:
        return "MD primary + PDF supplement"
    elif has_md:
        return "MD only — create chunks"
    elif has_json:
        return "JSON only — extend schema"
    elif has_pdf:
        return "PDF exclusive — extract & chunk"
    return "⚠️ MISSING — add to Ground Truth"

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Lorin AI v2 — Topic Coverage Map                    ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    print("Loading all source text...")
    sources = load_all_text()
    md_sources  = {k: v for k, v in sources.items() if v[0] == "md"}
    json_sources = {k: v for k, v in sources.items() if v[0] == "json"}
    pdf_sources  = {k: v for k, v in sources.items() if v[0] == "pdf"}
    print(f"  MD sources:   {len(md_sources)}")
    print(f"  JSON sources: {len(json_sources)}")
    print(f"  PDF sources:  {len(pdf_sources)}\n")

    print("Generating Topic Coverage Map...")
    print()

    # Table header
    header = f"{'Topic':<35} {'JSON':^6} {'MD':^6} {'PDF':^6} {'Unique Source':<30} {'Action'}"
    print(header)
    print("─" * len(header))

    coverage_map = []
    missing_topics = []

    for topic, keywords in TOPIC_KEYWORDS.items():
        has_json = any(check_topic(keywords, t) for _, t in json_sources.values())
        has_md   = any(check_topic(keywords, t) for _, t in md_sources.values())
        has_pdf  = any(check_topic(keywords, t) for _, t in pdf_sources.values())

        j = "✅" if has_json else "❌"
        m = "✅" if has_md   else "❌"
        p = "✅" if has_pdf  else "❌"

        unique = find_unique_source(topic, keywords, sources)
        action = determine_action(has_json, has_md, has_pdf, unique)

        if not has_json and not has_md and not has_pdf:
            missing_topics.append(topic)

        row = f"{topic:<35} {j:^6} {m:^6} {p:^6} {unique:<30} {action}"
        print(row)

        coverage_map.append({
            "topic": topic, "keywords": keywords,
            "in_json": has_json, "in_md": has_md, "in_pdf": has_pdf,
            "unique_source": unique, "action": action
        })

    print("\n" + "─" * len(header))
    print(f"Total topics mapped: {len(coverage_map)}")
    if missing_topics:
        print(f"\n⚠️  MISSING TOPICS (must add to Ground Truth):")
        for t in missing_topics:
            print(f"   - {t}")
    else:
        print("✅ All topics have at least one source.")

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump({"topics": coverage_map, "missing": missing_topics}, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Coverage map saved → {OUT_PATH}")
    print("\n⚡ READY TO PROCEED TO STEP 3 — Chunk Construction")
