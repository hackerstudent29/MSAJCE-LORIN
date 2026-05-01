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

import base64

async def send_email(to_email, subject, summary_data, attachments):
    brevo_key = os.getenv("BREVO_API_KEY")
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": brevo_key,
        "content-type": "application/json"
    }
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Inter', -apple-system, sans-serif; line-height: 1.6; color: #1F2937; background-color: #F9FAFB; margin: 0; padding: 0; }}
            .container {{ max-width: 600px; margin: 20px auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }}
            .header {{ background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%); padding: 32px; text-align: center; color: white; }}
            .header h1 {{ margin: 0; font-size: 24px; font-weight: 700; letter-spacing: -0.025em; }}
            .content {{ padding: 32px; }}
            .metric-card {{ background: #F3F4F6; border-radius: 8px; padding: 16px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }}
            .metric-label {{ font-size: 14px; font-weight: 600; color: #4B5563; }}
            .metric-value {{ font-size: 18px; font-weight: 700; color: #111827; }}
            .badge {{ padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 600; text-transform: uppercase; }}
            .badge-success {{ background: #DEF7EC; color: #03543F; }}
            .badge-warning {{ background: #FEF3C7; color: #92400E; }}
            .footer {{ background: #F9FAFB; padding: 24px; text-align: center; font-size: 12px; color: #6B7280; border-top: 1px solid #E5E7EB; }}
            .section-title {{ font-size: 16px; font-weight: 700; margin-bottom: 12px; color: #374151; border-left: 4px solid #6366F1; padding-left: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Sunday Strategic Intelligence</h1>
                <p style="margin-top: 8px; opacity: 0.9;">Triple-Pillar Forensic Audit</p>
            </div>
            <div class="content">
                <div class="section-title">Institutional ROI & Performance</div>
                <div class="metric-card"><span class="metric-label">Human Deflection Rate</span><span class="badge badge-success">{summary_data['deflection']}</span></div>
                <div class="metric-card"><span class="metric-label">Total Weekly Interactions</span><span class="metric-value">{summary_data['total']}</span></div>
                <div class="metric-card"><span class="metric-label">RAG Optimization Gaps</span><span class="badge badge-warning">{summary_data['gaps']} DETECTED</span></div>
                <div class="section-title">Auditor Insight</div>
                <p style="font-size: 14px; color: #4B5563;">
                    Lorin's institutional brain is currently maintaining stable deflection. Check the 'Developer Optimization' pillar for low-score queries that require immediate re-indexing.
                </p>
            </div>
            <div class="footer">© 2026 MSAJCE Lorin Intelligence System | Lead Architect: Ramanathan S</div>
        </div>
    </body>
    </html>
    """
    
    payload = {
        "sender": {"name": "Lorin Auditor", "email": "a105fc001@smtp-brevo.com"},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
        "attachment": []
    }
    
    for file_path in attachments:
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                content = base64.b64encode(f.read()).decode("utf-8")
                payload["attachment"].append({"content": content, "name": os.path.basename(file_path)})
                
    async with httpx.AsyncClient() as client:
        await client.post(url, headers=headers, json=payload)

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
    high_conf = len([l for l in logs if float(l.get("score", 0)) > 0.6])
    
    roi_data = [
        {"Metric": "Total Week Interactions", "Value": total_queries},
        {"Metric": "Human Deflection Rate", "Value": f"{(high_conf/total_queries)*100:.1f}%"},
        {"Metric": "Estimated Time Saved (Hours)", "Value": f"{(total_queries * 3 / 60):.1f}"},
        {"Metric": "Avg Latency (ms)", "Value": sum(l.get("latency", 0) for l in logs) // total_queries}
    ]
    
    with open(roi_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Metric", "Value"])
        writer.writeheader()
        writer.writerows(roi_data)

    # --- DISPATCH ---
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    admin_id = "7770158141"
    
    summary_data = {
        "deflection": f"{(high_conf/total_queries)*100:.1f}%",
        "total": str(total_queries),
        "gaps": str(len(gaps))
    }

    tg_summary = f"""📊 *Sunday Strategic Intelligence Report*
    
🛡️ *Auditor Presence*: {total_queries} Interactions
🛠️ *Optimization*: {len(gaps)} RAG Gaps detected
🏛️ *Institutional ROI*: {summary_data['deflection']} Human Deflection

Triple-Pillar Audit dispatched via Email and Telegram."""

    # 1. Telegram Dispatch
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                         json={"chat_id": admin_id, "text": tg_summary, "parse_mode": "Markdown"})
        for file_path in [forensics_file, optimization_file, roi_file]:
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    await client.post(f"https://api.telegram.org/bot{token}/sendDocument", data={"chat_id": admin_id}, files={"document": f})

    # 2. Email Dispatch (Brevo)
    await send_email(
        to_email="ramzendrum@gmail.com",
        subject="📊 Sunday Strategic Intelligence Report: Triple-Pillar Architecture",
        summary_data=summary_data,
        attachments=[forensics_file, optimization_file, roi_file]
    )

    # Cleanup
    for file_path in [forensics_file, optimization_file, roi_file]:
        if os.path.exists(file_path): os.remove(file_path)

    # Cleanup
    for file_path in [forensics_file, optimization_file, roi_file]:
        if os.path.exists(file_path):
            os.remove(file_path)

if __name__ == "__main__":
    asyncio.run(run_audit())
