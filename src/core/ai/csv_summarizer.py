"""
AI-based CSV summarizer for generating work summaries from commit data.
"""
import os
import csv
import logging
from typing import List, Dict, Any
from datetime import datetime

from src.core.config import app_config
from src.core.llm_client import LLMClient

# Configure logger
logging.basicConfig(
    level=getattr(logging, app_config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=app_config.LOG_FILE,
    filemode="a"
)
logger = logging.getLogger(__name__)


class AICsvSummarizer:
    """AI-based summarizer for analyzing commit CSV files."""
    
    def __init__(self):
        """Initialize the AI CSV summarizer."""
        api_key = app_config.LLM_API_KEY or app_config.CLAUDE_API_KEY
        self.client = LLMClient(api_key=api_key)
        self.model = app_config.LLM_MODEL or app_config.CLAUDE_MODEL
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        logger.info("AI CSV summarizer initialized")
    
    def read_csv_data(self, csv_path: str) -> List[Dict[str, str]]:
        """Read commit data from a CSV file.
        
        Args:
            csv_path: Path to the CSV file
            
        Returns:
            List of commit data dictionaries
        """
        commits = []
        try:
            with open(csv_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    commits.append(row)
            logger.info(f"Read {len(commits)} commits from {csv_path}")
            return commits
        except Exception as e:
            logger.error(f"Error reading CSV file {csv_path}: {str(e)}")
            return []
    
    def generate_repository_summary(self, repo_name: str, commits: List[Dict[str, str]]) -> str:
        """Generate a point-wise summary for a repository's commits.
        
        Args:
            repo_name: Name of the repository
            commits: List of commit data dictionaries
            
        Returns:
            Point-wise summary of the work done
        """
        try:
            # Prepare commit data for analysis
            commit_messages = []
            for commit in commits:
                commit_msg = f"- {commit.get('Commit Message', '')} (by {commit.get('Username', 'unknown')})"
                commit_messages.append(commit_msg)
            
            commits_text = "\n".join(
                commit_messages[:app_config.BATCH_SIZE]
            )
            
            # Create prompt for AI
            prompt = f"""Analyze the following commits for repository '{repo_name}' and provide a concise point-wise summary of the work done.

Commits ({len(commits)} total):
{commits_text}

Please provide:
1. A brief overview (1-2 sentences)
2. Key features/changes implemented (bullet points)
3. Bug fixes or improvements (bullet points)
4. Any notable patterns or themes

Keep the summary concise and actionable."""
            
            # Call Claude API
            message = self.client.messages.create(
                model=self.model,
                max_tokens=min(1000, app_config.AI_MAX_TOKENS),
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Track token usage
            self.total_input_tokens += message.usage.input_tokens
            self.total_output_tokens += message.usage.output_tokens
            
            summary = message.content[0].text
            logger.info(f"Generated summary for {repo_name}")
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary for {repo_name}: {str(e)}")
            return f"Error generating summary: {str(e)}"
    
    def generate_overall_summary(self, all_commits: List[Dict[str, str]], repositories: List[str]) -> str:
        """Generate an overall summary of work across all repositories.
        
        Args:
            all_commits: List of all commit data dictionaries
            repositories: List of repository names
            
        Returns:
            Overall summary of work done
        """
        try:
            # Group commits by repository
            repo_commit_counts = {}
            repo_contributors = {}
            
            for commit in all_commits:
                repo = commit.get('Repository', 'unknown')
                username = commit.get('Username', 'unknown')
                
                repo_commit_counts[repo] = repo_commit_counts.get(repo, 0) + 1
                
                if repo not in repo_contributors:
                    repo_contributors[repo] = set()
                repo_contributors[repo].add(username)
            
            # Prepare statistics
            stats_text = f"""Total Commits: {len(all_commits)}
Repositories: {len(repositories)}

Commit Distribution:
"""
            for repo, count in sorted(repo_commit_counts.items(), key=lambda x: x[1], reverse=True):
                contributors = len(repo_contributors.get(repo, set()))
                stats_text += f"- {repo}: {count} commits ({contributors} contributors)\n"
            
            # Sample commit messages from each repository
            sample_commits = {}
            for commit in all_commits[:app_config.BATCH_SIZE]:
                repo = commit.get('Repository', 'unknown')
                if repo not in sample_commits:
                    sample_commits[repo] = []
                if len(sample_commits[repo]) < 5:  # Max 5 samples per repo
                    sample_commits[repo].append(commit.get('Commit Message', ''))
            
            samples_text = "\nSample Commits by Repository:\n"
            for repo, messages in sample_commits.items():
                samples_text += f"\n{repo}:\n"
                for msg in messages:
                    samples_text += f"  - {msg}\n"
            
            # Create prompt for AI
            prompt = f"""Analyze the following commit data across multiple repositories and provide a concise executive summary.

{stats_text}
{samples_text}

Please provide:
1. Overall project activity summary (2-3 sentences)
2. Key accomplishments across all repositories (bullet points)
3. Areas of focus or themes
4. Any recommendations or observations

Keep it concise and high-level."""
            
            # Call Claude API
            message = self.client.messages.create(
                model=self.model,
                max_tokens=min(1500, app_config.AI_MAX_TOKENS),
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Track token usage
            self.total_input_tokens += message.usage.input_tokens
            self.total_output_tokens += message.usage.output_tokens
            
            summary = message.content[0].text
            logger.info("Generated overall summary")
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating overall summary: {str(e)}")
            return f"Error generating overall summary: {str(e)}"
    
    def create_summary_report(self, base_path: str, repo_summaries: Dict[str, str], 
                             overall_summary: str, date_range: str) -> str:
        """Create a summary report file.
        
        Args:
            base_path: Base path for the CSV files
            repo_summaries: Dictionary mapping repository names to summaries
            overall_summary: Overall summary text
            date_range: Date range for the report
            
        Returns:
            Path to the summary report file
        """
        try:
            # Create summary CSV
            summary_path = base_path.replace('.csv', '_AI_SUMMARY.csv')
            
            with open(summary_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow(['Repository', 'Summary'])
                
                # Write overall summary first
                writer.writerow(['OVERALL SUMMARY', overall_summary])
                writer.writerow([])  # Empty row for separation
                
                # Write repository summaries
                for repo, summary in sorted(repo_summaries.items()):
                    writer.writerow([repo, summary])
            
            logger.info(f"Created summary report: {summary_path}")
            return summary_path
            
        except Exception as e:
            logger.error(f"Error creating summary report: {str(e)}")
            raise
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get token usage statistics.

        Returns:
            Dictionary with token usage and estimated cost
        """
        input_cost_per_million = getattr(
            app_config, "LLM_INPUT_COST_PER_MILLION",
            app_config.CLAUDE_INPUT_COST_PER_MILLION,
        )
        output_cost_per_million = getattr(
            app_config, "LLM_OUTPUT_COST_PER_MILLION",
            app_config.CLAUDE_OUTPUT_COST_PER_MILLION,
        )
        estimated_cost = (
            (self.total_input_tokens / 1_000_000)
            * input_cost_per_million
            + (self.total_output_tokens / 1_000_000)
            * output_cost_per_million
        )
        
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "estimated_cost": estimated_cost
        }
