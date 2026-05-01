import os
import asyncio
import httpx
import base64
import json
import csv
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def send_rich_email(to_email, subject, summary_data, attachments):
    brevo_key = os.getenv("BREVO_API_KEY")
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": brevo_key,
        "content-type": "application/json"
    }
    
    # PREMIUM HTML TEMPLATE
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
                
                <div class="metric-card">
                    <span class="metric-label">Human Deflection Rate</span>
                    <span class="badge badge-success">{summary_data['deflection']}</span>
                </div>
                
                <div class="metric-card">
                    <span class="metric-label">Total Weekly Interactions</span>
                    <span class="metric-value">{summary_data['total']}</span>
                </div>

                <div class="metric-card">
                    <span class="metric-label">RAG Optimization Gaps</span>
                    <span class="badge badge-warning">{summary_data['gaps']} DETECTED</span>
                </div>

                <div class="section-title">Auditor Insight</div>
                <p style="font-size: 14px; color: #4B5563;">
                    Lorin is currently maintaining a high success rate across all departments. We have identified several low-confidence queries regarding transport schedules that require re-indexing. 
                    The Triple-Pillar CSV files are attached for your forensic review.
                </p>
            </div>
            <div class="footer">
                © 2026 MSAJCE Lorin Intelligence System<br>
                Lead Architect: Ramanathan S
            </div>
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
                payload["attachment"].append({
                    "content": content,
                    "name": os.path.basename(file_path)
                })
                
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        print(f"Email Status: {response.status_code}")
        print(response.text)

async def test_mock_report():
    # 1. Create Mock CSVs
    mock_files = ["lorin_audit_forensics.csv", "lorin_developer_optimization.csv", "lorin_institutional_benefits.csv"]
    for f in mock_files:
        with open(f, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Mock Header 1", "Mock Header 2"])
            writer.writerow(["Mock Data A", "Mock Data B"])

    # 2. Mock Summary Data
    summary_data = {
        "deflection": "89.4%",
        "total": "426",
        "gaps": "12"
    }

    # 3. Send the Rich Email
    await send_rich_email(
        to_email="ramzendrum@gmail.com",
        subject="📊 TEST: Sunday Strategic Intelligence Report",
        summary_data=summary_data,
        attachments=mock_files
    )

    # 4. Cleanup
    for f in mock_files:
        if os.path.exists(f): os.remove(f)

if __name__ == "__main__":
    asyncio.run(test_mock_report())
