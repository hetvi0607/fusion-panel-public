"""
GitHub Commit Tracking Automation main script.

This script orchestrates the entire process:
1. Fetches commits from GitHub repositories
2. Analyzes commits using Claude AI
3. Generates a CSV report
4. Sends an email with the report attached

Usage:
    python main.py [--month YYYY-MM] [--repos repo1,repo2]
"""
import os
import sys
import logging
import argparse
import time
from datetime import datetime, timedelta
import calendar
from typing import Dict, List, Tuple, Any, Optional
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from config import app_config
from github_client import GitHubClient
from ai_analyzer_simple import SimpleAiAnalyzer
from csv_reporter import CSVReporter

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
    
    # Optional repository list
    parser.add_argument('--repos', type=str, help='Comma-separated list of repositories (org/repo)')
    
    # Removed email recipient argument
    
    # Flag to disable AI analysis
    parser.add_argument('--no-ai', action='store_true', help='Disable AI analysis')
    
    # Flag to show verbose output
    parser.add_argument('--verbose', action='store_true', help='Show verbose output')
    
    return parser.parse_args()


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


def get_repositories(repo_arg: Optional[str] = None) -> List[str]:
    """Get the list of repositories to process.
    
    Args:
        repo_arg: Comma-separated list of repositories. If None, uses config.
        
    Returns:
        List of repository names in format org/repo
    """
    if repo_arg:
        # Use repositories from command line argument
        repos = [repo.strip() for repo in repo_arg.split(',')]
        logger.info(f"Using repositories from command line: {', '.join(repos)}")
        return repos
    elif app_config.REPOSITORIES:
        # Use repositories from config
        repos = list(app_config.REPOSITORIES.keys())
        logger.info(f"Using repositories from config: {', '.join(repos)}")
        return repos
    else:
        logger.error("No repositories specified in config or command line")
        sys.exit(1)


