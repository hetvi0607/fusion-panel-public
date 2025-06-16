"""
CSV reporter for generating commit reports.
"""
import os
import csv
import logging
from typing import List, Dict, Any
from datetime import datetime

from config import app_config

# Configure logger
logging.basicConfig(
    level=getattr(logging, app_config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=app_config.LOG_FILE,
    filemode="a"
)
logger = logging.getLogger(__name__)


class CSVReporter:
    """Reporter for generating CSV files with commit data."""
    
    def __init__(self, output_dir: str = None):
        """Initialize the CSV reporter.
        
        Args:
            output_dir: Directory where CSV files will be saved.
                If None, uses the project root directory.
        """
        self.output_dir = output_dir or os.path.dirname(os.path.abspath(__file__))
        logger.info(f"CSV reporter initialized with output directory: {self.output_dir}")
    
    def create_repository_reports(self, commits_data: List[Dict[str, Any]], month_year: str) -> str:
        """Create separate CSV reports for each repository.
        
        Args:
            commits_data: List of commit data dictionaries
            month_year: Month and year for the report title
            
        Returns:
            Path to the main CSV file
        """
        try:
            # Define the CSV headers
            headers = [
                "No.", "Commit Hash", "URL", "Commit Message", 
                "Date Time", "Username", "Repository", 
                "AI Summary", "Change Type"
            ]
            
            # Create a filename based on month and year
            filename_base = f"github_commits_{month_year.replace(' ', '_').lower()}"
            main_csv_path = os.path.join(self.output_dir, f"{filename_base}.csv")
            
            # Sort all commits by date (oldest to newest)
            sorted_all_commits = sorted(
                commits_data, 
                key=lambda x: x["date_time"] if isinstance(x["date_time"], datetime) else datetime.now()
            )
            
            # Write all commits to the main CSV file
            with open(main_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)
                
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
                    
                    writer.writerow(row_data)
            
            logger.info(f"Created main CSV file with {len(sorted_all_commits)} commits: {main_csv_path}")
            
            # Get unique repository names
            repo_names = set(commit["repo_name"] for commit in commits_data)
            
            # Create separate CSV files for each repository
            for repo_name in repo_names:
                # Filter commits for this repository
                repo_commits = [commit for commit in commits_data if commit["repo_name"] == repo_name]
                
                # Sort commits by date
                sorted_repo_commits = sorted(
                    repo_commits, 
                    key=lambda x: x["date_time"] if isinstance(x["date_time"], datetime) else datetime.now()
                )
                
                # Create a filename based on repository name and month
                repo_filename = repo_name.replace('/', '_')
                repo_csv_path = os.path.join(self.output_dir, f"{filename_base}_{repo_filename}.csv")
                
                # Write repository commits to a separate CSV file
                with open(repo_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(headers)
                    
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
                        
                        writer.writerow(row_data)
                
                logger.info(f"Created repository CSV file for {repo_name} with {len(sorted_repo_commits)} commits: {repo_csv_path}")
            
            # Return path to the main CSV file
            return main_csv_path
            
        except Exception as e:
            logger.error(f"Error creating CSV reports: {str(e)}")
            raise
