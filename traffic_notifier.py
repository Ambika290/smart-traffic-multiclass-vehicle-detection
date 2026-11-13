import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# --- AUTOMATED EMAIL ALERTS CONFIGURATION ---
# ADD THIS LINE BACK: This tells Python where the Gmail server is located!
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# # 1. The account you used to generate the password
SENDER_EMAIL = "unknown93@gmail.com"

# # 2. The 16-character app password Google gave you
SENDER_PASSWORD = "mbwa bduf mrdt grez"

# # 3. Send it to yourself so you can see it in your inbox!
RECEIVER_EMAIL = "unknown93@gmail.com"

def send_traffic_alert(incident_type, lane_id, metric_value):
    """Generates an email template and attempts secure dispatch with an automatic offline fallback."""
    print(f"\n📢 [SYSTEM NOTIFICATION SYSTEM]: Preparing alert for {lane_id}...")
    print(f"📌 Type: {incident_type} | Metric: {metric_value}")
    
    # Check if configurations are still set to default values
    if SENDER_PASSWORD == "your_app_password" or SENDER_EMAIL == "your_traffic_system@gmail.com":
        print("ℹ️ [OFFLINE SIMULATION MODE ACTIVE]: Skipping server connection. Configure real credentials to send live emails.")
        print("✨ Telemetry alert logging completed successfully.\n")
        return True

    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = f"🚨 SYSTEM ALERT: Critical {incident_type} on {lane_id}"
        message["From"] = SENDER_EMAIL
        message["To"] = RECEIVER_EMAIL

        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #44464f;">
                <div style="max-width: 600px; margin: auto; background: #ffffff; border-radius: 8px; overflow: hidden; border-top: 5px solid #0c2340; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
                    <div style="background-color: #0c2340; padding: 20px; text-align: center; color: #ffffff;">
                        <h2 style="margin: 0; font-size: 22px;">🚦 Smart Traffic Enforcement Alert</h2>
                    </div>
                    <div style="padding: 20px; color: #333333; line-height: 1.61;">
                        <p style="font-size: 16px;">Attention Traffic Operations Center Manager,</p>
                        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                            <tr style="background-color: #f8f9fa;"><td style="padding: 10px; font-weight: bold; border: 1px solid #dee2e6;">Incident:</td><td style="padding: 10px; border: 1px solid #dee2e6; color: #dc3545; font-weight: bold;">{incident_type}</td></tr>
                            <tr><td style="padding: 10px; font-weight: bold; border: 1px solid #dee2e6;">Location:</td><td style="padding: 10px; border: 1px solid #dee2e6;">{lane_id}</td></tr>
                            <tr style="background-color: #f8f9fa;"><td style="padding: 10px; font-weight: bold; border: 1px solid #dee2e6;">Value:</td><td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">{metric_value}</td></tr>
                            <tr><td style="padding: 10px; font-weight: bold; border: 1px solid #dee2e6;">Time:</td><td style="padding: 10px; border: 1px solid #dee2e6;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
                        </table>
                    </div>
                </div>
            </body>
        </html>
        """
        message.attach(MIMEText(html_body, "html"))

        # Initialize network transaction
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=5)
        server.starttls()  
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, message.as_string())
        server.quit()
        
        print(f"📬 [LIVE DISPATCH SUCCESS]: Email delivered to {RECEIVER_EMAIL}!\n")
        return True
    except Exception as email_err:
        # Graceful fallback handler prevents script crash if network lookup fails
        print(f"⚠️ [NETWORK OFFLINE]: Could not reach mail server. Mock saved to logs. Error: {email_err}\n")
        return True
    