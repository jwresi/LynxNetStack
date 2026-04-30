"""
Notifications Service for Email and Slack integrations
Handles user invitations and system notifications
"""

import smtplib
import json
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import requests
import secrets
import string

class NotificationService:
    def __init__(self, db: Session, company_id: int):
        self.db = db
        self.company_id = company_id
        self.logger = logging.getLogger(__name__)
        
        # Load company notification settings
        self.email_settings = {}
        self.slack_settings = {}
        self._load_settings()
    
    def _load_settings(self):
        """Load notification settings from company configuration"""
        try:
            from ..database import CompanySetting
            
            settings = self.db.query(CompanySetting).filter(
                CompanySetting.company_id == self.company_id,
                CompanySetting.category == 'notifications'
            ).all()
            
            for setting in settings:
                if setting.setting_key.startswith('email_'):
                    key = setting.setting_key.replace('email_', '')
                    self.email_settings[key] = setting.setting_value
                elif setting.setting_key.startswith('slack_'):
                    key = setting.setting_key.replace('slack_', '')
                    self.slack_settings[key] = setting.setting_value
                    
        except Exception as e:
            self.logger.warning(f"Could not load notification settings: {e}")
    
    def send_email(self, to_email: str, subject: str, body: str, html_body: Optional[str] = None) -> bool:
        """Send email using configured SMTP settings"""
        try:
            if not all([
                self.email_settings.get('smtp_server'),
                self.email_settings.get('username'),
                self.email_settings.get('password')
            ]):
                self.logger.error("Email settings not configured")
                return False
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.email_settings['username']
            msg['To'] = to_email
            
            # Add plain text part
            text_part = MIMEText(body, 'plain')
            msg.attach(text_part)
            
            # Add HTML part if provided
            if html_body:
                html_part = MIMEText(html_body, 'html')
                msg.attach(html_part)
            
            # Send email
            smtp_port = int(self.email_settings.get('smtp_port', 587))
            server = smtplib.SMTP(self.email_settings['smtp_server'], smtp_port)
            server.starttls()
            server.login(self.email_settings['username'], self.email_settings['password'])
            
            text = msg.as_string()
            server.sendmail(self.email_settings['username'], to_email, text)
            server.quit()
            
            self.logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    def send_slack_message(self, message: str, channel: Optional[str] = None) -> bool:
        """Send message to Slack using webhook"""
        try:
            webhook_url = self.slack_settings.get('webhook_url')
            if not webhook_url:
                self.logger.error("Slack webhook URL not configured")
                return False
            
            payload = {
                'text': message,
                'username': 'LynxMSP',
                'icon_emoji': ':robot_face:'
            }
            
            if channel:
                payload['channel'] = channel
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                self.logger.info("Slack message sent successfully")
                return True
            else:
                self.logger.error(f"Slack API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to send Slack message: {e}")
            return False
    
    def generate_invitation_token(self, length: int = 32) -> str:
        """Generate secure random token for invitations"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    def send_user_invitation(self, email: str, role: str = 'user', invited_by: str = 'System') -> Dict[str, Any]:
        """Send user invitation via email and/or Slack"""
        try:
            from ..database import User, Company
            
            # Check if user already exists
            existing_user = self.db.query(User).filter(User.email == email).first()
            if existing_user:
                return {
                    'success': False,
                    'message': 'User with this email already exists'
                }
            
            # Get company information
            company = self.db.query(Company).filter(Company.id == self.company_id).first()
            if not company:
                return {
                    'success': False,
                    'message': 'Company not found'
                }
            
            # Generate invitation token
            invitation_token = self.generate_invitation_token()
            
            # Store invitation in database (you would need to create an Invitation model)
            # For now, we'll just proceed with sending the email
            
            # Prepare email content
            subject = f"Invitation to join {company.name} on LynxMSP"
            
            # Plain text email body
            text_body = f"""
Hello!

You have been invited by {invited_by} to join {company.name} on LynxMSP.

Role: {role.title()}

To accept this invitation and create your account, please click the link below:
https://your-lynx-domain.com/invite/{invitation_token}

This invitation will expire in 7 days.

If you have any questions, please contact your system administrator.

