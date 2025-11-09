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
    
    # Claude API credentials
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
    
    # Google Sheets API credentials (optional)
    GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    
    # Spreadsheet ID for Google Sheets integration
    SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
    
    # Email settings
    EMAIL_SENDER = os.getenv("EMAIL_SENDER")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "recipient@example.com")
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    
    # WhatsApp Business API settings
    WHATSAPP_ENABLED = os.getenv("WHATSAPP_ENABLED", "False").lower() in ("true", "1", "yes")
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    # Parse WhatsApp group IDs (comma-separated list)
    WHATSAPP_GROUP_IDS = [
        group_id.strip() 
        for group_id in os.getenv("WHATSAPP_GROUP_IDS", "").split(",") 
        if group_id.strip()
    ]
    
    # Repository configuration
    # Repositories are now stored in SQLite database (repositories.db)
    # Use migrate_to_db.py to migrate from .env to database
    # Use manage_repos.py to manage repository configurations
    REPOSITORIES = []  # Will be loaded from database
    
    @staticmethod
    def load_repositories():
        """Load repository configurations from database."""
        try:
            from src.core.repository_db import RepositoryDB
            db = RepositoryDB()
            repositories = db.get_repositories(enabled_only=True)
            
            if not repositories:
                # Fallback to environment variables if database is empty
                import logging
                logger = logging.getLogger(__name__)
                logger.warning("No repositories found in database. Falling back to environment variables.")
                
                # Parse repository-branch mappings (prioritize this)
                if os.getenv("GITHUB_REPOS_BRANCHES", ""):
                    for repo_branch in os.getenv("GITHUB_REPOS_BRANCHES", "").split(","):
                        if ":" in repo_branch:
                            repo, branch = repo_branch.split(":", 1)
                            repo = repo.strip()
                            branch = branch.strip()
                            if repo:
                                repositories.append({
                                    "repo": repo,
                                    "branch": branch,
                                    "enabled": True,
                                    "ai_enabled": True
                                })
                else:
                    # Fallback to standard repository list without branches
                    for repo in os.getenv("GITHUB_REPOS", "").split(","):
                        if repo.strip():
                            repositories.append({
                                "repo": repo.strip(),
                                "branch": None,
                                "enabled": True,
                                "ai_enabled": True
                            })
            
            return repositories
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error loading repositories from database: {str(e)}")
            return []
    
    # Load repositories from database on initialization
    REPOSITORIES = load_repositories.__func__()
    
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
    AI_ENABLED = os.getenv("AI_ENABLED", "True").lower() in ("true", "1", "yes")
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
    # Default log file path - relative to project root
    _current_file = os.path.abspath(__file__)
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_file)))
    LOG_FILE = os.getenv("LOG_FILE", os.path.join(_project_root, "logs", "commit_tracker.log"))


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
