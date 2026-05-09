"""
v2_ground_truth.py — Ground Truth v2 generator.
Extracts all HODs, wardens, key contacts, stats, and critical dates.
Extends (does NOT replace) existing ground_truth.json.
Outputs: data/ground_truth_v2.json
"""
import os, json, glob, re
from dotenv import load_dotenv
import httpx

load_dotenv()

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKS_DIR = os.path.join(BASE_DIR, "data", "v2_chunks")
ENTITY_REG = os.path.join(BASE_DIR, "data", "v2_entity_registry.json")
EXISTING_GT= os.path.join(BASE_DIR, "data", "ground_truth.json")
OUT_PATH   = os.path.join(BASE_DIR, "data", "ground_truth_v2.json")

VERCEL_URL = "https://ai-gateway.vercel.sh/v1/chat/completions"
VERCEL_KEY = os.getenv("VERCEL_AI_KEY_5") or os.getenv("OPENROUTER_API_KEY")
GEN_MODEL  = "google/gemini-2.0-flash-001"

def llm_call(prompt: str, max_tokens: int = 2000) -> str:
    headers = {"Authorization": f"Bearer {VERCEL_KEY}", "Content-Type": "application/json"}
    data = {"model": GEN_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
    try:
        r = httpx.post(VERCEL_URL, headers=headers, json=data, timeout=90)
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"    [LLM ERROR] {e}")
        return "{}"

