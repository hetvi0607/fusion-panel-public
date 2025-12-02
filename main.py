"""
GitHub Commit Tracking Automation main script.

This script orchestrates the entire process:
1. Fetches commits from GitHub repositories
2. Generates CSV reports (one per repository + combined)
3. Uses Claude AI to generate point-wise summaries (if AI_ENABLED)
4. Creates an overall summary CSV

Usage:
    python main.py [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
    python main.py [--month YYYY-MM] [--repos repo1,repo2]
    python main.py  # Interactive mode - prompts for date range
"""
import os
import sys
import logging
import argparse
import time
from datetime import datetime
import calendar
from typing import Dict, List, Tuple, Any, Optional

from src.core.config import app_config
from src.core.github_client import GitHubClient
from src.core.csv_reporter import CSVReporter
from src.core.ai.csv_summarizer import AICsvSummarizer
from src.integrations.whatsapp_sender import send_whatsapp_report

# Configure logger
logging.basicConfig(
    level=getattr(logging, app_config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=app_config.LOG_FILE,
    filemode="a"
)
logger = logging.getLogger(__name__)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='GitHub Commit Tracking Automation')
    
    # Optional month specification
    parser.add_argument('--month', type=str, help='Month to process in YYYY-MM format')
    
    # Optional date range specification
    parser.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format')
    parser.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format')
    
    # Optional repository list
    parser.add_argument('--repos', type=str, help='Comma-separated list of repositories (org/repo)')
    
    # Removed email recipient argument
    
    # Flag to disable AI analysis
    parser.add_argument('--no-ai', action='store_true', help='Disable AI analysis')
    
    # Flag to show verbose output
    parser.add_argument('--verbose', action='store_true', help='Show verbose output')
    
    return parser.parse_args()


def prompt_for_date_range() -> Tuple[str, str]:
    """Prompt user for date range interactively.
    
    Returns:
        Tuple of (start_date, end_date) in YYYY-MM-DD format
    """
    print("\nEnter date range for commit tracking:")
    
    while True:
        start_date_str = input("Start date (YYYY-MM-DD): ").strip()
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            break
        except ValueError:
            print("Invalid date format. Please use YYYY-MM-DD (e.g., 2024-01-01)")
    
    while True:
        end_date_str = input("End date (YYYY-MM-DD): ").strip()
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            if end_date < start_date:
                print("End date cannot be before start date. Please try again.")
                continue
            break
        except ValueError:
            print("Invalid date format. Please use YYYY-MM-DD (e.g., 2024-01-31)")
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')


def get_date_range_for_month(month_str: Optional[str] = None) -> Tuple[str, str]:
    """Get start and end dates for the specified month.
    
    Args:
        month_str: Month in YYYY-MM format. If None, uses current month.
        
    Returns:
        Tuple of (start_date, end_date) in YYYY-MM-DD format
    """
    if month_str:
        try:
            # Parse YYYY-MM format
            year, month = map(int, month_str.split('-'))
            start_date = datetime(year, month, 1)
            
            # Get last day of month
            _, last_day = calendar.monthrange(year, month)
            end_date = datetime(year, month, last_day)
            
        except ValueError as e:
            logger.error(f"Invalid month format: {month_str}. Error: {str(e)}")
            sys.exit(1)
    else:
        # Use current month
        now = datetime.now()
        start_date = datetime(now.year, now.month, 1)
        end_date = now
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')


