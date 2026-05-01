import os
import sys
import asyncio
import json
import csv
import httpx
from datetime import datetime, timedelta

# Ensure core can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import RAGEngine

async def run_audit():
    engine = RAGEngine()
    logs_raw = await engine.redis.lrange("lorin_forensic_logs", 0, -1)
    logs = [json.loads(l) for l in logs_raw]
    
    if not logs:
        print("No logs found for this week.")
        return

    # --- PILLAR 1: Raw Forensics ---
    forensics_file = "lorin_audit_forensics.csv"
    with open(forensics_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=logs[0].keys())
        writer.writeheader()
        writer.writerows(logs)

    # --- PILLAR 2: Developer Optimization (Gaps) ---
    optimization_file = "lorin_developer_optimization.csv"
    gaps = [l for l in logs if float(l.get("score", 0)) < 0.3 or l.get("status") == "FAILED"]
    if gaps:
        with open(optimization_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=gaps[0].keys())
            writer.writeheader()
            writer.writerows(gaps)

    # --- PILLAR 3: Institutional ROI ---
    roi_file = "lorin_institutional_benefits.csv"
    total_queries = len(logs)
    success_queries = len([l for l in logs if l.get("status") == "SUCCESS"])
    high_conf = len([l for l in logs if float(l.get("score", 0)) > 0.6])
    
    roi_data = [
        {"Metric": "Total Week Interactions", "Value": total_queries},
        {"Metric": "Human Deflection Rate", "Value": f"{(high_conf/total_queries)*100:.1f}%"},
        {"Metric": "Success Rate", "Value": f"{(success_queries/total_queries)*100:.1f}%"},
        {"Metric": "Estimated Time Saved (Hours)", "Value": f"{(total_queries * 3 / 60):.1f}"},
        {"Metric": "Avg Latency (ms)", "Value": sum(l.get("latency", 0) for l in logs) // total_queries}
    ]
    
    with open(roi_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Metric", "Value"])
        writer.writeheader()
        writer.writerows(roi_data)

    # --- TELEGRAM DISPATCH ---
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    admin_id = "7770158141"
    
    summary = f"""📊 *Sunday Strategic Intelligence Report*
    
🛡️ *Auditor Presence*: {total_queries} Interactions
🛠️ *Optimization*: {len(gaps)} RAG Gaps detected
🏛️ *Institutional ROI*: {(high_conf/total_queries)*100:.1f}% Human Deflection

Triple-Pillar Audit attached below."""

    async with httpx.AsyncClient() as client:
        # Send Summary
        await client.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                         json={"chat_id": admin_id, "text": summary, "parse_mode": "Markdown"})
        
        # Send Files
        for file_path in [forensics_file, optimization_file, roi_file]:
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    await client.post(f"https://api.telegram.org/bot{token}/sendDocument", 
                                     data={"chat_id": admin_id}, 
                                     files={"document": f})
                os.remove(file_path)

if __name__ == "__main__":
    asyncio.run(run_audit())
