"""
Google Sheets integration for report generation.
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound

from config import app_config

# Configure logger
logging.basicConfig(
    level=getattr(logging, app_config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=app_config.LOG_FILE,
    filemode="a"
)
logger = logging.getLogger(__name__)

# Define the required scopes for Google Sheets
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

class GoogleSheetsClient:
    """Client for interacting with Google Sheets API."""
    
    def __init__(self, credentials_file: str = None):
        """Initialize the Google Sheets client.
        
        Args:
            credentials_file: Path to the Google credentials JSON file.
                If None, uses the file from config.
        """
        self.credentials_file = credentials_file or app_config.GOOGLE_CREDENTIALS_FILE
        
        try:
            # Authenticate with Google Sheets API
            self.credentials = Credentials.from_service_account_file(
                self.credentials_file, scopes=SCOPES
            )
            self.client = gspread.authorize(self.credentials)
            logger.info("Google Sheets client initialized")
        except Exception as e:
            logger.error(f"Error initializing Google Sheets client: {str(e)}")
            raise
    
    def create_spreadsheet(self, title: str) -> gspread.Spreadsheet:
        """Create a new spreadsheet.
        
        Args:
            title: Title of the spreadsheet
            
        Returns:
            Spreadsheet object
        """
        try:
            spreadsheet = self.client.create(title)
            logger.info(f"Created new spreadsheet with title: {title}")
            return spreadsheet
        except APIError as e:
            logger.error(f"Error creating spreadsheet: {str(e)}")
            raise
    
    def get_or_create_spreadsheet(self, title: str) -> gspread.Spreadsheet:
        """Get an existing spreadsheet or create a new one.
        
        Args:
            title: Title of the spreadsheet
            
        Returns:
            Spreadsheet object
        """
        try:
            # Try to find an existing spreadsheet with the given title
            spreadsheet = self.client.open(title)
            logger.info(f"Found existing spreadsheet with title: {title}")
            return spreadsheet
        except SpreadsheetNotFound:
            # Create a new spreadsheet if not found
            logger.info(f"Spreadsheet not found. Creating new one with title: {title}")
            return self.create_spreadsheet(title)
        except APIError as e:
            logger.error(f"Error accessing spreadsheet: {str(e)}")
            raise
    
    def format_header_row(self, worksheet: gspread.Worksheet):
        """Format the header row of the worksheet.
        
        Args:
            worksheet: Worksheet to format
        """
        try:
            # Format header row (bold, background color, freeze)
            worksheet.format('A1:I1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8}
            })
            
            # Freeze header row
            worksheet.freeze(rows=1)
            
            # Auto-resize columns to fit content
            worksheet.columns_auto_resize(0, 8)  # Columns A-I (0-8)
            
            logger.info("Formatted header row")
        except APIError as e:
            logger.error(f"Error formatting header row: {str(e)}")
    
    def generate_report(self, commits_data: List[Dict[str, Any]], month_year: str) -> str:
        """Generate a report in Google Sheets.
        
        Args:
            commits_data: List of commit data dictionaries
            month_year: Month and year for the report title
            
        Returns:
            URL of the created spreadsheet
        """
        try:
            # Create spreadsheet
            title = f"GitHub Commits - {month_year}"
            spreadsheet = self.get_or_create_spreadsheet(title)
            
            # Get the first worksheet or create it if it doesn't exist
            try:
                worksheet = spreadsheet.get_worksheet(0)
                if not worksheet:
                    worksheet = spreadsheet.add_worksheet(title="Commits", rows=1000, cols=20)
                else:
                    # Clear existing data but keep the sheet
                    worksheet.clear()
            except Exception:
                # Create new worksheet if there was an error
                worksheet = spreadsheet.add_worksheet(title="Commits", rows=1000, cols=20)
            
            # Set up header row
            headers = [
                "No.", "Commit Hash", "URL", "Commit Message", 
                "Date Time", "Username", "Repo Name", 
                "AI Summary", "Change Type"
            ]
            worksheet.append_row(headers)
            
            # Format header row
            self.format_header_row(worksheet)
            
            # Sort commits by date (oldest to newest)
            sorted_commits = sorted(
                commits_data, 
                key=lambda x: x["date_time"] if isinstance(x["date_time"], datetime) else datetime.now()
            )
            
            # Add commit data rows
            for idx, commit in enumerate(sorted_commits, 1):
                # Format datetime
                date_time_str = commit["date_time"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(commit["date_time"], datetime) else str(commit["date_time"])
                
                # Prepare row data
                row_data = [
                    idx,  # Serial number
                    commit["sha"],  # Commit hash
                    commit["url"],  # URL
                    commit["message"],  # Commit message
                    date_time_str,  # Date time
                    commit["username"],  # Username
                    commit["repo_name"],  # Repository name
                    commit.get("ai_summary", ""),  # AI summary
                    commit.get("change_type", "")  # Change type
                ]
                
                # Append row to worksheet
                worksheet.append_row(row_data)
                
                # Apply hyperlink to URL column
                worksheet.update_cell(idx + 1, 3, f'=HYPERLINK("{commit["url"]}", "{commit["url"]}")')
                
                # Format long text columns for better readability
                worksheet.format(f'D{idx + 1}', {'wrapStrategy': 'WRAP'})
                worksheet.format(f'H{idx + 1}', {'wrapStrategy': 'WRAP'})
            
            # Resize columns to fit content
            try:
                worksheet.columns_auto_resize(0, 8)  # Columns A-I (0-8)
            except Exception as e:
                logger.warning(f"Could not auto-resize columns: {str(e)}")
            
            # Share the spreadsheet with the recipient
            if app_config.EMAIL_RECIPIENT:
                spreadsheet.share(app_config.EMAIL_RECIPIENT, perm_type='user', role='reader')
            
            logger.info(f"Generated report with {len(sorted_commits)} commits")
            
            return spreadsheet.url
            
        except Exception as e:
            logger.error(f"Error generating report: {str(e)}")
            raise
    
    def create_repository_sheets(self, commits_data: List[Dict[str, Any]], month_year: str) -> str:
        """Create separate sheets for each repository.
        
        Args:
            commits_data: List of commit data dictionaries
            month_year: Month and year for the report title
            
        Returns:
            URL of the spreadsheet
        """
        try:
            # Create spreadsheet
            title = f"GitHub Commits - {month_year}"
            spreadsheet = self.get_or_create_spreadsheet(title)
            
            # Get unique repository names
            repo_names = set(commit["repo_name"] for commit in commits_data)
            
            # Create "All Commits" sheet first
            all_commits_sheet = None
            try:
                # Check if "All Commits" sheet exists
                all_commits_sheet = spreadsheet.worksheet("All Commits")
                all_commits_sheet.clear()
            except gspread.exceptions.WorksheetNotFound:
                # Create new sheet if it doesn't exist
                all_commits_sheet = spreadsheet.add_worksheet(title="All Commits", rows=1000, cols=20)
            
            # Set up header row for "All Commits" sheet
            headers = [
                "No.", "Commit Hash", "URL", "Commit Message", 
                "Date Time", "Username", "Repo Name", 
                "AI Summary", "Change Type"
            ]
            all_commits_sheet.append_row(headers)
            
            # Format header row
            self.format_header_row(all_commits_sheet)
            
            # Sort all commits by date (oldest to newest)
            sorted_all_commits = sorted(
                commits_data, 
                key=lambda x: x["date_time"] if isinstance(x["date_time"], datetime) else datetime.now()
            )
            
            # Add commit data to "All Commits" sheet
            for idx, commit in enumerate(sorted_all_commits, 1):
                # Format datetime
                date_time_str = commit["date_time"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(commit["date_time"], datetime) else str(commit["date_time"])
                
                # Prepare row data
                row_data = [
                    idx,
                    commit["sha"],
                    commit["url"],
                    commit["message"],
                    date_time_str,
                    commit["username"],
                    commit["repo_name"],
                    commit.get("ai_summary", ""),
                    commit.get("change_type", "")
                ]
                
                # Append row to worksheet
                all_commits_sheet.append_row(row_data)
                
                # Apply hyperlink to URL column
                all_commits_sheet.update_cell(idx + 1, 3, f'=HYPERLINK("{commit["url"]}", "{commit["sha"][:7]}")')
                
                # Format long text columns
                all_commits_sheet.format(f'D{idx + 1}', {'wrapStrategy': 'WRAP'})
                all_commits_sheet.format(f'H{idx + 1}', {'wrapStrategy': 'WRAP'})
            
            # Create separate sheets for each repository
            for repo_name in repo_names:
                # Filter commits for this repository
                repo_commits = [commit for commit in commits_data if commit["repo_name"] == repo_name]
                
                # Sort commits by date
                sorted_repo_commits = sorted(
                    repo_commits, 
                    key=lambda x: x["date_time"] if isinstance(x["date_time"], datetime) else datetime.now()
                )
                
                # Create or get worksheet for this repository
                repo_sheet_name = repo_name.split('/')[-1]  # Just use the repo name, not org/repo
                repo_sheet = None
                
                try:
                    # Check if sheet already exists
                    repo_sheet = spreadsheet.worksheet(repo_sheet_name)
                    repo_sheet.clear()
                except gspread.exceptions.WorksheetNotFound:
                    # Create new sheet if it doesn't exist
                    repo_sheet = spreadsheet.add_worksheet(title=repo_sheet_name, rows=len(sorted_repo_commits) + 10, cols=20)
                
                # Add header row
                repo_sheet.append_row(headers)
                
                # Format header row
                self.format_header_row(repo_sheet)
                
                # Add commit data
                for idx, commit in enumerate(sorted_repo_commits, 1):
                    # Format datetime
                    date_time_str = commit["date_time"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(commit["date_time"], datetime) else str(commit["date_time"])
                    
                    # Prepare row data
                    row_data = [
                        idx,
                        commit["sha"],
                        commit["url"],
                        commit["message"],
                        date_time_str,
                        commit["username"],
                        commit["repo_name"],
                        commit.get("ai_summary", ""),
                        commit.get("change_type", "")
                    ]
                    
                    # Append row to worksheet
                    repo_sheet.append_row(row_data)
                    
                    # Apply hyperlink to URL column
                    repo_sheet.update_cell(idx + 1, 3, f'=HYPERLINK("{commit["url"]}", "{commit["sha"][:7]}")')
                    
                    # Format long text columns
                    repo_sheet.format(f'D{idx + 1}', {'wrapStrategy': 'WRAP'})
                    repo_sheet.format(f'H{idx + 1}', {'wrapStrategy': 'WRAP'})
                
                logger.info(f"Created sheet for repository {repo_name} with {len(sorted_repo_commits)} commits")
            
            # Resize columns in all sheets
            worksheets = spreadsheet.worksheets()
            for worksheet in worksheets:
                try:
                    worksheet.columns_auto_resize(0, 8)  # Columns A-I (0-8)
                except Exception as e:
                    logger.warning(f"Could not auto-resize columns in sheet {worksheet.title}: {str(e)}")
            
            # Return URL of the spreadsheet
            return spreadsheet.url
            
        except Exception as e:
            logger.error(f"Error creating repository sheets: {str(e)}")
            raise