def get_date_range(start_date_arg: Optional[str] = None, 
                   end_date_arg: Optional[str] = None,
                   month_arg: Optional[str] = None) -> Tuple[str, str]:
    """Get date range from arguments or prompt user.
    
    Args:
        start_date_arg: Start date in YYYY-MM-DD format
        end_date_arg: End date in YYYY-MM-DD format
        month_arg: Month in YYYY-MM format
        
    Returns:
        Tuple of (start_date, end_date) in YYYY-MM-DD format
    """
    # Priority 1: Explicit date range
    if start_date_arg and end_date_arg:
        try:
            start_date = datetime.strptime(start_date_arg, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_arg, '%Y-%m-%d')
            
            if end_date < start_date:
                logger.error("End date cannot be before start date")
                sys.exit(1)
            
            return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')
        except ValueError as e:
            logger.error(f"Invalid date format: {str(e)}")
            sys.exit(1)
    
    # Priority 2: Month specification
    elif month_arg:
        return get_date_range_for_month(month_arg)
    
    # Priority 3: Prompt user for date range
    else:
        return prompt_for_date_range()


def get_repositories(repo_arg: Optional[str] = None) -> List[Dict[str, str]]:
    """Get the list of repositories to process.
    
    Args:
        repo_arg: Comma-separated list of repositories. If None, uses config.
        
    Returns:
        List of repository dictionaries with 'repo' and 'branch' keys
    """
    if repo_arg:
        # Use repositories from command line argument
        repo_list = []
        for repo in repo_arg.split(','):
            repo = repo.strip()
            if repo:
                repo_list.append({'repo': repo, 'branch': None})
        logger.info(f"Using repositories from command line: {', '.join([r['repo'] for r in repo_list])}")
        return repo_list
    elif app_config.REPOSITORIES:
        # Use repositories from config (already in the right format)
        logger.info(f"Using {len(app_config.REPOSITORIES)} repository configurations from config")
        return app_config.REPOSITORIES
    else:
        logger.error("No repositories specified in config or command line")
        sys.exit(1)




