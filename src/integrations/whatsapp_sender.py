"""
WhatsApp Business API integration for sending reports and summaries.

This module supports:
- Sending text messages (AI summaries) to WhatsApp groups
- Sending CSV files to WhatsApp groups
- Using WhatsApp Business Cloud API (Meta)
"""
import os
import logging
import requests
from typing import List, Optional, Dict, Any
import mimetypes

from src.core.config import app_config

# Configure logger
logging.basicConfig(
    level=getattr(logging, app_config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=app_config.LOG_FILE,
    filemode="a"
)
logger = logging.getLogger(__name__)


class WhatsAppSender:
    """WhatsApp Business API client for sending messages and files."""
    
    def __init__(self, access_token: str = None, phone_number_id: str = None, business_account_id: str = None):
        """Initialize WhatsApp sender.
        
        Args:
            access_token: WhatsApp Business API access token
            phone_number_id: WhatsApp Business phone number ID
            business_account_id: WhatsApp Business Account ID
        """
        self.access_token = access_token or app_config.WHATSAPP_ACCESS_TOKEN
        self.phone_number_id = phone_number_id or app_config.WHATSAPP_PHONE_NUMBER_ID
        self.business_account_id = business_account_id or app_config.WHATSAPP_BUSINESS_ACCOUNT_ID
        
        if not self.access_token:
            raise ValueError("WhatsApp access token is required")
        if not self.phone_number_id:
            raise ValueError("WhatsApp phone number ID is required")
        
        self.api_version = "v18.0"
        self.base_url = f"https://graph.facebook.com/{self.api_version}"
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        logger.info("WhatsApp sender initialized")
    
    def _format_message_for_whatsapp(self, message: str, max_length: int = 4096) -> str:
        """Format and truncate message for WhatsApp.
        
        WhatsApp has a 4096 character limit for text messages.
        
        Args:
            message: Message to format
            max_length: Maximum message length
            
        Returns:
            Formatted message
        """
        if len(message) <= max_length:
            return message
        
        # Truncate and add indicator
        truncated = message[:max_length - 50]
        return f"{truncated}\n\n...(message truncated, see full report in CSV file)"
    
    def send_text_message(self, recipient_id: str, message: str) -> Dict[str, Any]:
        """Send a text message to a WhatsApp recipient (individual or group).
        
        Args:
            recipient_id: WhatsApp recipient ID (phone number or group ID)
            message: Message text to send
            
        Returns:
            API response dictionary
        """
        try:
            # Format message
            formatted_message = self._format_message_for_whatsapp(message)
            
            # Prepare API request
            url = f"{self.base_url}/{self.phone_number_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_id,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": formatted_message
                }
            }
            
            # Send request
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Text message sent to {recipient_id}")
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending text message to {recipient_id}: {str(e)}")
            raise
    
    def upload_media(self, file_path: str) -> str:
        """Upload a file to WhatsApp Business API and get media ID.
        
        Args:
            file_path: Path to the file to upload
            
        Returns:
            Media ID from WhatsApp
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"
            
            # Prepare upload request
            url = f"{self.base_url}/{self.phone_number_id}/media"
            
            # Read file
            with open(file_path, 'rb') as f:
                files = {
                    'file': (os.path.basename(file_path), f, mime_type)
                }
                data = {
                    'messaging_product': 'whatsapp'
                }
                headers = {
                    "Authorization": f"Bearer {self.access_token}"
                }
                
                response = requests.post(url, headers=headers, data=data, files=files)
                response.raise_for_status()
            
            result = response.json()
            media_id = result.get('id')
            
            logger.info(f"File uploaded: {file_path}, Media ID: {media_id}")
            return media_id
            
        except Exception as e:
            logger.error(f"Error uploading file {file_path}: {str(e)}")
            raise
    
    def send_document(self, recipient_id: str, file_path: str, caption: Optional[str] = None) -> Dict[str, Any]:
        """Send a document (CSV, PDF, etc.) to a WhatsApp recipient.
        
        Args:
            recipient_id: WhatsApp recipient ID
            file_path: Path to the document file
            caption: Optional caption for the document
            
        Returns:
            API response dictionary
        """
        try:
            # Upload file first
            media_id = self.upload_media(file_path)
            
            # Prepare message request
            url = f"{self.base_url}/{self.phone_number_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_id,
                "type": "document",
                "document": {
                    "id": media_id,
                    "filename": os.path.basename(file_path)
                }
            }
            
            # Add caption if provided
            if caption:
                payload["document"]["caption"] = caption[:1024]  # WhatsApp caption limit
            
            # Send request
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Document sent to {recipient_id}: {os.path.basename(file_path)}")
            return result
            
        except Exception as e:
            logger.error(f"Error sending document to {recipient_id}: {str(e)}")
            raise
    
    def send_to_multiple_recipients(self, recipient_ids: List[str], message: str = None, 
                                   file_path: str = None, caption: str = None) -> Dict[str, List[str]]:
        """Send message/file to multiple recipients (groups).
        
        Args:
            recipient_ids: List of WhatsApp recipient IDs
            message: Optional text message
            file_path: Optional file path to send
            caption: Optional caption for file
            
        Returns:
            Dictionary with 'success' and 'failed' recipient IDs
        """
        results = {
            "success": [],
            "failed": []
        }
        
        for recipient_id in recipient_ids:
            try:
                # Send text message if provided
                if message:
                    self.send_text_message(recipient_id, message)
                
                # Send file if provided
                if file_path:
                    self.send_document(recipient_id, file_path, caption)
                
                results["success"].append(recipient_id)
                logger.info(f"Successfully sent to {recipient_id}")
                
            except Exception as e:
                logger.error(f"Failed to send to {recipient_id}: {str(e)}")
                results["failed"].append(recipient_id)
        
        return results
    
    def format_ai_summary_for_whatsapp(self, summary_path: str) -> str:
        """Format AI summary CSV content into a WhatsApp-friendly message.
        
        Args:
            summary_path: Path to AI summary CSV file
            
        Returns:
            Formatted message string
        """
        try:
            import csv
            
            message_parts = ["📊 *GitHub Commit Summary*\n"]
            
            with open(summary_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    repo = row.get('Repository', 'Unknown')
                    summary = row.get('Summary', '')
                    
                    if repo and summary:
                        if repo == 'OVERALL SUMMARY':
                            message_parts.append(f"\n*{repo}*\n{summary}\n")
                        else:
                            message_parts.append(f"\n*{repo}:*\n{summary}\n")
            
            full_message = "\n".join(message_parts)
            return self._format_message_for_whatsapp(full_message)
            
        except Exception as e:
            logger.error(f"Error formatting AI summary: {str(e)}")
            return f"Error formatting summary: {str(e)}"
    
    def send_commit_report(self, csv_path: str, summary_path: str = None, 
                          recipient_ids: List[str] = None, date_range: str = "") -> Dict[str, Any]:
        """Send complete commit report to WhatsApp groups.
        
        This method sends both the AI summary (as text) and CSV file (as document).
        
        Args:
            csv_path: Path to main CSV report
            summary_path: Path to AI summary CSV (optional)
            recipient_ids: List of WhatsApp group/recipient IDs
            date_range: Date range string for the report
            
        Returns:
            Results dictionary with success/failure information
        """
        if not recipient_ids:
            recipient_ids = app_config.WHATSAPP_GROUP_IDS
            
        if not recipient_ids:
            logger.warning("No WhatsApp recipients configured")
            return {"success": [], "failed": [], "message": "No recipients configured"}
        
        try:
            # Prepare caption for CSV
            caption = f"GitHub Commit Report - {date_range}" if date_range else "GitHub Commit Report"
            
            # If AI summary exists, send it as formatted text first
            if summary_path and os.path.exists(summary_path):
                ai_message = self.format_ai_summary_for_whatsapp(summary_path)
                
                logger.info(f"Sending AI summary to {len(recipient_ids)} recipients")
                summary_results = self.send_to_multiple_recipients(
                    recipient_ids=recipient_ids,
                    message=ai_message
                )
                
                # Small delay to avoid rate limiting
                import time
                time.sleep(2)
            
            # Send CSV file
            logger.info(f"Sending CSV report to {len(recipient_ids)} recipients")
            csv_results = self.send_to_multiple_recipients(
                recipient_ids=recipient_ids,
                file_path=csv_path,
                caption=caption
            )
            
            return {
                "csv_results": csv_results,
                "summary_sent": summary_path is not None,
                "recipients_count": len(recipient_ids)
            }
            
        except Exception as e:
            logger.error(f"Error sending commit report: {str(e)}")
            raise


def send_whatsapp_report(csv_path: str, summary_path: str = None, date_range: str = "") -> bool:
    """
    Convenience function to send WhatsApp report.
    
    Args:
        csv_path: Path to CSV report
        summary_path: Path to AI summary CSV
        date_range: Date range string
        
    Returns:
        True if successful, False otherwise
    """
    try:
        if not app_config.WHATSAPP_ENABLED:
            logger.info("WhatsApp notifications disabled")
            return False
        
        sender = WhatsAppSender()
        results = sender.send_commit_report(csv_path, summary_path, date_range=date_range)
        
        success_count = len(results.get("csv_results", {}).get("success", []))
        total_count = results.get("recipients_count", 0)
        
        logger.info(f"WhatsApp report sent to {success_count}/{total_count} recipients")
        print(f"\n✅ WhatsApp report sent to {success_count}/{total_count} recipients")
        
        return success_count > 0
        
    except Exception as e:
        logger.error(f"Failed to send WhatsApp report: {str(e)}")
        print(f"\n❌ Failed to send WhatsApp report: {str(e)}")
        return False
