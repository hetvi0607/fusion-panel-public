"""
CSV reporter for generating commit reports.
"""
import os
import csv
import logging
from typing import List, Dict, Any
from datetime import datetime

from src.core.config import app_config

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
                If None, uses data/reports in the project root directory.
        """
        if output_dir is None:
            # Default to data/reports relative to project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            output_dir = os.path.join(project_root, "data", "reports")
        self.output_dir = output_dir
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
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
                "Date Time", "Username", "Repository", "Branch"
            ]
            
            # Create a filename based on month and year
            filename_base = f"{month_year.replace(' ', '_').lower()}"
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
                        commit.get("branch", "default")
                    ]
                    
                    writer.writerow(row_data)
            
            logger.info(f"Created main CSV file with {len(sorted_all_commits)} commits: {main_csv_path}")
            
            # Get unique repository + branch combinations
            repo_branch_combos = set((commit["repo_name"], commit.get("branch", "default")) for commit in commits_data)
            
            # Create separate CSV files for each repository + branch combination
            for repo_name, branch in repo_branch_combos:
                # Filter commits for this repository and branch
                repo_commits = [
                    commit for commit in commits_data 
                    if commit["repo_name"] == repo_name and commit.get("branch", "default") == branch
                ]
                
                # Sort commits by date
                sorted_repo_commits = sorted(
                    repo_commits, 
                    key=lambda x: x["date_time"] if isinstance(x["date_time"], datetime) else datetime.now()
                )
                
                # Create a filename based on month, repository name, and branch
                repo_filename = repo_name.replace('/', '_')
                repo_csv_path = os.path.join(self.output_dir, f"{filename_base}_{repo_filename}_{branch}.csv")
                
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
                            commit.get("branch", "default")
                        ]
                        
                        writer.writerow(row_data)
                
                logger.info(f"Created repository CSV file for {repo_name} (branch: {branch}) with {len(sorted_repo_commits)} commits: {repo_csv_path}")
            
            # Return path to the main CSV file
            return main_csv_path
            
        except Exception as e:
            logger.error(f"Error creating CSV reports: {str(e)}")
            raise