def make_gt_entry(value: str, source: str, valid_until: str = "2027-05-31") -> dict:
    return {"value": value, "source": source, "valid_until": valid_until}

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Lorin AI v2 — Ground Truth Generator                ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    # Start with existing ground truth
    gt = {}
    if os.path.exists(EXISTING_GT):
        with open(EXISTING_GT) as f:
            gt = json.load(f)
        print(f"[1] Loaded existing ground_truth.json: {len(gt)} entries")

    # Load entity registry
    entity_chunks = []
    if os.path.exists(ENTITY_REG):
        with open(ENTITY_REG, encoding='utf-8') as f:
            entity_data = json.load(f)
        entity_chunks = entity_data.get("entity_chunks", [])
        print(f"[2] Loaded entity registry: {len(entity_chunks)} entities")

    # Extract HODs from entity chunks
    print("[3] Extracting HOD, Warden, Officer entries...")
    for ec in entity_chunks:
        entities = ec.get("entities", {})
        role  = entities.get("role","").lower()
        name  = entities.get("name","")
        dept  = entities.get("department","")
        email = entities.get("email","")
        phone = entities.get("phone","")
        chunk_id = ec.get("chunk_id","")

        if not name: continue

        # HOD entries
        if "hod" in role or "head of department" in role:
            dept_key = re.sub(r'[^a-z0-9]', '_', dept.lower())
            gt[f"hod_{dept_key}"] = make_gt_entry(name, chunk_id)
            if email: gt[f"hod_{dept_key}_email"] = make_gt_entry(email, chunk_id)
            if phone: gt[f"hod_{dept_key}_phone"] = make_gt_entry(phone, chunk_id)

        # Principal
        if "principal" in role:
            gt["principal_name"]  = make_gt_entry(name, chunk_id)
            if email: gt["principal_email"] = make_gt_entry(email, chunk_id)
            if phone: gt["principal_phone"] = make_gt_entry(phone, chunk_id)

        # Warden
        if "warden" in role:
            warden_type = "boys" if "boy" in dept.lower() or "gent" in dept.lower() else "girls"
            gt[f"hostel_warden_{warden_type}"] = make_gt_entry(name, chunk_id)

        # Placement Officer / TPO
        if "placement" in role or "tpo" in role:
            gt["placement_officer"] = make_gt_entry(name, chunk_id)
            if email: gt["placement_officer_email"] = make_gt_entry(email, chunk_id)
            if phone: gt["placement_officer_phone"] = make_gt_entry(phone, chunk_id)

        # Librarian
        if "librarian" in role:
            gt["chief_librarian"] = make_gt_entry(name, chunk_id)

        # Transport
        if "transport" in role:
            gt["transport_coordinator"] = make_gt_entry(name, chunk_id)

    # Extract key stats from chunks using LLM
    print("[4] Extracting key statistics from chunks...")
    all_chunks_text = ""
    for jpath in glob.glob(os.path.join(CHUNKS_DIR, "*.json"))[:5]:  # sample for stats
        with open(jpath, encoding='utf-8') as f:
            data = json.load(f)
        for c in data.get("chunks",[])[:10]:
            all_chunks_text += c.get("text","")[:500] + "\n"

    stats_prompt = (
        "Extract key institutional statistics from the text below.\n"
        "Return a JSON object with these keys (use empty string if not found):\n"
        "highest_package, average_package, placement_percentage, total_students,\n"
        "total_buses, library_volumes, naac_grade, college_code,\n"
        "campus_area_acres, established_year\n\n"
        f"TEXT:\n{all_chunks_text[:4000]}\n\n"
        "Return ONLY valid JSON. No explanations."
    )
    raw_stats = llm_call(stats_prompt, max_tokens=500)
    try:
        m = re.search(r'\{.*\}', raw_stats, re.DOTALL)
        stats = json.loads(m.group(0)) if m else {}
        for key, val in stats.items():
            if val and str(val).strip():
                gt[key] = make_gt_entry(str(val), "auto_extracted_from_chunks")
    except Exception as e:
        print(f"    [STATS PARSE ERROR] {e}")

    # Hardcoded critical facts (from prior sessions and ground_truth.json)
    critical_facts = {
        "college_code":       ("1301", "Anna_University_Affiliation", "2099-12-31"),
        "principal_name":     ("Dr. K.S. Srinivasan", "msajce_about.md", "2027-05-31"),
        "hod_it":             ("Dr. Weslin D", "msajce_it.md", "2027-05-31"),
        "hod_cse":            ("Dr. K. Sayeelatha", "msajce_cse.md", "2027-05-31"),
        "hod_aids":           ("Dr. M. Senthil Kumar", "msajce_aids.md", "2027-05-31"),
        "hod_aiml":           ("Dr. P. Velmani", "msajce_aiml.md", "2027-05-31"),
        "hod_ece":            ("Dr. S. Radha", "msajce_ece.md", "2027-05-31"),
        "hod_eee":            ("Dr. R. Maheswari", "msajce_eee.md", "2027-05-31"),
        "iic_president":      ("Dr. B. Janarthanan", "IIC_Council_List", "2026-12-31"),
        "csi_vp":             ("Saqlin Mustaq M (Batch 2023-2027)", "Professional_Societies", "2027-05-31"),
        "highest_package":    ("12 LPA", "msajce_placement.md", "2027-05-31"),
        "campus_area_acres":  ("70", "msajce_about.md", "2099-12-31"),
        "established_year":   ("2001", "msajce_about.md", "2099-12-31"),
        "library_volumes":    ("40000+", "msajce_library.md", "2027-05-31"),
        "total_buses":        ("22+", "msajce_transport.md", "2027-05-31"),
        "admission_documents": (
            "10th & 12th Marks Sheets (Original), Transfer Certificate (TC), "
            "Community Certificate, Nativity Certificate (if applicable), "
            "First Graduate Certificate (if applicable), TNEA Allotment Order, "
            "10 Passport size photos, Income Certificate (for scholarships)",
            "msajce_admission.md", "2027-05-31"
        ),
        "college_address":    ("34, Rajiv Gandhi Salai (OMR), Siruseri IT Park, Siruseri, Chennai – 603103", "msajce_about.md", "2099-12-31"),
        "college_phone":      ("+91 99400 04500", "msajce_about.md", "2099-12-31"),
        "college_email":      ("msajce.office@gmail.com", "msajce_about.md", "2099-12-31"),
        "grievance_email":    ("grievance@msajce-edu.in", "msajce_about.md", "2099-12-31"),
        "online_application": ("https://enrollonline.co.in/Registration/Apply/MSAJCE", "msajce_admission.md", "2027-05-31"),
    }
    for key, (val, src, until) in critical_facts.items():
        if key not in gt or not gt[key].get("value"):  # don't overwrite if already extracted
            gt[key] = make_gt_entry(val, src, until)

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(gt, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Ground Truth v2 saved → {OUT_PATH}")
    print(f"   Total entries          : {len(gt)}")
    print(f"   HOD entries            : {sum(1 for k in gt if k.startswith('hod_'))}")
    print(f"   Critical facts locked  : {len(critical_facts)}")
    print(f"   Source: extends existing ground_truth.json (not replaced)")
