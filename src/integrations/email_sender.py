"""
Email notification module for sending reports.
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Any, Optional

from src.core.config import app_config

# Configure logger
logging.basicConfig(
    level=getattr(logging, app_config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=app_config.LOG_FILE,
    filemode="a"
)
logger = logging.getLogger(__name__)


class EmailSender:
    """Email sender for report delivery."""
    
    def __init__(self, sender_email: str = None, password: str = None,
                 smtp_server: str = None, smtp_port: int = None):
        """Initialize the email sender.
        
        Args:
            sender_email: Sender email address. If None, uses the email from config.
            password: Sender email password. If None, uses the password from config.
            smtp_server: SMTP server address. If None, uses the server from config.
            smtp_port: SMTP server port. If None, uses the port from config.
        """
        self.sender_email = sender_email or app_config.EMAIL_SENDER
        self.password = password or app_config.EMAIL_PASSWORD
        self.smtp_server = smtp_server or app_config.SMTP_SERVER
        self.smtp_port = smtp_port or app_config.SMTP_PORT
        
        # Validate required fields
        if not all([self.sender_email, self.password, self.smtp_server, self.smtp_port]):
            missing_fields = []
            if not self.sender_email:
                missing_fields.append("sender_email")
            if not self.password:
                missing_fields.append("password")
            if not self.smtp_server:
                missing_fields.append("smtp_server")
            if not self.smtp_port:
                missing_fields.append("smtp_port")
            
            error_msg = f"Missing required email configuration: {', '.join(missing_fields)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info("Email sender initialized")
    
    def send_email(self, recipient: str, subject: str, body: str,
                  spreadsheet_url: str, report_stats: Dict[str, Any]) -> bool:
        """Send an email with the report summary and spreadsheet link.
        
        Args:
            recipient: Recipient email address
            subject: Email subject
            body: Custom email body text
            spreadsheet_url: URL of the Google Sheets report
            report_stats: Dictionary with report statistics
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            # Create message
            message = MIMEMultipart()
            message["From"] = self.sender_email
            message["To"] = recipient
            message["Subject"] = subject
            
            # Add custom body text
            if body:
                message.attach(MIMEText(body + "\n\n", "plain"))
            
            # Add report statistics
            stats_text = self._format_report_stats(report_stats)
            message.attach(MIMEText(stats_text + "\n\n", "plain"))
            
            # Add spreadsheet link
            link_text = f"View the full report here: {spreadsheet_url}"
            message.attach(MIMEText(link_text, "plain"))
            
            # Connect to SMTP server and send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()  # Secure the connection
                server.login(self.sender_email, self.password)
                server.send_message(message)
            
            logger.info(f"Email sent to {recipient}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return False
    
    def _format_report_stats(self, stats: Dict[str, Any]) -> str:
        """Format report statistics for email body.
        
        Args:
            stats: Dictionary with report statistics
            
        Returns:
            Formatted statistics text
        """
        # Extract statistics
        total_commits = stats.get("total_commits", 0)
        num_repos = stats.get("num_repositories", 0)
        date_range = stats.get("date_range", "")
        ai_processed = stats.get("ai_processed", 0)
        ai_failed = stats.get("ai_failed", 0)
        change_type_counts = stats.get("change_type_counts", {})
        
        # Format statistics text
        text = "Report Summary:\n"
        text += f"- Total commits: {total_commits}\n"
        text += f"- Repositories processed: {num_repos}\n"
        text += f"- Date range: {date_range}\n"
        
        # Add AI statistics if available
        if "ai_processed" in stats:
            text += "\nAI Analysis Statistics:\n"
            text += f"- Commits processed with AI: {ai_processed}\n"
            text += f"- AI analysis failures: {ai_failed}\n"
            
            # Add change type breakdown if available
            if change_type_counts:
                text += "\nChange Type Breakdown:\n"
                for change_type, count in sorted(change_type_counts.items(), key=lambda x: x[1], reverse=True):
                    percentage = (count / total_commits) * 100 if total_commits > 0 else 0
                    text += f"- {change_type}: {count} ({percentage:.1f}%)\n"
        
        # Add any notable observations or issues
        if "observations" in stats and stats["observations"]:
            text += "\nNotable Observations:\n"
            for observation in stats["observations"]:
                text += f"- {observation}\n"
        
        return text
