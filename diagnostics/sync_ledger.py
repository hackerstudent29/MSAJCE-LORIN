import os
import json

AUDIT_DIR = "d://.gemini/claude RAG/data/audits/deep_audit"
LEDGER = "d://.gemini/claude RAG/data/audits/live_audit_questions.txt"

def sync_ledger():
    print("SYNCING LEDGER...")
    q_entries = []
    
    files = [f for f in os.listdir(AUDIT_DIR) if f.endswith(".json")]
    for file in files:
        file_path = os.path.join(AUDIT_DIR, file)
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                for entry in data:
                    status = entry.get("evaluation", {}).get("status", "UNKNOWN")
                    q = entry.get("question", "N/A")
                    q_entries.append(f"[{status}] {q}")
        except:
            pass
            
    with open(LEDGER, "w") as f:
        f.write("# MSAJCE LORIN — LIVE FORENSIC AUDIT LEDGER\n")
        f.write("# Updated in real-time during the 450-question institutional lockdown.\n\n")
        f.write("--- QUESTIONS COMPLETED ---\n")
        f.write("\n".join(q_entries))
        f.write("\n")

    print(f"DONE. {len(q_entries)} questions synced.")

if __name__ == "__main__":
    sync_ledger()
