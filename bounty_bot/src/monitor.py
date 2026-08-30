"""
Issue Monitor Module - Phase 2 Implementation
監控 Algora 和 GitHub 上的開源懸賞 Issue
"""

import os
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import requests
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


class BountyIssue(BaseModel):
    """Data model for identified bounty issues"""
    id: str
    title: str
    description: str
    repository: str
    repository_url: str
    issue_url: str
    bounty_amount: float
    language: str
    labels: List[str] = Field(default_factory=list)
    source: str  # "algora" or "github"
    created_at: datetime
    last_checked: Optional[datetime] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class IssueMonitor:
    """
    Main monitor class for polling bounty issues
    
    TODO: Implement the following methods
    """

    def __init__(self, config_path: str = "bounty_bot/config/settings.yaml"):
        """
        Initialize the monitor with configuration
        
        Args:
            config_path: Path to settings.yaml configuration file
            
        TODO:
            - [ ] Load YAML configuration
            - [ ] Validate required fields (LLM provider, GitHub token, Algora endpoint)
            - [ ] Initialize cache directory (/tmp/bounty_cache)
            - [ ] Setup logging with config.log_level
        """
        self.config_path = config_path
        self.config = None
        self.cache_file = "/tmp/bounty_cache/issues.json"
        self.identified_issues: List[BountyIssue] = []
        
        # TODO: Implement initialization logic

    def poll_algora_api(self) -> List[BountyIssue]:
        """
        Poll Algora API for bounty issues
        
        Endpoint: https://api.algora.io/v1/bounties
        
        TODO:
            - [ ] Call Algora API with proper headers
            - [ ] Parse response JSON
            - [ ] Filter by language (config.filters.languages)
            - [ ] Filter by minimum bounty amount (config.filters.min_bounty_amount)
            - [ ] Exclude issues with excluded labels (config.filters.exclude_labels)
            - [ ] Create BountyIssue objects for each qualifying issue
            - [ ] Log number of issues found and filtered
            
        Returns:
            List of BountyIssue objects
            
        Example Response Structure (from Algora):
            {
                "bounties": [
                    {
                        "id": "12345",
                        "title": "Fix memory leak",
                        "description": "...",
                        "repository": "org/repo",
                        "amount": 100.0,
                        "language": "Python",
                        "url": "https://algora.io/bounties/12345"
                    }
                ]
            }
        """
        logger.info("Starting Algora API poll...")
        # TODO: Implement Algora polling
        pass

    def poll_github_api(self) -> List[BountyIssue]:
        """
        Poll GitHub REST API for bounty issues
        
        API: https://api.github.com/search/issues
        Query: label:bounty OR label:bug-bounty
        
        TODO:
            - [ ] Use GitHub REST API with Authentication (GITHUB_TOKEN)
            - [ ] Search query: 'label:bounty OR label:bug-bounty state:open'
            - [ ] Paginate through results (per_page=100, max 3 pages)
            - [ ] Extract repo language using repo details endpoint
            - [ ] Filter by language and min bounty amount (parse from issue body/title)
            - [ ] Create BountyIssue objects for each qualifying issue
            - [ ] Handle rate limiting (GitHub limit: 30 requests/min)
            
        Returns:
            List of BountyIssue objects
            
        Reference: https://docs.github.com/en/rest/search/search?apiVersion=2022-11-28
        """
        logger.info("Starting GitHub API poll...")
        # TODO: Implement GitHub polling
        pass

    def run_poll_cycle(self) -> List[BountyIssue]:
        """
        Execute one complete poll cycle
        
        TODO:
            - [ ] Call poll_algora_api()
            - [ ] Call poll_github_api()
            - [ ] Merge and deduplicate results
            - [ ] Save results to cache (self.cache_file)
            - [ ] Update last_checked timestamp
            - [ ] Log summary (total issues found, filtered count)
            - [ ] Return list of new qualifying issues
            
        Returns:
            List of new BountyIssue objects identified in this cycle
        """
        logger.info("=== Poll Cycle Started ===")
        # TODO: Implement poll cycle
        pass

    def deduplicate_issues(self, 
                          algora_issues: List[BountyIssue],
                          github_issues: List[BountyIssue]) -> List[BountyIssue]:
        """
        Merge and deduplicate issues from both sources
        
        TODO:
            - [ ] Compare issues by repository + issue_url
            - [ ] Prioritize by bounty amount (higher is better)
            - [ ] Return combined list without duplicates
        """
        # TODO: Implement deduplication
        pass

    def load_cache(self) -> List[BountyIssue]:
        """Load previously identified issues from cache"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    return [BountyIssue(**issue) for issue in data]
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        return []

    def save_cache(self, issues: List[BountyIssue]):
        """Save identified issues to cache"""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        try:
            with open(self.cache_file, 'w') as f:
                json.dump([issue.dict() for issue in issues], f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def get_new_issues(self) -> List[BountyIssue]:
        """
        Get issues that were not in the previous poll cycle
        
        TODO:
            - [ ] Compare current issues with cached issues
            - [ ] Return only newly identified issues
            - [ ] Log newly found issues
        """
        # TODO: Implement new issue detection
        pass


# Example usage for testing
if __name__ == "__main__":
    monitor = IssueMonitor()
    
    # TODO: Uncomment after implementation
    # new_issues = monitor.run_poll_cycle()
    # print(f"Found {len(new_issues)} new bounty issues!")
    # for issue in new_issues:
    #     print(f"  - [{issue.bounty_amount}] {issue.title}")
