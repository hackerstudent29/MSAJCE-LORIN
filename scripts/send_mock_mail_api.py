import os
import httpx
import json
import base64
from dotenv import load_dotenv

load_dotenv()

async def send_lorin_report_with_attachment():
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = "eventbooking.otp@gmail.com"
    receiver_email = "ramzendrum@gmail.com"
    csv_path = os.path.join("data", "sunday_forensic_report.csv")

    if not api_key:
        print("Error: Missing BREVO_API_KEY in .env")
        return

    # Read and Encode CSV
    try:
        with open(csv_path, "rb") as f:
            csv_content = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }

    # HTML Content
    html_content = f"""
    <html>
      <body style="font-family: 'Inter', sans-serif; color: #1F2937; line-height: 1.6; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #E5E7EB; border-radius: 12px;">
        <div style="background: linear-gradient(135deg, #6366F1, #8B5CF6); height: 6px; border-radius: 12px 12px 0 0; margin: -20px -20px 20px -20px;"></div>
        <h1 style="color: #4F46E5; font-size: 24px; font-weight: 700; margin-bottom: 8px;">Forensic Intelligence Report</h1>
        <p style="font-size: 14px; color: #6B7280; margin-bottom: 24px;">Status: <strong>ATTACHMENT INCLUDED (Testing)</strong></p>
        
        <p>Hello Ramanathan,</p>
        
        <p>Attached is the <strong>Sunday Intelligence Forensic Report</strong> containing the latest performance metrics for the Lorin RAG engine. This data includes query categories, confidence scores, and system latency.</p>
        
        <div style="background-color: #F9FAFB; padding: 16px; border-radius: 8px; margin-bottom: 24px;">
          <p style="margin: 0;">📊 <strong>File:</strong> sunday_forensic_report.csv</p>
          <p style="margin: 5px 0 0 0;">🔍 <strong>Rows:</strong> 25 Log Entries</p>
        </div>
        
        <p style="font-size: 14px;">Please review the attached CSV to verify the system's retrieval precision and response speed.</p>
        
        <hr style="border: 0; border-top: 1px solid #F3F4F6; margin: 24px 0;" />
        
        <p style="font-size: 12px; color: #9CA3AF; text-align: center;">
          This is an automated forensic dispatch from the Lorin RAG Engine.<br/>
          &copy; 2026 MSAJCE AI Systems | Developed by Ramanathan S
        </p>
      </body>
    </html>
    """

    payload = {
        "sender": {"name": "Lorin Intelligence", "email": sender_email},
        "to": [{"email": receiver_email, "name": "Ramanathan S"}],
        "subject": "📊 Lorin RAG: Sunday Forensic Report Export",
        "htmlContent": html_content,
        "attachment": [
            {
                "content": csv_content,
                "name": "sunday_forensic_report.csv"
            }
        ]
    }

    try:
        print(f"Sending forensic report with attachment to {receiver_email}...")
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=30.0)
            if response.status_code in [200, 201]:
                print(f"SUCCESS: Forensic report with CSV delivered to {receiver_email}!")
            else:
                print(f"API Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"FAILED to send via API: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(send_lorin_report_with_attachment())
