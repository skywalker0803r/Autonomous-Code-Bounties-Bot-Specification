"""
Phase 6: Auto Submitter Module
Automatically creates and submits pull requests for validated patches

Workflow:
1. Clone user's fork or target repository
2. Create feature branch
3. Apply patch to repository
4. Commit changes
5. Push to remote
6. Create PR via GitHub API

Author: Autonomous Code Bounties Bot
Created: 2026-09-02
"""

import os
import json
import logging
import re
import stat
import subprocess
import time
import shutil
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from git import Repo, GitCommandError
import requests


def _rmtree_clearing_readonly(func, path, exc_info) -> None:
    """shutil.rmtree onerror hook: git leaves pack/idx files read-only, which
    makes plain rmtree() raise PermissionError ([WinError 5] Access is
    denied) on Windows - clear the flag and retry once."""
    os.chmod(path, stat.S_IWRITE)
    func(path)

# Configure logging
logger = logging.getLogger(__name__)


class SubmissionResult(BaseModel):
    """Result of pull request submission"""
    issue_id: str
    submitter_id: str
    repository: str
    fork_url: str
    branch_name: str
    pr_url: Optional[str] = None
    pr_number: Optional[int] = None
    status: str  # "PR_CREATED", "SUBMISSION_FAILED", "GIT_FAILED"
    commit_sha: Optional[str] = None
    error_message: Optional[str] = None
    submitted_at: datetime = Field(default_factory=datetime.now)
    commit_message: str = ""


class SubmitterConfig(BaseModel):
    """Configuration for Auto Submitter"""
    github_token: str = Field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    github_username: str = Field(default_factory=lambda: os.getenv("GITHUB_USERNAME", ""))
    github_api_url: str = "https://api.github.com"
    git_user_name: str = "Autonomous Bounty Bot"
    git_user_email: str = Field(default_factory=lambda: os.getenv("GIT_USER_EMAIL", "bot@autonomousbounties.dev"))
    repo_clone_dir: str = "/tmp/bounty_repos"
    branch_prefix: str = "fix/bounty"
    timeout_seconds: int = 300


class GitOperationError(RuntimeError):
    """A git clone/push failure, with any credentials already redacted from its message."""


