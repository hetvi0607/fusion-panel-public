"""
Configuration module for the GitHub Commit Tracking Automation.
Contains configuration classes and parameters for the application.
"""
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration class with common settings."""
    
    # GitHub API credentials
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    
    # Claude API credentials (hardcoded)
    CLAUDE_API_KEY = "REDACTED_REMOVED_CREDENTIAL"
    CLAUDE_MODEL = "claude-3-5-sonnet-20241022"  # Default to Sonnet
    
    # Google Sheets API credentials
    GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    
    # Email settings
    EMAIL_SENDER = os.getenv("EMAIL_SENDER")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "recipient@example.com")
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    
    # Repository configuration
    # Parse repository configuration including branch specifications
    # Format in .env: GITHUB_REPOS=org/repo1,org/repo2
    # Format in .env for branches: GITHUB_REPOS_BRANCHES=org/repo1:branch1,org/repo2:branch2
    REPOSITORIES = {}
    
    # Parse standard repository list
    for repo in os.getenv("GITHUB_REPOS", "").split(","):
        if repo.strip():
            REPOSITORIES[repo.strip()] = {"enabled": True, "ai_enabled": True, "branch": None}
    
    # Parse repository-branch mappings
    for repo_branch in os.getenv("GITHUB_REPOS_BRANCHES", "").split(","):
        if ":" in repo_branch:
            repo, branch = repo_branch.split(":", 1)
            repo = repo.strip()
            branch = branch.strip()
            if repo:
                # Update existing entry or create new one
                if repo in REPOSITORIES:
                    REPOSITORIES[repo]["branch"] = branch
                else:
                    REPOSITORIES[repo] = {"enabled": True, "ai_enabled": True, "branch": branch}
    
    # Default to current month if not specified
    @staticmethod
    def get_default_date_range():
        """Get the default date range (current month)."""
        now = datetime.now()
        start_date = datetime(now.year, now.month, 1).strftime("%Y-%m-%d")
        # Use current date as end date
        end_date = now.strftime("%Y-%m-%d")
        return start_date, end_date
    
    # AI analysis settings
    # Hardcoded to always be True
    AI_ENABLED = True
    AI_SUMMARY_MIN_WORDS = int(os.getenv("AI_SUMMARY_MIN_WORDS", 50))
    AI_SUMMARY_MAX_WORDS = int(os.getenv("AI_SUMMARY_MAX_WORDS", 150))
    AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", 100000))  # Maximum tokens per request
    AI_RATE_LIMIT = int(os.getenv("AI_RATE_LIMIT", 50))  # Maximum requests per minute
    AI_BUDGET_LIMIT = float(os.getenv("AI_BUDGET_LIMIT", 50.0))  # Maximum monthly budget ($)
    
    # Performance settings
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", 100))  # Number of commits to process in batch
    PARALLEL_PROCESSING = os.getenv("PARALLEL_PROCESSING", "False").lower() in ("true", "1", "yes")
    MAX_WORKERS = int(os.getenv("MAX_WORKERS", 5))  # Number of worker threads/processes
    
    # Retry settings
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
    RETRY_DELAY = int(os.getenv("RETRY_DELAY", 5))  # In seconds
    
    # Logging settings
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "commit_tracker.log")


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    LOG_LEVEL = "DEBUG"


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    LOG_LEVEL = "INFO"


# Select configuration based on environment
ENV = os.getenv("ENVIRONMENT", "development")
if ENV.lower() == "production":
    app_config = ProductionConfig()
else:
    app_config = DevelopmentConfig()
