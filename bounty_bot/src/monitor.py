"""
Issue Monitor Module - Phase 2 Implementation
監控 Algora 和 GitHub 上的開源懸賞 Issue
"""

import os
import json
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import requests
from pydantic import BaseModel, Field
import yaml

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
    Supports Algora API and GitHub REST API as data sources
    """

    def __init__(self, config_path: str = "bounty_bot/config/settings.yaml"):
        """
        Initialize the monitor with configuration
        
        Args:
            config_path: Path to settings.yaml configuration file
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.cache_file = "/tmp/bounty_cache/issues.json"
        self.identified_issues: List[BountyIssue] = []
        self.previous_issues: List[BountyIssue] = self.load_cache()
        
        logger.info(f"Monitor initialized with config from {config_path}")
        logger.info(f"Filters: Languages={self.config['filters']['languages']}, "
                   f"Min Bounty=${self.config['filters']['min_bounty_amount']}")

    def _load_config(self) -> Dict:
        """Load and parse YAML configuration file"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Expand environment variables
            config = self._expand_env_vars(config)
            logger.info("Configuration loaded successfully")
            return config
        except FileNotFoundError:
            logger.error(f"Config file not found: {self.config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML config: {e}")
            raise

    def _expand_env_vars(self, config: Dict) -> Dict:
        """Recursively expand environment variables in config"""
        if isinstance(config, dict):
            return {k: self._expand_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._expand_env_vars(item) for item in config]
        elif isinstance(config, str):
            if config.startswith("${") and config.endswith("}"):
                env_var = config[2:-1]
                return os.getenv(env_var, config)
            return config
        return config

    def poll_algora_api(self) -> List[BountyIssue]:
        """
        Poll Algora API for bounty issues
        
        Endpoint: https://api.algora.io/v1/bounties
        
        Returns:
            List of BountyIssue objects matching filters
        """
        logger.info("Starting Algora API poll...")
        algora_issues = []
        
        try:
            endpoint = self.config['algora']['api_endpoint']
            headers = {
                'User-Agent': 'Autonomous-Code-Bounties-Bot/1.0',
                'Accept': 'application/json'
            }
            
            # Poll with pagination
            page = 1
            max_pages = 5
            
            while page <= max_pages:
                try:
                    params = {'page': page, 'per_page': 50}
                    response = requests.get(endpoint, headers=headers, params=params, timeout=10)
                    response.raise_for_status()
                    
                    data = response.json()
                    bounties = data.get('bounties', [])
                    
                    if not bounties:
                        logger.info(f"No more bounties on page {page}")
                        break
                    
                    for bounty in bounties:
                        # Apply filters
                        if self._matches_filters(bounty):
                            issue = self._parse_algora_bounty(bounty)
                            algora_issues.append(issue)
                            logger.debug(f"✓ Added: {issue.title} (${issue.bounty_amount})")
                        else:
                            logger.debug(f"✗ Filtered out: {bounty.get('title', 'Unknown')}")
                    
                    page += 1
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"API request failed on page {page}: {e}")
                    break
            
            logger.info(f"Algora API poll completed: {len(algora_issues)} issues found")
            
        except Exception as e:
            logger.error(f"Algora API poll failed: {e}")
        
        return algora_issues

    def _matches_filters(self, bounty: Dict) -> bool:
        """Check if bounty matches configured filters"""
        # Check bounty amount
        amount = bounty.get('amount', 0)
        min_bounty = self.config['filters']['min_bounty_amount']
        if amount < min_bounty:
            return False
        
        # Check language
        language = bounty.get('language', '')
        if language and language not in self.config['filters']['languages']:
            return False
        
        # Check excluded labels
        labels = bounty.get('labels', [])
        excluded = set(self.config['filters']['exclude_labels'])
        if any(label in excluded for label in labels):
            return False
        
        return True

    def _parse_algora_bounty(self, bounty: Dict) -> BountyIssue:
        """Convert Algora bounty response to BountyIssue object"""
        return BountyIssue(
            id=bounty.get('id', ''),
            title=bounty.get('title', 'Unknown'),
            description=bounty.get('description', ''),
            repository=bounty.get('repository', ''),
            repository_url=bounty.get('repo_url', ''),
            issue_url=bounty.get('url', ''),
            bounty_amount=float(bounty.get('amount', 0)),
            language=bounty.get('language', 'Unknown'),
            labels=bounty.get('labels', []),
            source='algora',
            created_at=datetime.fromisoformat(bounty.get('created_at', datetime.now().isoformat())),
            last_checked=datetime.now()
        )

    def poll_github_api(self) -> List[BountyIssue]:
        """
        Poll GitHub REST API for bounty issues
        
        API: https://api.github.com/search/issues
        Query: label:bounty OR label:bug-bounty state:open
        
        Returns:
            List of BountyIssue objects matching filters
        """
        logger.info("Starting GitHub API poll...")
        github_issues = []
        
        try:
            token = self.config['github'].get('token')
            if not token:
                logger.warning("GitHub token not configured, skipping GitHub API poll")
                return github_issues
            
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'Autonomous-Code-Bounties-Bot/1.0'
            }
            
            # Search for issues with bounty-related labels
            search_query = 'label:bounty OR label:bug-bounty OR label:"good first issue" state:open'
            params = {
                'q': search_query,
                'sort': 'updated',
                'order': 'desc',
                'per_page': 100
            }
            
            endpoint = 'https://api.github.com/search/issues'
            
            for page in range(1, 4):  # Limit to 3 pages (300 issues max)
                try:
                    params['page'] = page
                    response = requests.get(endpoint, headers=headers, params=params, timeout=10)
                    response.raise_for_status()
                    
                    data = response.json()
                    items = data.get('items', [])
                    
                    if not items:
                        logger.info(f"No more issues on page {page}")
                        break
                    
                    for item in items:
                        # Extract repository language
                        repo_name = item.get('repository_url', '').split('/')[-1]
                        repo_owner = item.get('repository_url', '').split('/')[-2]
                        language = self._get_github_repo_language(repo_owner, repo_name, headers)
                        
                        # Check if matches language filter
                        if language and language not in self.config['filters']['languages']:
                            logger.debug(f"✗ Skipped (language {language}): {item.get('title')}")
                            continue
                        
                        # Try to extract bounty amount from issue body/title
                        bounty_amount = self._extract_bounty_amount(item)
                        if bounty_amount < self.config['filters']['min_bounty_amount']:
                            logger.debug(f"✗ Skipped (bounty ${bounty_amount}): {item.get('title')}")
                            continue
                        
                        issue = self._parse_github_issue(item, language, bounty_amount)
                        github_issues.append(issue)
                        logger.debug(f"✓ Added: {issue.title} (${issue.bounty_amount})")
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"GitHub API request failed on page {page}: {e}")
                    break
            
            logger.info(f"GitHub API poll completed: {len(github_issues)} issues found")
            
        except Exception as e:
            logger.error(f"GitHub API poll failed: {e}")
        
        return github_issues

    def _get_github_repo_language(self, owner: str, repo: str, headers: Dict) -> Optional[str]:
        """Fetch primary programming language for a GitHub repository"""
        try:
            url = f'https://api.github.com/repos/{owner}/{repo}'
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get('language', 'Unknown')
        except Exception as e:
            logger.debug(f"Failed to fetch language for {owner}/{repo}: {e}")
        return None

    def _extract_bounty_amount(self, github_issue: Dict) -> float:
        """Extract bounty amount from GitHub issue title or body"""
        import re
        
        body = github_issue.get('body', '') + ' ' + github_issue.get('title', '')
        
        # Look for patterns like "$100", "$50 bounty", "bounty: $200"
        patterns = [
            r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $100, $1,000, $100.00
            r'bounty.*?\$?(\d+(?:,\d{3})*)',     # bounty $100 or bounty 100
            r'reward.*?\$?(\d+(?:,\d{3})*)',     # reward $100
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, body, re.IGNORECASE)
            if matches:
                try:
                    # Remove commas and convert to float
                    amount = float(matches[0].replace(',', ''))
                    if 50 <= amount <= 10000:  # Reasonable bounty range
                        return amount
                except ValueError:
                    pass
        
        return 0.0

    def _parse_github_issue(self, item: Dict, language: Optional[str], bounty_amount: float) -> BountyIssue:
        """Convert GitHub API response to BountyIssue object"""
        return BountyIssue(
            id=str(item.get('id', '')),
            title=item.get('title', 'Unknown'),
            description=item.get('body', '')[:500],  # Truncate description
            repository=item.get('repository_url', '').replace('https://api.github.com/repos/', ''),
            repository_url=item.get('repository_url', ''),
            issue_url=item.get('html_url', ''),
            bounty_amount=bounty_amount,
            language=language or 'Unknown',
            labels=[label.get('name', '') for label in item.get('labels', [])],
            source='github',
            created_at=datetime.fromisoformat(item.get('created_at', datetime.now().isoformat()).replace('Z', '+00:00')),
            last_checked=datetime.now()
        )

    def run_poll_cycle(self) -> List[BountyIssue]:
        """
        Execute one complete poll cycle
        
        Returns:
            List of new BountyIssue objects identified in this cycle
        """
        logger.info("=== Poll Cycle Started ===")
        start_time = datetime.now()
        
        # Poll both APIs
        algora_issues = self.poll_algora_api()
        github_issues = self.poll_github_api()
        
        # Merge and deduplicate
        self.identified_issues = self.deduplicate_issues(algora_issues, github_issues)
        
        # Get new issues
        new_issues = self.get_new_issues()
        
        # Save to cache
        self.save_cache(self.identified_issues)
        
        # Update previous issues
        self.previous_issues = self.identified_issues.copy()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"=== Poll Cycle Completed ===")
        logger.info(f"Total issues found: {len(self.identified_issues)}, "
                   f"New issues: {len(new_issues)}, "
                   f"Time: {elapsed:.2f}s")
        
        return new_issues

    def deduplicate_issues(self, 
                          algora_issues: List[BountyIssue],
                          github_issues: List[BountyIssue]) -> List[BountyIssue]:
        """
        Merge and deduplicate issues from both sources
        
        Returns:
            Combined list of issues without duplicates
        """
        issue_map = {}
        
        # Add all issues, keyed by (repository, issue_url)
        for issue in algora_issues + github_issues:
            key = (issue.repository, issue.issue_url)
            
            # Prioritize higher bounty amounts
            if key not in issue_map or issue.bounty_amount > issue_map[key].bounty_amount:
                issue_map[key] = issue
        
        merged_issues = list(issue_map.values())
        logger.info(f"Deduplicated {len(algora_issues) + len(github_issues)} issues → "
                   f"{len(merged_issues)} unique issues")
        
        return merged_issues

    def get_new_issues(self) -> List[BountyIssue]:
        """
        Get issues that were not in the previous poll cycle
        
        Returns:
            List of newly identified issues
        """
        previous_urls = {issue.issue_url for issue in self.previous_issues}
        new_issues = [issue for issue in self.identified_issues 
                     if issue.issue_url not in previous_urls]
        
        if new_issues:
            logger.info(f"Found {len(new_issues)} new issues:")
            for issue in new_issues:
                logger.info(f"  [{issue.source.upper()}] ${issue.bounty_amount} - {issue.title} "
                           f"({issue.repository})")
        
        return new_issues


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
            logger.debug(f"Saved {len(issues)} issues to cache")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")


# Example usage for testing
if __name__ == "__main__":
    monitor = IssueMonitor()
    
    # Run a single poll cycle
    new_issues = monitor.run_poll_cycle()
    
    if new_issues:
        print(f"\n✅ Found {len(new_issues)} new bounty issues!")
        for issue in new_issues:
            print(f"  - [{issue.source.upper()}] ${issue.bounty_amount:,.0f} | {issue.title}")
            print(f"    🔗 {issue.issue_url}\n")
    else:
        print("No new issues found in this poll cycle.")
    # for issue in new_issues:
    #     print(f"  - [{issue.bounty_amount}] {issue.title}")
