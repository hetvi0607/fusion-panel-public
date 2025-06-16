"""
GitHub API client for fetching repository and commit data.
"""
import logging
from datetime import datetime
import time
import re
from typing import Dict, List, Tuple, Optional, Any

import requests
from requests.exceptions import RequestException
from dateutil import parser

from config import app_config

# Configure logger
logging.basicConfig(
    level=getattr(logging, app_config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=app_config.LOG_FILE,
    filemode="a"
)
logger = logging.getLogger(__name__)


class GitHubClient:
    """Client for interacting with the GitHub API."""
    
    def __init__(self, token: str = None):
        """Initialize the GitHub client.
        
        Args:
            token: GitHub API token. If None, uses the token from config.
        """
        self.token = token or app_config.GITHUB_TOKEN
        if not self.token:
            raise ValueError("GitHub token is required")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json"
        }
        self.api_base_url = "https://api.github.com"
        
        # Test the connection
        try:
            response = requests.get(f"{self.api_base_url}/user", headers=self.headers)
            response.raise_for_status()
            self.authenticated_user = response.json().get("login")
            logger.info(f"GitHub client initialized as user: {self.authenticated_user}")
        except Exception as e:
            logger.error(f"Error initializing GitHub client: {str(e)}")
            raise
    
    def get_repo(self, repo_name: str) -> Dict:
        """Get a repository by name.
        
        Args:
            repo_name: Repository name in format "owner/repo"
            
        Returns:
            Repository data as dictionary
        """
        try:
            response = requests.get(f"{self.api_base_url}/repos/{repo_name}", headers=self.headers)
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            logger.error(f"Error accessing repository {repo_name}: {str(e)}")
            raise
    
    def _handle_rate_limit(self):
        """Handle GitHub API rate limiting."""
        rate_limit = requests.get(f"{self.api_base_url}/rate_limit", headers=self.headers)
        rate_limit.raise_for_status()
        rate_limit_data = rate_limit.json()
        reset_time = datetime.strptime(rate_limit_data['rate']['reset'], "%Y-%m-%dT%H:%M:%SZ")
        
        # Calculate seconds until reset
        now = datetime.utcnow()
        seconds_to_wait = int((reset_time - now).total_seconds()) + 5  # Add 5 seconds buffer
        
        if seconds_to_wait > 0:
            logger.warning(f"GitHub API rate limit reached. Waiting {seconds_to_wait} seconds")
            time.sleep(seconds_to_wait)
    
    def fetch_commits(self, repo_name: str, start_date: str, end_date: str, branch: str = None) -> List[Dict[str, Any]]:
        """Fetch commits from a repository within a date range.
        
        Args:
            repo_name: Repository name in format "owner/repo"
            start_date: Start date in format YYYY-MM-DD
            end_date: End date in format YYYY-MM-DD
            branch: Branch name (optional). If None, uses the default branch
            
        Returns:
            List of commit data dictionaries
        """
        try:
            # Convert dates to datetime objects for comparison
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
            
            # GitHub API pagination parameters
            page = 1
            per_page = 100
            all_commits = []
            
            while True:
                # Fetch commits page by page
                url = f"{self.api_base_url}/repos/{repo_name}/commits"
                params = {
                    "since": f"{start_date}T00:00:00Z",
                    "until": f"{end_date}T23:59:59Z",
                    "page": page,
                    "per_page": per_page
                }
                
                # Add branch filtering if specified
                if branch:
                    params["sha"] = branch
                    logger.info(f"Fetching commits from branch: {branch}")
                
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                commits_page = response.json()
                
                # If no more commits, break the loop
                if not commits_page:
                    break
                
                # Process commits on this page
                for commit in commits_page:
                    # Extract commit details
                    sha = commit["sha"]
                    html_url = commit["html_url"]
                    message = commit["commit"]["message"]
                    date_str = commit["commit"]["author"]["date"]
                    username = commit["commit"]["author"]["name"]
                    
                    # Parse date string to datetime
                    date_time = parser.parse(date_str)
                    
                    # Store commit info
                    commit_dict = {
                        "sha": sha,
                        "url": html_url,
                        "message": message,
                        "date_time": date_time,
                        "username": username,
                        "repo_name": repo_name,
                        "_commit_obj": sha  # Store just the SHA for further processing
                    }
                    
                    all_commits.append(commit_dict)
                
                # Move to next page
                page += 1
                
                # Add a small delay to avoid rate limiting
                time.sleep(0.1)
            
            logger.info(f"Fetched {len(all_commits)} commits from {repo_name} in date range {start_date} to {end_date}")
            return all_commits
            
        except RequestException as e:
            logger.error(f"Error fetching commits from {repo_name}: {str(e)}")
            return []
    
    def _extract_commit_data(self, commit: Dict[str, Any], repo_name: str) -> Dict[str, Any]:
        """Extract relevant data from a GitHub commit.
        
        Args:
            commit: GitHub Commit object
            repo_name: Repository name
            
        Returns:
            Dictionary with commit data
        """
        # Get commit details
        sha = commit["sha"]
        html_url = commit["html_url"]
        message = commit["commit"]["message"]
        date_str = commit["commit"]["author"]["date"]
        username = commit["commit"]["author"]["name"]
        
        # Parse date string to datetime
        date_time = parser.parse(date_str)
        
        return {
            "sha": sha,
            "url": html_url,
            "message": message,
            "date_time": date_time,
            "username": username,
            "repo_name": repo_name,
            # These will be filled in later by the AI analysis
            "ai_summary": None,
            "change_type": None,
            # Store the commit object for later use (e.g., to fetch the diff)
            "_commit_obj": commit
        }
    
    def get_commit_diff(self, commit_obj) -> Tuple[int, str]:
        """Get the diff for a commit.
        
        Args:
            commit_obj: Commit object or SHA string
            
        Returns:
            Tuple of (number of files changed, diff content)
        """
        try:
            # Handle different input types (SHA string or dict with repo info)
            if isinstance(commit_obj, dict) and 'repo_name' in commit_obj:
                repo_name = commit_obj['repo_name']
                commit_sha = commit_obj['sha']
            elif isinstance(commit_obj, str) and '/' in commit_obj:
                # If commit_obj is a full repository URL
                parts = commit_obj.split('/')
                if len(parts) >= 5:  # https://api.github.com/repos/owner/repo/commits/sha
                    repo_name = f"{parts[-4]}/{parts[-3]}"
                    commit_sha = parts[-1]
                else:
                    repo_name = "example-org/sample-api"  # Default to current repo
                    commit_sha = commit_obj
            else:
                # If it's just a SHA string
                repo_name = "example-org/sample-api"  # Default to current repo
                commit_sha = commit_obj
            
            # Get commit details with files information
            url = f"{self.api_base_url}/repos/{repo_name}/commits/{commit_sha}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            commit_data = response.json()
            
            files = commit_data.get('files', [])
            files_changed = len(files)
            
            # Collect all file diffs
            diff_content = ""
            for file in files:
                filename = file.get('filename', 'unknown')
                status = file.get('status', 'unknown')
                additions = file.get('additions', 0)
                deletions = file.get('deletions', 0)
                patch = file.get('patch', '')
                
                diff_content += f"File: {filename} (status: {status})\n"
                diff_content += f"Changes: +{additions} -{deletions}\n"
                if patch:
                    diff_content += f"{patch}\n\n"
                
            return files_changed, diff_content
            
        except Exception as e:
            logger.error(f"Error getting diff for commit {commit_sha}: {str(e)}")
            return 0, "Error retrieving diff content."
    
    def close(self):
        """Close the GitHub client connection."""
        logger.info("GitHub client connection closed")