class AutoSubmitter:
    """
    Automatic pull request submitter for validated patches
    
    Handles:
    - Repository cloning and forking
    - Feature branch creation
    - Patch application
    - Git commit and push
    - GitHub PR creation via API
    """

    def __init__(self, config: Optional[SubmitterConfig] = None):
        """
        Initialize the auto submitter
        
        Args:
            config: SubmitterConfig instance
        """
        self.config = config or SubmitterConfig()
        self.submitter_id = f"submitter_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._redact_pattern = re.compile(re.escape(self.config.github_token)) if self.config.github_token else None
        
        # Validate configuration
        if not self.config.github_token:
            raise ValueError("GITHUB_TOKEN environment variable is required")
        if not self.config.github_username:
            raise ValueError("GITHUB_USERNAME environment variable is required")
        
        logger.info(f"🚀 AutoSubmitter initialized (ID: {self.submitter_id})")

    def _redact(self, text: str) -> str:
        """
        Strip the GitHub token out of arbitrary text before it's logged or
        persisted. The token is embedded in the authenticated clone/push URL
        (see `_clone_fork`), and git errors (GitCommandError) include the
        full command line and remote URL verbatim - without this, a single
        clone/push failure would write the live token to the log in plaintext.
        """
        if not self._redact_pattern:
            return text
        return self._redact_pattern.sub("***REDACTED***", text)

    def _configure_git(self, repo: Repo) -> None:
        """
        Set the bot's commit identity on this one clone only.

        This used to run `git config --global` once at startup, which
        silently overwrote the user's own global git identity (used by every
        other repo on their machine) with the bot's name/email. Writing to
        this clone's local config instead leaves the user's global git
        settings untouched.
        """
        try:
            with repo.config_writer() as cw:
                cw.set_value("user", "name", self.config.git_user_name)
                cw.set_value("user", "email", self.config.git_user_email)
            logger.info("✓ Git configured with bot credentials (repo-local)")
        except Exception as e:
            logger.error(f"Failed to configure git: {e}")
            raise

    def submit_patch(
        self,
        issue_id: str,
        issue_title: str,
        repository_url: str,
        repository: str,
        patch_content: str,
        issue_url: str
    ) -> SubmissionResult:
        """
        Submit a validated patch as a pull request
        
        Args:
            issue_id: Bounty issue ID
            issue_title: Issue title
            repository_url: Original repository URL
            repository: Repository name (org/repo)
            patch_content: Unified diff format patch
            issue_url: GitHub issue URL
        
        Returns:
            SubmissionResult with PR details or failure reason
        """
        logger.info(f"🔄 Starting PR submission for issue {issue_id}")
        
        try:
            # Step 1: Clone or create fork
            fork_url = self._get_or_create_fork(repository_url, repository)
            logger.info(f"✓ Fork URL: {fork_url}")

            default_branch = self._get_default_branch(repository)

            # Step 2: Clone repository
            repo_path = self._clone_fork(fork_url, issue_id)
            logger.info(f"✓ Repository cloned to: {repo_path}")

            # Step 3: Create feature branch
            repo = Repo(repo_path)
            self._configure_git(repo)
            branch_name = self._create_branch(repo, issue_id, default_branch)
            logger.info(f"✓ Feature branch created: {branch_name}")
            
            # Step 4: Apply patch
            self._apply_patch(repo, patch_content)
            logger.info(f"✓ Patch applied successfully")
            
            # Step 5: Commit changes
            commit_message = self._build_commit_message(issue_id, issue_title, issue_url)
            commit_sha = self._commit_changes(repo, commit_message)
            logger.info(f"✓ Changes committed: {commit_sha}")
            
            # Step 6: Push to remote
            self._push_branch(repo, branch_name)
            logger.info(f"✓ Branch pushed to remote")
            self._scrub_remote_credentials(repo, fork_url)

            # Step 7: Create PR
            pr_data = self._create_pull_request(
                fork_url, repository, branch_name, issue_title, issue_url, commit_message, default_branch
            )
            
            if pr_data and "html_url" in pr_data:
                result = SubmissionResult(
                    issue_id=issue_id,
                    submitter_id=self.submitter_id,
                    repository=repository,
                    fork_url=fork_url,
                    branch_name=branch_name,
                    pr_url=pr_data["html_url"],
                    pr_number=pr_data.get("number"),
                    status="PR_CREATED",
                    commit_sha=commit_sha,
                    commit_message=commit_message
                )
                logger.info(f"✅ PR successfully created: {pr_data['html_url']}")
                return result
            else:
                raise RuntimeError("Failed to retrieve PR details after creation")
        
        except Exception as e:
            # Redact defensively even here: GitCommandError/GitOperationError
            # are the known token-bearing cases, but this is the last line of
            # defense before the message is logged, put in exc_info's
            # traceback, and persisted into the returned SubmissionResult.
            redacted = self._redact(str(e))
            logger.error(f"❌ Submission failed for issue {issue_id}: {redacted}")

            # Determine error type
            status = "SUBMISSION_FAILED"
            if isinstance(e, (GitCommandError, GitOperationError)):
                status = "GIT_FAILED"

            return SubmissionResult(
                issue_id=issue_id,
                submitter_id=self.submitter_id,
                repository=repository,
                fork_url=repository_url,
                branch_name="",
                status=status,
                error_message=redacted
            )

    def _get_default_branch(self, repository: str) -> str:
        """
        Look up the target repository's actual default branch via the GitHub
        API. `_create_branch`/`_create_pull_request` used to hardcode "main"
        (with a "master" fallback for branch checkout only), which fails
        outright for repos whose default branch is neither - falling back to
        "main" here preserves that prior behavior if the lookup itself fails.
        """
        try:
            response = requests.get(
                f"{self.config.github_api_url}/repos/{repository}",
                headers={"Authorization": f"token {self.config.github_token}"},
                timeout=10
            )
            response.raise_for_status()
            return response.json().get("default_branch") or "main"
        except requests.RequestException as e:
            logger.warning(f"Failed to look up default branch for {repository}, assuming 'main': {e}")
            return "main"

    def _get_or_create_fork(self, repository_url: str, repository: str) -> str:
        """
        Get existing fork or create new one

        Args:
            repository_url: Original repository URL
            repository: Repository name (org/repo)

        Returns:
            Fork URL
        """
        org, repo_name = repository.split("/")
        
        # Try to get existing fork
        fork_url = f"https://github.com/{self.config.github_username}/{repo_name}"
        
        try:
            response = requests.head(
                fork_url,
                headers={"Authorization": f"token {self.config.github_token}"},
                timeout=10
            )
            if response.status_code == 200:
                logger.info(f"✓ Using existing fork: {fork_url}")
                return fork_url
        except requests.RequestException:
            pass
        
        # Create fork via GitHub API
        logger.info(f"Creating fork of {repository}...")
        
        headers = {
            "Authorization": f"token {self.config.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        url = f"{self.config.github_api_url}/repos/{repository}/forks"
        
        try:
            response = requests.post(
                url,
                headers=headers,
                json={},
                timeout=30
            )
            response.raise_for_status()
            fork_data = response.json()
            fork_url = fork_data["clone_url"] or fork_url
            logger.info(f"✓ Fork creation accepted, waiting for it to become clonable...")
            # The GitHub API queues fork creation and responds before the
            # fork actually exists - cloning it immediately can 404 ("git
            # clone" -> "Repository not found") even though the API call
            # above succeeded. Poll until the fork repo is reachable (or
            # give up and let the caller's clone attempt surface the error).
            self._wait_for_fork_ready(fork_url)
            return fork_url
        except requests.HTTPError as e:
            # A 4xx/5xx here means the fork was never created (most often a
            # 403 "Resource not accessible by personal access token" - the
            # configured GITHUB_TOKEN can read the repo but isn't scoped to
            # create forks). Silently falling back to the guessed fork_url
            # used to send this straight into a "git clone: Repository not
            # found" failure several steps later, which hid the real cause -
            # raise here instead so the actual GitHub API error surfaces.
            body = e.response.text[:300] if e.response is not None else str(e)
            raise GitOperationError(
                f"Failed to create fork of {repository} via GitHub API "
                f"({e.response.status_code if e.response is not None else '?'}): {body}"
            ) from None
        except requests.RequestException as e:
            logger.warning(f"Failed to create fork via API: {e}")
            # Fall back to existing fork assumption
            return fork_url

    def _wait_for_fork_ready(
        self, fork_url: str, timeout_seconds: float = 60.0, poll_interval_seconds: float = 3.0
    ) -> None:
        """Poll a freshly-created fork until GitHub reports it as reachable."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                response = requests.head(
                    fork_url,
                    headers={"Authorization": f"token {self.config.github_token}"},
                    timeout=10
                )
                if response.status_code == 200:
                    logger.info(f"✓ Fork is ready: {fork_url}")
                    return
            except requests.RequestException:
                pass
            time.sleep(poll_interval_seconds)
        logger.warning(f"Fork not confirmed ready after {timeout_seconds}s, proceeding anyway: {fork_url}")

    def _clone_fork(self, fork_url: str, issue_id: str) -> str:
        """
        Clone fork to local directory
        
        Args:
            fork_url: Fork repository URL
            issue_id: Issue ID for directory naming
        
        Returns:
            Path to cloned repository
        """
        repo_dir = Path(self.config.repo_clone_dir) / f"issue_{issue_id}"
        
        # Clean up existing directory
        if repo_dir.exists():
            import shutil
            shutil.rmtree(repo_dir, onerror=_rmtree_clearing_readonly)
            logger.info(f"Cleaned up existing directory: {repo_dir}")
        
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        
        # Add GitHub token to fork URL for authentication
        parsed_url = urlparse(fork_url)
        auth_url = f"https://{self.config.github_username}:{self.config.github_token}@{parsed_url.netloc}{parsed_url.path}"
        
        try:
            Repo.clone_from(auth_url, str(repo_dir), depth=1)
            logger.info(f"✓ Repository cloned to {repo_dir}")
            return str(repo_dir)
        except GitCommandError as e:
            # GitCommandError.__str__ includes the full command line, which
            # embeds the auth_url (and therefore the raw token) - never log
            # or re-raise it as-is.
            redacted = self._redact(str(e))
            logger.error(f"Failed to clone repository: {redacted}")
            raise GitOperationError(f"Failed to clone repository: {redacted}") from None

    def _create_branch(self, repo: Repo, issue_id: str, default_branch: str = "main") -> str:
        """
        Create and checkout feature branch

        Args:
            repo: GitPython Repo object
            issue_id: Issue ID for branch naming
            default_branch: Repository's actual default branch to branch from

        Returns:
            Branch name
        """
        branch_name = f"{self.config.branch_prefix}-issue-{issue_id}"

        try:
            # Start from the repo's real default branch; fall back to the
            # old main/master guesses if the lookup returned something that
            # isn't actually present locally (e.g. API lookup failed).
            head_names = [h.name for h in repo.heads]
            if default_branch in head_names:
                repo.heads[default_branch].checkout()
            elif "main" in head_names:
                repo.heads.main.checkout()
            else:
                repo.heads.master.checkout()

            # Create new branch
            repo.create_head(branch_name)
            repo.heads[branch_name].checkout()
            logger.info(f"✓ Branch created and checked out: {branch_name}")
            return branch_name
        except GitCommandError as e:
            logger.error(f"Failed to create branch: {e}")
            raise

    def _apply_patch(self, repo: Repo, patch_content: str) -> None:
        """
        Apply unified diff patch to repository
        
        Args:
            repo: GitPython Repo object
            patch_content: Unified diff format patch
        """
        # Write patch to temporary file
        patch_file = Path(repo.working_dir) / ".bounty_patch.diff"
        
        try:
            # newline="" is required on Windows: Path.write_text() otherwise
            # translates every "\n" to "\r\n", corrupting the diff's own line
            # endings so git apply/patch fail to match hunk context lines.
            patch_file.write_text(patch_content, encoding="utf-8", newline="")
            logger.info(f"Applying patch from {patch_file}")

            # `--recount` matters here for the same reason it does in
            # LLMSolver.apply_patch_to_repo: LLM-generated diffs often have
            # slightly-off hunk line counts that plain `git apply`/`patch`
            # reject outright, even though the same diff already applied
            # cleanly in the sandbox test stage. Without this, a patch that
            # passed testing could still fail here, on a fresh fork clone.
            result = subprocess.run(
                ["git", "apply", "--recount", "--whitespace=fix", "-p1", str(patch_file)],
                cwd=repo.working_dir,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                three_way = subprocess.run(
                    ["git", "apply", "--3way", "--recount", "--whitespace=fix", "-p1", str(patch_file)],
                    cwd=repo.working_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if three_way.returncode != 0:
                    patch_executable = self._resolve_patch_executable()
                    if not patch_executable:
                        raise RuntimeError(
                            f"Patch application failed with git apply: "
                            f"{three_way.stderr or result.stderr}"
                        )
                    logger.warning(f"git apply failed, falling back to patch: {three_way.stderr or result.stderr}")
                    fallback = subprocess.run(
                        [patch_executable, "-p1", "--fuzz=3", "-i", str(patch_file)],
                        cwd=repo.working_dir,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if fallback.returncode != 0:
                        raise RuntimeError(f"Patch application failed: {fallback.stderr or three_way.stderr or result.stderr}")

            logger.info(f"✓ Patch applied successfully")
        finally:
            # Clean up patch file
            if patch_file.exists():
                patch_file.unlink()

    @staticmethod
    def _resolve_patch_executable() -> Optional[str]:
        """Find patch on PATH or in Git for Windows' bundled usr/bin directory."""
        found = shutil.which("patch")
        if found:
            return found

        git_executable = shutil.which("git")
        if not git_executable:
            return None

        patch_name = "patch.exe" if os.name == "nt" else "patch"
        directory = Path(git_executable).resolve().parent
        for _ in range(4):
            candidate = directory / "usr" / "bin" / patch_name
            if candidate.exists():
                return str(candidate)
            if directory.parent == directory:
                break
            directory = directory.parent
        return None

    def _build_commit_message(self, issue_id: str, issue_title: str, issue_url: str) -> str:
        """
        Build commit message for the patch
        
        Args:
            issue_id: Issue ID
            issue_title: Issue title
            issue_url: GitHub issue URL
        
        Returns:
            Formatted commit message
        """
        return f"""Fix: {issue_title}

Automated fix for bounty issue: {issue_id}
Issue URL: {issue_url}

This pull request was automatically generated by the Autonomous Code Bounties Bot.
Generated at: {datetime.now().isoformat()}
"""

    def _commit_changes(self, repo: Repo, commit_message: str) -> str:
        """
        Commit changes to the repository
        
        Args:
            repo: GitPython Repo object
            commit_message: Commit message
        
        Returns:
            Commit SHA
        """
        try:
            # Stage all changes
            repo.git.add(A=True)
            
            # Commit
            repo.index.commit(commit_message)
            commit_sha = repo.head.commit.hexsha[:7]
            logger.info(f"✓ Changes committed: {commit_sha}")
            return commit_sha
        except GitCommandError as e:
            logger.error(f"Failed to commit changes: {e}")
            raise

    def _push_branch(self, repo: Repo, branch_name: str) -> None:
        """
        Push feature branch to remote
        
        Args:
            repo: GitPython Repo object
            branch_name: Branch name to push
        """
        try:
            repo.remotes.origin.push(branch_name)
            logger.info(f"✓ Branch pushed to remote")
        except GitCommandError as e:
            # The origin remote's URL still carries the auth token at this
            # point, so GitCommandError's message (command line + remote URL)
            # would otherwise leak it into the logs.
            redacted = self._redact(str(e))
            logger.error(f"Failed to push branch: {redacted}")
            raise GitOperationError(f"Failed to push branch: {redacted}") from None

    def _scrub_remote_credentials(self, repo: Repo, fork_url: str) -> None:
        """
        Once push has succeeded, the auth token is no longer needed - remove
        it from the clone's on-disk `.git/config` (GitPython's clone_from
        wrote it there verbatim as the remote URL) so it doesn't sit in
        plaintext on disk for as long as this temp clone exists.
        """
        try:
            repo.remotes.origin.set_url(fork_url)
        except GitCommandError as e:
            logger.warning(f"Could not scrub credentials from remote URL: {self._redact(str(e))}")

    def _create_pull_request(
        self,
        fork_url: str,
        repository: str,
        branch_name: str,
        issue_title: str,
        issue_url: str,
        commit_message: str,
        base_branch: str = "main"
    ) -> Dict[str, Any]:
        """
        Create pull request via GitHub API

        Args:
            fork_url: Fork repository URL
            repository: Target repository (org/repo)
            branch_name: Feature branch name
            issue_title: Issue title for PR title
            issue_url: GitHub issue URL
            commit_message: Commit message for PR body
            base_branch: Repository's actual default branch to open the PR against

        Returns:
            PR response data from GitHub API
        """
        headers = {
            "Authorization": f"token {self.config.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        pr_title = f"Fix: {issue_title} (Automated)"
        pr_body = f"""## Automated Fix

**Issue**: {issue_url}

**What**: Automated fix for the reported issue

**Changes**: 
```
{commit_message}
```

**Testing**: This fix was validated in an isolated Docker sandbox before submission.

**Note**: This PR was automatically generated by the Autonomous Code Bounties Bot.

---
Generated at: {datetime.now().isoformat()}
"""
        
        url = f"{self.config.github_api_url}/repos/{repository}/pulls"
        
        payload = {
            "title": pr_title,
            "body": pr_body,
            "head": f"{self.config.github_username}:{branch_name}",
            "base": base_branch
        }
        
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            pr_data = response.json()
            logger.info(f"✓ PR created successfully: {pr_data['html_url']}")
            return pr_data
        except requests.RequestException as e:
            logger.error(f"Failed to create PR: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise

    def save_submission_result(self, result: SubmissionResult, output_path: str) -> None:
        """
        Save submission result to JSON file
        
        Args:
            result: SubmissionResult object
            output_path: Path to save JSON file
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(mode='json'), f, indent=2, ensure_ascii=False)
        logger.info(f"✓ Submission result saved: {output_path}")

    @staticmethod
    def load_submission_result(json_path: str) -> SubmissionResult:
        """
        Load submission result from JSON file
        
        Args:
            json_path: Path to JSON file
        
        Returns:
            SubmissionResult object
        """
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SubmissionResult(**data)
