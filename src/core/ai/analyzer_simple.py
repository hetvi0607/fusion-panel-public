#!/usr/bin/env python
import os
import time
import logging
import anthropic
from typing import Dict, List, Any, Tuple

from src.core.config import app_config

logger = logging.getLogger(__name__)

class SimpleAiAnalyzer:
    """A simplified AI analyzer that uses Claude API for commit analysis."""
    
    # Add these class attributes for tracking token usage
    token_usage = {"input": 0, "output": 0}
    estimated_cost = 0.0
    request_count = 0
    
    def __init__(self, api_key: str = None, use_mock: bool = False):
        """Initialize the AI analyzer.
        
        Args:
            api_key: Claude API key. If None, uses the key from config.
            use_mock: If True, use mock responses instead of calling the API
        """
        self.use_mock = use_mock
        if use_mock:
            logger.info("Using MOCK mode for AI analysis - no API calls will be made")
            self.client = None
            self.use_new_api = False
        else:
            self.api_key = api_key or app_config.CLAUDE_API_KEY
            if not self.api_key:
                raise ValueError("Claude API key is required when not using mock mode")
            
            # Create the client based on the library version
            try:
                # Try the newer way first
                self.client = anthropic.Anthropic(api_key=self.api_key)
                self.use_new_api = True
                logger.info("Using newer Anthropic API (v0.54.0+)")
            except Exception as e:
                # Fall back to older version if needed
                try:
                    self.client = anthropic.Client(api_key=self.api_key)
                    self.use_new_api = False
                    logger.info("Using older Anthropic API")
                except Exception as e:
                    raise ValueError(f"Failed to initialize Anthropic client: {str(e)}")
                    
        self.model = app_config.CLAUDE_MODEL
        logger.info(f"AI analyzer initialized with model {self.model}")
        
    def _generate_mock_response(self, commit_data, diff_content):
        """Generate a mock AI response for testing purposes.
        
        Args:
            commit_data: The commit data
            diff_content: The diff content
            
        Returns:
            Tuple of (summary, change_type)
        """
        # Use some basic heuristics to determine a reasonable mock response
        commit_msg = commit_data.get("message", "").lower()
        
        # Determine change type based on keywords in commit message
        change_type = "Other"
        if any(word in commit_msg for word in ["fix", "bug", "issue", "error", "crash"]):
            change_type = "Bug Fix"
        elif any(word in commit_msg for word in ["feat", "feature", "add", "new", "implement"]):
            change_type = "Feature"
        elif any(word in commit_msg for word in ["refactor", "clean", "reorganize", "restructure", "improve"]):
            change_type = "Refactoring"
        elif any(word in commit_msg for word in ["doc", "comment", "readme"]):
            change_type = "Documentation"
        elif any(word in commit_msg for word in ["test", "spec", "assert"]):
            change_type = "Testing"
        
        # Generate a simple summary
        summary = f"This commit appears to {commit_data.get('message', '')[:50]}"
        
        return summary, change_type
    
    def _create_prompt(self, commit_message: str, repo_name: str, 
                      files_changed, diff_content: str) -> str:
        """Create a prompt for Claude to analyze a commit.
        
        Args:
            commit_message: The commit message
            repo_name: Name of the repository
            files_changed: Number of files changed or list of file paths
            diff_content: Git diff content
            
        Returns:
            Formatted prompt string
        """
        # Handle case where files_changed is an integer (count) rather than list of files
        if isinstance(files_changed, int):
            num_files = files_changed
            files_list = "No detailed file list available"
        else:
            # It's a list of files
            num_files = len(files_changed)
            try:
                if num_files > 0:
                    files_list = ', '.join(str(f) for f in files_changed[:10])
                    if num_files > 10:
                        files_list += "..."
                else:
                    files_list = "No files changed"
            except Exception as e:
                logger.warning(f"Error formatting file list: {str(e)}. Using fallback.")
                files_list = f"{num_files} files (details unavailable)"
        
        prompt = f"""
        Please analyze this GitHub commit and provide a clear, concise summary and categorize it.

        Repository: {repo_name}
        Commit Message: {commit_message}
        Files Changed: {num_files} files
        
        Changed Files:
        {files_list}
        
        Diff Content:
        ```
        {diff_content[:8000]}{"..." if len(diff_content) > 8000 else ""}
        ```
        
        Please provide:
        1. A concise (1-2 sentences) summary of what this commit does
        2. Categorize this change as one of: Feature, Bug Fix, Refactoring, Documentation, Testing, Infrastructure, Other

        Respond in this format:
        SUMMARY: [Your summary here]
        CHANGE_TYPE: [Category]
        """
        return prompt
    
    def _parse_response(self, response_text: str) -> Tuple[str, str]:
        """Parse Claude API response to extract summary and change type.
        
        Args:
            response_text: Text response from Claude API
            
        Returns:
            Tuple of (summary, change_type)
        """
        summary = "AI analysis completed"
        change_type = "Other"
        
        try:
            lines = response_text.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith("SUMMARY:"):
                    summary = line.replace("SUMMARY:", "").strip()
                elif line.startswith("CHANGE_TYPE:"):
                    change_type = line.replace("CHANGE_TYPE:", "").strip()
        except Exception as e:
            logger.warning(f"Error parsing Claude response: {str(e)}")
            
        return summary, change_type
    
    def analyze_commit(self, commit_data: Dict[str, Any], diff_content: str, files_changed: List[str]) -> Dict[str, Any]:
        """Analyze a commit using Claude API.
        
        Args:
            commit_data: The commit data
            diff_content: The diff content
            files_changed: List of changed files
            
        Returns:
            Updated commit data with AI analysis
        """
        if not app_config.AI_ENABLED:
            commit_data["ai_summary"] = "AI analysis disabled"
            commit_data["change_type"] = "Other"
            return commit_data
        
        try:
            # Get a simplified prompt
            prompt = self._create_prompt(
                commit_data["message"],
                commit_data["repo_name"],
                files_changed,
                diff_content
            )
            
            logger.debug(f"Processing commit {commit_data['sha'][:7]} with AI")
            
            # Use the appropriate API version
            if self.use_new_api:
                # New API (v0.54.0+)
                try:
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=1000,
                        system="You are an expert code reviewer analyzing GitHub commits.",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    
                    # Extract the response text safely
                    if hasattr(response, 'content') and isinstance(response.content, list) and len(response.content) > 0:
                        if hasattr(response.content[0], 'text'):
                            response_text = response.content[0].text
                        else:
                            response_text = str(response.content[0])
                    else:
                        response_text = str(response)
                        
                except Exception as e:
                    logger.error(f"Error with new API: {str(e)}")
                    raise e
            else:
                # Old API (pre-v0.54.0)
                try:
                    response = self.client.completion(
                        prompt=f"\n\nHuman: {prompt}\n\nAssistant:",
                        model=self.model,
                        max_tokens_to_sample=1000,
                    )
                    response_text = response.completion
                except Exception as e:
                    logger.error(f"Error with old API: {str(e)}")
                    raise e
                    
            # Parse the response
            summary, change_type = self._parse_response(response_text)
            
            # Add the analysis to the commit data
            commit_data["ai_summary"] = summary
            commit_data["change_type"] = change_type
            
            logger.info(f"Successfully analyzed commit {commit_data['sha'][:7]}")
            
        except Exception as e:
            logger.error(f"Error analyzing commit {commit_data['sha'][:7]}: {str(e)}")
            commit_data["ai_summary"] = f"Analysis failed: {str(e)[:100]}"
            commit_data["change_type"] = "Other"
        
        return commit_data

    def get_usage_stats(self):
        """Get token usage statistics.
        
        Returns:
            Dict with token usage stats
        """
        return {
            "request_count": self.request_count,
            "token_usage": self.token_usage,
            "estimated_cost": self.estimated_cost
        }
