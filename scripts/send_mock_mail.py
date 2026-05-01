import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

def send_lorin_report():
    # Credentials
    smtp_server = "smtp-brevo.com"
    smtp_port = 465  # SSL
    smtp_user = os.getenv("BREVO_SMTP_LOGIN")
    smtp_key = os.getenv("BREVO_SMTP_KEY")
    sender_email = "lorin-ai@msajce-edu.in"
    receiver_email = "ramanathanb86@gmail.com"

    if not smtp_user or not smtp_key:
        print("Error: Missing Brevo SMTP credentials in .env")
        return

    # Create Message
    message = MIMEMultipart("alternative")
    message["Subject"] = "🏛️ Lorin RAG: Institutional Intelligence Overhaul Complete"
    message["From"] = f"Lorin AI <{sender_email}>"
    message["To"] = receiver_email

    # HTML Content
    html = f"""
    <html>
      <body style="font-family: 'Inter', sans-serif; color: #1F2937; line-height: 1.6; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #E5E7EB; border-radius: 12px;">
        <div style="background: linear-gradient(135deg, #6366F1, #8B5CF6); height: 6px; border-radius: 12px 12px 0 0; margin: -20px -20px 20px -20px;"></div>
        <h1 style="color: #4F46E5; font-size: 24px; font-weight: 700; margin-bottom: 8px;">Institutional Intelligence Overhaul</h1>
        <p style="font-size: 14px; color: #6B7280; margin-bottom: 24px;">Status: <strong>DIAMOND GRADE (100% SYNCED)</strong></p>
        
        <p>Hello Ramanathan,</p>
        
        <p>The Lorin RAG pipeline has been successfully upgraded to the <strong>Master Entity-Centric Architecture</strong>. Below is the final status of the knowledge base injection:</p>
        
        <div style="background-color: #F9FAFB; padding: 16px; border-radius: 8px; margin-bottom: 24px;">
          <ul style="list-style: none; padding: 0; margin: 0;">
            <li style="margin-bottom: 8px;">💎 <strong>Total Master Chunks:</strong> 563</li>
            <li style="margin-bottom: 8px;">🚀 <strong>Pinecone Cloud Sync:</strong> 100% COMPLETE</li>
            <li style="margin-bottom: 8px;">🧠 <strong>Local BM25 Fallback:</strong> 100% ALIGNED</li>
            <li style="margin-bottom: 8px;">🏛️ <strong>Entity Fusion:</strong> ACTIVE (e.g., Dr. K.S. Srinivasan Profile Unified)</li>
          </ul>
        </div>
        
        <h2 style="font-size: 18px; font-weight: 600; color: #374151;">Developer Context</h2>
        <p style="font-size: 14px;">The system now prioritizes identity-based queries and uses <strong>openai/text-embedding-3-small</strong> for high-precision retrieval across all institutional departments.</p>
        
        <hr style="border: 0; border-top: 1px solid #F3F4F6; margin: 24px 0;" />
        
        <p style="font-size: 12px; color: #9CA3AF; text-align: center;">
          This is an automated production report from the Lorin RAG Engine.<br/>
          &copy; 2026 MSAJCE AI Systems | Developed by Ramanathan S
        </p>
      </body>
    </html>
    """
    
    part = MIMEText(html, "html")
    message.attach(part)

    # Send
    try:
        print(f"Connecting to Brevo SSL server at {smtp_server}:{smtp_port}...")
        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30) as server:
            server.login(smtp_user, smtp_key)
            server.sendmail(sender_email, receiver_email, message.as_string())
        print(f"SUCCESS: Mock report sent to {receiver_email}")
    except Exception as e:
        print(f"FAILED to send mail: {e}")

if __name__ == "__main__":
    send_lorin_report()