def process_commit(commit: Dict[str, Any], github_client: GitHubClient, ai_analyzer: SimpleAiAnalyzer) -> Dict[str, Any]:
    """Process a commit, including AI analysis if enabled.
    
    Args:
        commit: Commit data dictionary
        github_client: GitHub client for API access
        ai_analyzer: AI analyzer for commit analysis
        
    Returns:
        Processed commit data with additional fields
    """
    try:
        # If AI is enabled, analyze the commit
        if app_config.AI_ENABLED:
            # For our new implementation, we can pass the commit dictionary directly
            # The get_commit_diff method now handles different input types
            files_changed, diff_content = github_client.get_commit_diff(commit)
            commit = ai_analyzer.analyze_commit(commit, diff_content, files_changed)
        else:
            commit["ai_summary"] = "AI analysis not performed"
            commit["change_type"] = "Other"
        
        return commit
    
    except Exception as e:
        logger.error(f"Error processing commit {commit['sha'][:7]}: {str(e)}")
        commit["ai_summary"] = f"Processing error: {str(e)[:100]}"
        commit["change_type"] = "Other"
        return commit


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
        # Get date range for the month
        start_date, end_date = get_date_range_for_month(args.month)
        
        # Get the list of repositories
        repositories = get_repositories(args.repos)
        
        # Format month-year string for report title
        month_year = datetime.strptime(start_date, '%Y-%m-%d').strftime('%B %Y')
        
        # Initialize GitHub client
        github_client = GitHubClient()
        
        # Initialize AI analyzer if enabled
        ai_analyzer = None
        if app_config.AI_ENABLED:
            try:
                ai_analyzer = SimpleAiAnalyzer()
                logger.info("AI analyzer initialized")
            except Exception as e:
                logger.error(f"Error initializing AI analyzer: {str(e)}")
                logger.warning("Continuing without AI analysis")
                app_config.AI_ENABLED = False
        
        # Fetch commits from all repositories
        # Fetch commits for each repository
        logger.info(f"Fetching commits for {len(repositories)} repositories")
        all_commits = []
        for repo_name in repositories:
            try:
                # Get branch from config if specified
                branch = None
                if repo_name in app_config.REPOSITORIES:
                    branch = app_config.REPOSITORIES[repo_name].get('branch')
                
                branch_info = f" (branch: {branch})" if branch else ""
                logger.info(f"Fetching commits for {repo_name}{branch_info}")
                
                # Pass branch to fetch_commits
                repo_commits = github_client.fetch_commits(repo_name, start_date, end_date, branch=branch)
                logger.info(f"Fetched {len(repo_commits)} commits for {repo_name}{branch_info}")
                
                all_commits.extend(repo_commits)
            except Exception as e:
                logger.error(f"Error fetching commits for {repo_name}: {str(e)}")
        
        if not all_commits:
            logger.warning("No commits found in the specified date range")
            sys.exit(0)
        
        logger.info(f"Total commits fetched: {len(all_commits)}")
        
        # Process commits with AI analysis if enabled
        if app_config.AI_ENABLED and ai_analyzer:
            logger.info("Processing commits with AI analysis")
            
            processed_commits = []
            ai_success_count = 0
            ai_failure_count = 0
            
            # Use ThreadPoolExecutor for parallel processing if enabled
            if app_config.PARALLEL_PROCESSING:
                with ThreadPoolExecutor(max_workers=app_config.MAX_WORKERS) as executor:
                    # Submit all tasks
                    futures = {
                        executor.submit(
                            process_commit, commit, github_client, ai_analyzer
                        ): commit["sha"] 
                        for commit in all_commits
                    }
                    
                    # Process results as they complete
                    for future in tqdm(as_completed(futures), total=len(futures), desc="Processing commits"):
                        commit_sha = futures[future]
                        try:
                            result = future.result()
                            processed_commits.append(result)
                            
                            if result["ai_summary"] and "error" not in result["ai_summary"].lower():
                                ai_success_count += 1
                            else:
                                ai_failure_count += 1
                                
                        except Exception as e:
                            logger.error(f"Error processing commit {commit_sha[:7]}: {str(e)}")
                            ai_failure_count += 1
            else:
                # Sequential processing
                for commit in tqdm(all_commits, desc="Processing commits"):
                    try:
                        result = process_commit(commit, github_client, ai_analyzer)
                        processed_commits.append(result)
                        
                        if result["ai_summary"] and "error" not in result["ai_summary"].lower():
                            ai_success_count += 1
                        else:
                            ai_failure_count += 1
                            
                    except Exception as e:
                        logger.error(f"Error processing commit {commit['sha'][:7]}: {str(e)}")
                        ai_failure_count += 1
            
            # Replace all_commits with processed_commits
            all_commits = processed_commits
            
            logger.info(f"AI analysis complete. "
                       f"Success: {ai_success_count}, Failures: {ai_failure_count}")
        
        # Generate report in CSV format
        logger.info("Generating CSV report")
        csv_reporter = CSVReporter()
        report_path = csv_reporter.create_repository_reports(all_commits, month_year)
        logger.info(f"Report generated: {report_path}")
        
        # Prepare report statistics
        report_stats = {
            "total_commits": len(all_commits),
            "num_repositories": len(repositories),
            "date_range": f"{start_date} to {end_date}",
            "observations": []
        }
        
        # Add AI statistics if enabled
        if app_config.AI_ENABLED and ai_analyzer:
            report_stats["ai_processed"] = ai_success_count
            report_stats["ai_failed"] = ai_failure_count
            
            # Count change types
            change_types = [commit.get("change_type", "Other") for commit in all_commits]
            change_type_counts = dict(Counter(change_types))
            report_stats["change_type_counts"] = change_type_counts
            
            # Add AI usage stats
            usage_stats = ai_analyzer.get_usage_stats()
            report_stats["ai_token_usage"] = usage_stats["token_usage"]
            report_stats["ai_cost"] = usage_stats["estimated_cost"]
            
            # Add observations
            if ai_failure_count > 0:
                failure_percent = (ai_failure_count / len(all_commits)) * 100
                if failure_percent > 10:
                    report_stats["observations"].append(
                        f"High AI analysis failure rate: {failure_percent:.1f}%"
                    )
        
        # Log total execution time
        execution_time = time.time() - start_time
        logger.info(f"Total execution time: {execution_time:.2f} seconds")
        
        print(f"\nReport generated successfully: {report_path}")
        print(f"Total commits: {len(all_commits)}")
        print(f"Date range: {start_date} to {end_date}")
        
        if app_config.AI_ENABLED and ai_analyzer:
            print(f"AI analysis: {ai_success_count} successful, {ai_failure_count} failed")
            print(f"Estimated AI cost: ${usage_stats['estimated_cost']:.2f}")
        
        # Email notification functionality removed
        
        return 0
        
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
        print(f"Error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