Best regards,
LynxMSP Team
            """.strip()
            
            # HTML email body
            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #2196F3; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; background-color: #f9f9f9; }}
        .button {{ 
            display: inline-block; 
            background-color: #4CAF50; 
            color: white; 
            padding: 12px 24px; 
            text-decoration: none; 
            border-radius: 4px; 
            margin: 20px 0;
        }}
        .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>You're Invited to LynxMSP!</h1>
        </div>
        <div class="content">
            <p>Hello!</p>
            <p>You have been invited by <strong>{invited_by}</strong> to join <strong>{company.name}</strong> on LynxMSP.</p>
            <p><strong>Role:</strong> {role.title()}</p>
            <p>To accept this invitation and create your account, please click the button below:</p>
            <a href="https://your-lynx-domain.com/invite/{invitation_token}" class="button">Accept Invitation</a>
            <p>This invitation will expire in 7 days.</p>
            <p>If you have any questions, please contact your system administrator.</p>
        </div>
        <div class="footer">
            <p>LynxMSP - Comprehensive ISP/MSP/WISP Management Platform</p>
        </div>
    </div>
</body>
</html>
            """.strip()
            
            # Send email invitation
            email_sent = self.send_email(email, subject, text_body, html_body)
            
            # Send Slack notification if configured
            slack_sent = False
            if self.slack_settings.get('webhook_url'):
                slack_message = f"📧 User invitation sent to {email} for {company.name} (Role: {role})"
                slack_sent = self.send_slack_message(slack_message)
            
            return {
                'success': email_sent,
                'email_sent': email_sent,
                'slack_sent': slack_sent,
                'invitation_token': invitation_token,
                'expires_at': (datetime.utcnow() + timedelta(days=7)).isoformat(),
                'message': 'Invitation sent successfully' if email_sent else 'Failed to send invitation email'
            }
            
        except Exception as e:
            self.logger.error(f"Error sending user invitation: {e}")
            return {
                'success': False,
                'message': f'Error sending invitation: {str(e)}'
            }
    
    def send_system_notification(self, message: str, notification_type: str = 'info') -> bool:
        """Send system notification to configured channels"""
        try:
            # Send to Slack if configured
            slack_sent = False
            if self.slack_settings.get('webhook_url'):
                emoji_map = {
                    'info': ':information_source:',
                    'warning': ':warning:',
                    'error': ':x:',
                    'success': ':white_check_mark:'
                }
                
                emoji = emoji_map.get(notification_type, ':robot_face:')
                slack_message = f"{emoji} {message}"
                slack_sent = self.send_slack_message(slack_message)
            
            # Could add email notifications to admins here
            
            return slack_sent
            
        except Exception as e:
            self.logger.error(f"Error sending system notification: {e}")
            return False
    
    def test_email_configuration(self) -> Dict[str, Any]:
        """Test email configuration by sending a test email"""
        try:
            if not self.email_settings.get('username'):
                return {
                    'success': False,
                    'message': 'Email configuration incomplete'
                }
            
            test_email = self.email_settings['username']  # Send to self
            subject = "LynxMSP Email Configuration Test"
            body = f"""
This is a test email from LynxMSP to verify your email configuration.

Configuration Details:
- SMTP Server: {self.email_settings.get('smtp_server', 'Not configured')}
- SMTP Port: {self.email_settings.get('smtp_port', 'Not configured')}
- Username: {self.email_settings.get('username', 'Not configured')}

Time: {datetime.utcnow().isoformat()}

If you received this email, your email configuration is working correctly!
            """.strip()
            
            success = self.send_email(test_email, subject, body)
            
            return {
                'success': success,
                'message': 'Test email sent successfully' if success else 'Failed to send test email',
                'test_email': test_email
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Email test failed: {str(e)}'
            }
    
    def test_slack_configuration(self) -> Dict[str, Any]:
        """Test Slack configuration by sending a test message"""
        try:
            if not self.slack_settings.get('webhook_url'):
                return {
                    'success': False,
                    'message': 'Slack webhook URL not configured'
                }
            
            test_message = f"🧪 LynxMSP Slack integration test - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            success = self.send_slack_message(test_message)
            
            return {
                'success': success,
                'message': 'Test message sent to Slack successfully' if success else 'Failed to send test message to Slack'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Slack test failed: {str(e)}'
            }

def create_notification_service(db: Session, company_id: int) -> NotificationService:
    """Factory function to create a NotificationService instance"""
    return NotificationService(db, company_id)