def main():
    """Main entry point."""
    start_time = time.time()
    
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Configure logging for verbose output
    if args.verbose:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logging.getLogger().addHandler(console_handler)
    
    # Override AI setting if specified
    if args.no_ai:
        app_config.AI_ENABLED = False
        logger.info("AI analysis disabled via command line argument")
    
    logger.info("Starting GitHub Commit Tracking Automation")
    
    try:
        # Get date range
        start_date, end_date = get_date_range(args.start_date, args.end_date, args.month)
        
        # Get the list of repositories
        repositories = get_repositories(args.repos)
        
        # Format month-year string for report title
        month_year = datetime.strptime(start_date, '%Y-%m-%d').strftime('%B %Y')
        
        # Initialize GitHub client
        github_client = GitHubClient()
        
        # Initialize AI summarizer if enabled
        ai_summarizer = None
        if app_config.AI_ENABLED:
            try:
                ai_summarizer = AICsvSummarizer()
                logger.info("AI summarizer initialized")
            except Exception as e:
                logger.error(f"Error initializing AI summarizer: {str(e)}")
                logger.warning("Continuing without AI summaries")
                app_config.AI_ENABLED = False
        
        # Fetch commits from all repositories
        logger.info(f"Fetching commits for {len(repositories)} repository configurations")
        all_commits = []
        for repo_config in repositories:
            try:
                repo_name = repo_config['repo']
                branch = repo_config.get('branch')
                
                branch_info = f" (branch: {branch})" if branch else ""
                logger.info(f"Fetching commits for {repo_name}{branch_info}")
                
                # Pass branch to fetch_commits
                repo_commits = github_client.fetch_commits(repo_name, start_date, end_date, branch=branch)
                logger.info(f"Fetched {len(repo_commits)} commits for {repo_name}{branch_info}")
                
                all_commits.extend(repo_commits)
            except Exception as e:
                logger.error(f"Error fetching commits for {repo_config.get('repo', 'unknown')}: {str(e)}")
        
        if not all_commits:
            logger.warning("No commits found in the specified date range")
            sys.exit(0)
        
        logger.info(f"Total commits fetched: {len(all_commits)}")
        
        # Generate report in CSV format
        logger.info("Generating CSV report")
        csv_reporter = CSVReporter()
        report_path = csv_reporter.create_repository_reports(all_commits, month_year)
        logger.info(f"Report generated: {report_path}")
        
        # Generate AI summaries if enabled
        summary_path = None
        if app_config.AI_ENABLED and ai_summarizer:
            logger.info("Generating AI summaries from CSV data")
            
            try:
                # Generate summaries for each repository + branch combination
                repo_summaries = {}
                month_dir = os.path.dirname(report_path)
                
                # Get unique repo + branch combinations from the commits
                repo_branch_combos = set((commit["repo_name"], commit.get("branch", "default")) for commit in all_commits)
                
                for repo_name, branch in repo_branch_combos:
                    # Sanitize repo and branch names to match the new directory structure
                    repo_sanitized = repo_name.replace('/', '-')
                    branch_sanitized = branch.replace('/', '-')
                    
                    # Build path to repository-specific CSV using new hierarchical structure
                    repo_csv_path = os.path.join(month_dir, repo_sanitized, branch_sanitized, "commits.csv")
                    
                    if os.path.exists(repo_csv_path):
                        commits = ai_summarizer.read_csv_data(repo_csv_path)
                        if commits:
                            summary_key = f"{repo_name} ({branch})"
                            summary = ai_summarizer.generate_repository_summary(summary_key, commits)
                            repo_summaries[summary_key] = summary
                            logger.info(f"Generated summary for {repo_name} (branch: {branch})")
                    else:
                        logger.warning(f"CSV file not found for {repo_name} ({branch}): {repo_csv_path}")
                
                # Read all commits from main CSV for overall summary
                all_csv_commits = ai_summarizer.read_csv_data(report_path)
                repo_names = [r['repo'] for r in repositories]
                overall_summary = ai_summarizer.generate_overall_summary(all_csv_commits, repo_names)
                
                # Create summary report
                summary_path = ai_summarizer.create_summary_report(
                    report_path, repo_summaries, overall_summary, f"{start_date} to {end_date}"
                )
                
                # Get usage stats
                usage_stats = ai_summarizer.get_usage_stats()
                logger.info(f"AI summary generation complete. Cost: ${usage_stats['estimated_cost']:.4f}")
                
                print(f"\nAI Summary report generated: {summary_path}")
                print(f"Estimated AI cost: ${usage_stats['estimated_cost']:.4f}")
                print(f"Tokens used: {usage_stats['total_tokens']} (input: {usage_stats['input_tokens']}, output: {usage_stats['output_tokens']})")
                
            except Exception as e:
                logger.error(f"Error generating AI summaries: {str(e)}")
                print(f"\nWarning: Failed to generate AI summaries: {str(e)}")
        
        # Log total execution time
        execution_time = time.time() - start_time
        logger.info(f"Total execution time: {execution_time:.2f} seconds")
        
        print(f"\n{'='*60}")
        print(f"Report generated successfully!")
        print(f"{'='*60}")
        print(f"CSV Report: {report_path}")
        print(f"Total commits: {len(all_commits)}")
        print(f"Date range: {start_date} to {end_date}")
        print(f"Repositories: {len(repositories)}")
        if summary_path:
            print(f"AI Summary: {summary_path}")
        print(f"{'='*60}")
        
        # Email notification functionality removed
        
        # Send WhatsApp notification if enabled
        if app_config.WHATSAPP_ENABLED:
            try:
                logger.info("Sending WhatsApp notifications")
                whatsapp_sent = send_whatsapp_report(
                    csv_path=report_path,
                    summary_path=summary_path,
                    date_range=f"{start_date} to {end_date}"
                )
                if whatsapp_sent:
                    logger.info("WhatsApp notifications sent successfully")
                else:
                    logger.warning("WhatsApp notifications were not sent")
            except Exception as e:
                logger.error(f"Error sending WhatsApp notifications: {str(e)}")
                print(f"\n⚠️  Warning: Failed to send WhatsApp notifications: {str(e)}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
        print(f"Error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
