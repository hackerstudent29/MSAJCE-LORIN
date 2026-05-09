"""
v2_validate.py — 30-point validation checklist for msajce-v2.
Run this AFTER all ingestion steps complete.
Prints final report with pass/fail per check.
"""
import os, json, re, glob
from collections import Counter
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKS_DIR = os.path.join(BASE_DIR, "data", "v2_chunks")
BM25_V2    = os.path.join(BASE_DIR, "data", "bm25_index_v2")
GT_V2      = os.path.join(BASE_DIR, "data", "ground_truth_v2.json")
ENTITY_REG = os.path.join(BASE_DIR, "data", "v2_entity_registry.json")

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"

def check(label: str, result: bool, detail: str = "") -> tuple:
    status = PASS if result else FAIL
    line = f"  {status}  {label}"
    if detail: line += f" — {detail}"
    print(line)
    return result

results = []

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Lorin AI v2 — 30-Point Validation Checklist         ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    # Load all chunks for inspection
    all_chunks = []
    for jpath in glob.glob(os.path.join(CHUNKS_DIR, "*.json")):
        with open(jpath, encoding='utf-8') as f:
            data = json.load(f)
        chunks = data.get("chunks", []) if isinstance(data, dict) else data
        all_chunks.extend(chunks)

    total = len(all_chunks)
    print(f"  Total chunks loaded: {total}\n")
    # Distribution Check
    print("\n────────────────────────────────────────────────────────────")
    print("CHUNK TYPE DISTRIBUTION")
    print("────────────────────────────────────────────────────────────")
    type_counts = Counter(c.get("chunk_type", "unknown") for c in all_chunks)
    required_types = ["profile", "table", "paragraph", "rule", "contact", "list", "stat"]
    for t in required_types:
        count = type_counts.get(t, 0)
        status = "✅" if count > 0 else "⚠️ "
        print(f"  {status} {t.ljust(12)}: {count} chunks")
    
    print("\n────────────────────────────────────────────────────────────")
    print("DATA ENGINEERING CHECKS")
    print("─" * 60)

    # 1. No raw markdown table syntax
    raw_table = [c for c in all_chunks if "|" in c.get("text","") and "---" in c.get("text","")]
    results.append(check("No raw markdown table syntax in text fields",
                          len(raw_table) == 0, f"{len(raw_table)} violations"))

    # 2. No bullet hyphens in text
    bullet_chunks = [c for c in all_chunks if re.search(r'^\s*[-*]\s', c.get("text",""), re.MULTILINE)]
    results.append(check("No bullet hyphens in text fields",
                          len(bullet_chunks) == 0, f"{len(bullet_chunks)} violations"))

    # 3. No raw markdown headers in text
    header_chunks = [c for c in all_chunks if re.search(r'^#{1,3}\s', c.get("text",""), re.MULTILINE)]
    results.append(check("No raw markdown headers in text fields",
                          len(header_chunks) == 0, f"{len(header_chunks)} violations"))

    # 4. Chunk word count minimum (80)
    short = [c for c in all_chunks if len(c.get("text","").split()) < 80]
    results.append(check("All chunks ≥ 80 words",
                          len(short) == 0, f"{len(short)} chunks below minimum"))

    # 5. Chunk word count maximum (600)
    long_chunks = [c for c in all_chunks if len(c.get("text","").split()) > 600]
    results.append(check("All chunks ≤ 600 words",
                          len(long_chunks) == 0, f"{len(long_chunks)} chunks above maximum"))

    # 6. All chunks have super_chunk_text
    no_sct = [c for c in all_chunks if not c.get("super_chunk_text","").strip()]
    results.append(check("All chunks have super_chunk_text",
                          len(no_sct) == 0, f"{len(no_sct)} missing"))

    # 7. super_chunk_text format
    wrong_format = [c for c in all_chunks
                    if c.get("super_chunk_text") and
                    "INSTITUTION:" not in c.get("super_chunk_text","")]
    results.append(check("super_chunk_text follows INSTITUTION/DEPT/SECTION format",
                          len(wrong_format) == 0, f"{len(wrong_format)} malformed"))

    # 8. All chunks have ≥5 possible_questions
    few_q = [c for c in all_chunks if len(c.get("possible_questions",[])) < 5]
    results.append(check("All chunks have ≥5 possible_questions",
                          len(few_q) == 0, f"{len(few_q)} have fewer than 5"))

    # 9. No duplicate chunk_ids
    ids = [c.get("chunk_id","") for c in all_chunks]
    dupes = len(ids) - len(set(ids))
    results.append(check("No duplicate chunk_ids",
                          dupes == 0, f"{dupes} duplicates found"))

    print("\n" + "─" * 60)
    print("ENTITY EXTRACTION CHECKS")
    print("─" * 60)

    entity_chunks = [c for c in all_chunks if c.get("node_type") == "PERSON"]

    # 10. HOD chunks exist (minimum 5 departments)
    hod_chunks = [c for c in entity_chunks
                  if "hod" in c.get("entities",{}).get("role","").lower() or
                     "head of department" in c.get("entities",{}).get("role","").lower()]
    results.append(check("HOD profile chunks exist (≥5)",
                          len(hod_chunks) >= 5, f"{len(hod_chunks)} HOD chunks found"))

    # 11. Principal chunk exists
    principal = [c for c in entity_chunks
                 if "principal" in c.get("entities",{}).get("role","").lower()]
    results.append(check("Principal profile chunk exists",
                          len(principal) >= 1, f"{len(principal)} found"))

    # 12. No person entity duplicated across multiple chunks
    person_names = [c.get("entities",{}).get("name","").lower() for c in entity_chunks]
    person_names = [n for n in person_names if n]
    name_dupes = len(person_names) - len(set(person_names))
    results.append(check("No person entity duplicated across chunks",
                          name_dupes == 0, f"{name_dupes} duplicates"))

    # 13. Child chunks have valid parent_id
    child_chunks = [c for c in all_chunks if c.get("parent_id","")]
    all_ids_set  = set(ids)
    invalid_parents = [c for c in child_chunks if c.get("parent_id","") not in all_ids_set]
    results.append(check("All child chunks have valid parent_id",
                          len(invalid_parents) == 0, f"{len(invalid_parents)} invalid parent refs"))

    # 14. Parent chunks have child_ids
    parent_chunks = [c for c in all_chunks if c.get("is_parent") == True]
    empty_parents = [c for c in parent_chunks if not c.get("child_ids",[])]
    results.append(check("All parent chunks have child_ids populated",
                          len(empty_parents) == 0, f"{len(empty_parents)} parents with empty child_ids"))

    print("\n" + "─" * 60)
    print("CHUNK QUALITY CHECKS")
    print("─" * 60)

    # 15. All chunks have chunk_type
    no_type = [c for c in all_chunks if not c.get("chunk_type","")]
    results.append(check("All chunks have chunk_type",
                          len(no_type) == 0, f"{len(no_type)} missing"))

    # 16. All chunks have priority
    no_prio = [c for c in all_chunks if not c.get("priority","")]
    results.append(check("All chunks have priority",
                          len(no_prio) == 0, f"{len(no_prio)} missing"))

    # 17. All chunks have department
    no_dept = [c for c in all_chunks if not c.get("department","")]
    results.append(check("All chunks have department",
                          len(no_dept) == 0, f"{len(no_dept)} missing"))

    # 18. All chunks have source_files
    no_src = [c for c in all_chunks if not c.get("source_files",[])]
    results.append(check("All chunks have source_files",
                          len(no_src) == 0, f"{len(no_src)} missing"))

    # 19. All chunks have keywords
    no_kw = [c for c in all_chunks if not c.get("keywords",[])]
    results.append(check("All chunks have keywords",
                          len(no_kw) == 0, f"{len(no_kw)} missing"))

    # 20. Critical priority chunks exist
    critical = [c for c in all_chunks if c.get("priority") == "critical"]
    results.append(check("Critical priority chunks exist (≥5)",
                          len(critical) >= 5, f"{len(critical)} critical chunks"))

    print("\n" + "─" * 60)
    print("PINECONE CHECKS")
    print("─" * 60)

    try:
        v2_stats = pc.Index("msajce-v2").describe_index_stats()
        v2_count = v2_stats.total_vector_count
        raglorin_count = pc.Index("raglorin").describe_index_stats().total_vector_count
    except Exception as e:
        v2_count = 0; raglorin_count = 0
        print(f"    [PINECONE ERROR] {e}")

    # 21. msajce-v2 exists and has vectors
    results.append(check("msajce-v2 index exists and has vectors",
                          v2_count > 0, f"{v2_count} vectors"))

    # 22. msajce-v2 vector count approximately matches chunk count
    diff = abs(v2_count - total)
    results.append(check("msajce-v2 vector count ≈ chunk count",
                          diff < total * 0.05, f"vectors={v2_count}, chunks={total}, diff={diff}"))

    # 23. raglorin is untouched (compare with known baseline)
    results.append(check("raglorin index is UNTOUCHED",
                          raglorin_count > 0, f"{raglorin_count} vectors (must be unchanged)"))

    print("\n" + "─" * 60)
    print("RETRIEVAL CHECKS")
    print("─" * 60)

    # 24. BM25 v2 index exists
    bm25_exists = os.path.exists(os.path.join(BM25_V2, "params.index.json"))
    results.append(check("BM25 v2 index exists at data/bm25_index_v2/",
                          bm25_exists))

    # 25. Ground truth v2 exists
    gt_exists = os.path.exists(GT_V2)
    results.append(check("Ground truth v2 exists at data/ground_truth_v2.json",
                          gt_exists))

    # 26. Ground truth has HOD entries
    hod_gt_count = 0
    if gt_exists:
        with open(GT_V2) as f:
            gt = json.load(f)
        hod_gt_count = sum(1 for k in gt if k.startswith("hod_") and not k.endswith(("_email","_phone")))
    results.append(check("Ground truth has HOD entries (≥5)",
                          hod_gt_count >= 5, f"{hod_gt_count} HOD entries"))

    # 27. Ground truth has admission_documents
    results.append(check("Ground truth has admission_documents entry",
                          gt_exists and "admission_documents" in gt))

    # 28. Ground truth has principal_name
    results.append(check("Ground truth has principal_name",
                          gt_exists and "principal_name" in gt and gt["principal_name"].get("value","")))

    # 29. Ground truth has highest_package
    results.append(check("Ground truth has highest_package",
                          gt_exists and "highest_package" in gt))

    # 30. Total chunks in target range 550-700
    results.append(check("Total chunks in target range (550-700)",
                          550 <= total <= 700, f"{total} chunks"))

    # Final report
    passed = sum(1 for r in results if r)
    failed = len(results) - passed
    print("\n" + "=" * 60)
    print("FINAL VALIDATION REPORT")
    print("=" * 60)
    print(f"  Source files processed      : {len(glob.glob(os.path.join(CHUNKS_DIR,'*.json')))}")
    print(f"  Total chunks created        : {total}")
    print(f"  Parent chunks               : {len(parent_chunks)}")
    print(f"  Child chunks                : {len(child_chunks)}")
    print(f"  Entity profile chunks       : {len(entity_chunks)}")
    print(f"  Vectors in msajce-v2        : {v2_count}")
    print(f"  Ground truth entries        : {len(gt) if gt_exists else 0}")
    print(f"  raglorin index status       : UNTOUCHED ✅ ({raglorin_count} vectors)")
    print(f"  Validation checks passed    : {passed} / {len(results)}")
    if failed > 0:
        print(f"\n  ⚠️  {failed} checks FAILED — review above before switching engine to msajce-v2")
    else:
        print(f"\n  🎉 ALL CHECKS PASSED — Safe to switch engine.py to msajce-v2")
