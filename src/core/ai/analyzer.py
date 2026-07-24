"""
AI analyzer module for commit analysis using Claude API.
"""
import logging
import time
import re
from typing import Dict, List, Tuple, Any, Optional

import anthropic

from src.core.config import app_config

# Configure logger
logging.basicConfig(
    level=getattr(logging, app_config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=app_config.LOG_FILE,
    filemode="a"
)
logger = logging.getLogger(__name__)


class AiAnalyzer:
    """Commit analyzer using Claude API."""
    
    # Valid change types as defined in the requirements
    VALID_CHANGE_TYPES = [
        "Feature", "Bug Fix", "Refactor", "Performance", "Security",
        "Documentation", "Configuration", "Dependencies", "Database",
        "UI/UX", "Test", "Build/Deploy", "Other"
    ]
    
    def __init__(self, api_key: str = None):
        """Initialize the AI analyzer.
        
        Args:
            api_key: Claude API key. If None, uses the key from config.
        """
        self.api_key = api_key or app_config.CLAUDE_API_KEY
        if not self.api_key:
            raise ValueError("Claude API key is required")
        
        # Create the client based on the library version
        try:
            # Try the newer way first
            self.client = anthropic.Anthropic(api_key=self.api_key)
        except TypeError:
            # Fall back to older version if needed
            try:
                self.client = anthropic.Client(api_key=self.api_key)
            except Exception as e:
                raise ValueError(f"Failed to initialize Anthropic client: {str(e)}")
                
        self.model = app_config.CLAUDE_MODEL
        self.max_tokens = app_config.AI_MAX_TOKENS
        self.request_count = 0
        self.token_usage = {"input": 0, "output": 0}
        self.estimated_cost = 0.0
        self.rate_limit_window_start = time.time()
        self.requests_in_window = 0
        
        logger.info(f"AI analyzer initialized with model {self.model}")
    
    def _check_rate_limit(self):
        """Check and enforce rate limiting."""
        current_time = time.time()
        window_duration = 60  # 1 minute window
        
        # Reset counter if window has passed
        if current_time - self.rate_limit_window_start > window_duration:
            self.rate_limit_window_start = current_time
            self.requests_in_window = 0
        
        # If we've reached the limit, wait until the window resets
        if self.requests_in_window >= app_config.AI_RATE_LIMIT:
            sleep_time = window_duration - (current_time - self.rate_limit_window_start) + 1
            logger.warning(f"Rate limit reached. Waiting {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
            self.rate_limit_window_start = time.time()
            self.requests_in_window = 0
    
    def _track_token_usage(self, input_tokens: int, output_tokens: int):
        """Track token usage and estimate costs.
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            
        Returns:
            True if we're still under budget, False otherwise
        """
        try:
            # Ensure token_usage is properly initialized as a dict
            if not isinstance(self.token_usage, dict):
                logger.warning("token_usage was not a dict, resetting it")
                self.token_usage = {"input": 0, "output": 0}
                
            # Add the new tokens
            self.token_usage["input"] += input_tokens
            self.token_usage["output"] += output_tokens
            
            # Estimate costs (simplified, actual costs may vary)
            # Claude Sonnet pricing as of implementation: $3 per million input tokens, $15 per million output tokens
            input_cost = input_tokens * (3 / 1000000)
            output_cost = output_tokens * (15 / 1000000)
            
            # Initialize estimated_cost if needed
            if not hasattr(self, 'estimated_cost') or self.estimated_cost is None:
                self.estimated_cost = 0.0
                
            self.estimated_cost += input_cost + output_cost
            
            # Check if we're over budget
            if self.estimated_cost > app_config.AI_BUDGET_LIMIT:
                logger.warning(f"AI analysis budget limit reached: ${self.estimated_cost:.2f}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error tracking token usage: {str(e)}")
            return True  # Continue processing even if token tracking fails
    
    def _prepare_prompt(self, commit_message: str, repo_name: str, 
                        files_changed: List[str], diff_content: str) -> str:
        """Prepare the prompt for Claude API.
        
        Args:
            commit_message: The commit message
            repo_name: Repository name
            files_changed: List of changed files
            diff_content: The diff content
            
        Returns:
            Formatted prompt for Claude API
        """
        # Truncate diff content if it's too large
        max_diff_length = 50000  # This can be adjusted based on token limits
        if len(diff_content) > max_diff_length:
            diff_content = diff_content[:max_diff_length] + "\n[Diff truncated due to size...]"
        
        # Format the files changed list
        files_list = "\n".join(files_changed[:50])  # Limit to 50 files
        if len(files_changed) > 50:
            files_list += f"\n... and {len(files_changed) - 50} more files"
        
        return f"""Analyze this GitHub commit and provide:
1. A concise summary (50-150 words) of what was changed and why
2. Categorize the change type from: {', '.join(self.VALID_CHANGE_TYPES)}

Commit Message: {commit_message}
Repository: {repo_name}
Files Changed: {files_list}
Code Diff: {diff_content}

Focus on business impact and technical significance. Be specific about what functionality was added, modified, or removed.

Format your response as follows:
SUMMARY: [Your summary here]
CHANGE_TYPE: [Single category from the list]
"""
    
    def _parse_response(self, response: str) -> Tuple[str, str]:
        """Parse Claude's response to extract summary and change type.
        
        Args:
            response: The response from Claude API
            
        Returns:
            Tuple of (summary, change_type)
        """
        summary = ""
        change_type = "Other"  # Default
        
        # Extract summary using regex
        summary_match = re.search(r"SUMMARY:\s*(.*?)(?:\n\n|\nCHANGE_TYPE|\Z)", response, re.DOTALL)
        if summary_match:
            summary = summary_match.group(1).strip()
        
        # Extract change type using regex
        change_type_match = re.search(r"CHANGE_TYPE:\s*(.*?)(?:\n|\Z)", response)
        if change_type_match:
            change_type = change_type_match.group(1).strip()
            
            # Validate change type
            if change_type not in self.VALID_CHANGE_TYPES:
                # Find closest match
                for valid_type in self.VALID_CHANGE_TYPES:
                    if valid_type.lower() in change_type.lower():
                        change_type = valid_type
                        break
                else:
                    change_type = "Other"
        
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
            # Check rate limit and budget
            self._check_rate_limit()
            
            # Prepare prompt
            system_prompt = "You are an expert code reviewer analyzing GitHub commits. Provide clear, concise summaries and accurate categorization."
            prompt = self._prepare_prompt(
                commit_data["message"],
                commit_data["repo_name"],
                files_changed,
                diff_content
            )
            
            logger.debug(f"Processing commit {commit_data['sha'][:7]} with prompt length {len(prompt)}")
            response_text = ""
            
            # Try new API format first (v0.54.0+)
            try:
                logger.debug("Attempting to use new Anthropic API format (messages.create)")
                try:
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=min(1000, app_config.AI_MAX_TOKENS),
                        system=system_prompt,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    
                    # Extract response text based on response structure
                    if hasattr(response, 'content') and isinstance(response.content, list):
                        try:
                            response_text = response.content[0].text
                        except (AttributeError, IndexError, TypeError):
                            # Try different access patterns
                            try:
                                response_text = response.content[0]['text']
                            except (KeyError, IndexError, TypeError):
                                response_text = str(response.content)
                    else:
                        # Try direct access as string/dict
                        response_text = str(getattr(response, 'content', response))
                    
                    # Track token usage safely
                    try:
                        if hasattr(response, 'usage'):
                            input_tokens = getattr(response.usage, 'input_tokens', 0)
                            output_tokens = getattr(response.usage, 'output_tokens', 0)
                        else:
                            # Rough estimation
                            input_tokens = len(prompt) // 4
                            output_tokens = len(response_text) // 4
                        
                        budget_ok = self._track_token_usage(input_tokens, output_tokens)
                        if not budget_ok:
                            commit_data["ai_summary"] = "AI analysis budget limit reached"
                            commit_data["change_type"] = "Other"
                            return commit_data
                    except Exception as e:
                        logger.warning(f"Failed to track token usage: {str(e)}")
                except Exception as e:
                    logger.warning(f"Error with new API format: {str(e)}")
                    raise e
                
            # Fall back to old API format (pre-0.54.0)
            except Exception as e:
                logger.debug(f"New API failed: {str(e)}. Falling back to old API format")
                try:
                    response = self.client.completion(
                        prompt=f"\n\nHuman: {prompt}\n\nAssistant:",
                        model=self.model,
                        max_tokens_to_sample=min(
                            1000,
                            app_config.AI_MAX_TOKENS,
                        ),
                    )
                    
                    # Extract response text - old format is simpler
                    response_text = getattr(response, 'completion', str(response))
                    
                    # Track token usage
                    input_tokens = len(prompt) // 4  # Rough estimation
                    output_tokens = len(response_text) // 4  # Rough estimation
                    budget_ok = self._track_token_usage(input_tokens, output_tokens)
                    
                    if not budget_ok:
                        commit_data["ai_summary"] = "AI analysis budget limit reached"
                        commit_data["change_type"] = "Other"
                        return commit_data
                except Exception as nested_e:
                    logger.error(f"Both API formats failed. New API error: {str(e)}, Old API error: {str(nested_e)}")
                    raise nested_e
            
            # Ensure we have response text
            if not response_text:
                raise ValueError("Failed to extract response text from API response")
                
            logger.debug(f"Received response of length {len(response_text)}")
            
            # Parse response
            summary, change_type = self._parse_response(response_text)
            
            # Update rate limit stats
            self.request_count += 1
            self.requests_in_window += 1
            
            # Update commit data
            commit_data["ai_summary"] = summary
            commit_data["change_type"] = change_type
            
            logger.info(f"Successfully analyzed commit {commit_data['sha'][:7]}")
            
        except Exception as e:
            logger.error(f"Error analyzing commit {commit_data['sha'][:7]}: {str(e)}")
            commit_data["ai_summary"] = f"Analysis failed: {str(e)[:100]}"
            commit_data["change_type"] = "Other"
        
        return commit_data
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics.
        
        Returns:
            Dictionary with usage statistics
        """
        return {
            "request_count": self.request_count,
            "token_usage": self.token_usage,
            "estimated_cost": self.estimated_cost,
        }
