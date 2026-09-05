"""
Phase 4: LLM Solver Module
Generates patches for identified Issues using Google Gemini API

Author: Autonomous Code Bounties Bot
Created: 2026-09-01
"""

import os
import re
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
import subprocess
import tempfile
import shutil

from pydantic import BaseModel, Field
import google.generativeai as genai
import yaml
from git import Repo
from git.exc import GitCommandError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StackTrace(BaseModel):
    """Represents a single stack trace entry"""
    file_path: str
    function_name: str
    line_number: int
    code_line: str
    error_message: Optional[str] = None


class CodeSnippet(BaseModel):
    """Represents a code snippet"""
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str
    relevance_score: float
    context: str


class CodeContext(BaseModel):
    """Context extracted from Issue by CodeIngestor"""
    issue_id: str
    repository: str
    repository_url: str
    language: str
    stack_traces: List[StackTrace]
    code_snippets: List[CodeSnippet]
    related_files: List[str]
    summary: str
    extracted_at: datetime
    repository_branch: str = "main"
    clone_size_mb: float = 0.0


class PatchResult(BaseModel):
    """Result of patch generation"""
    issue_id: str
    solver_id: str
    original_code: str
    patched_code: str
    diff: str
    files_affected: List[str]
    changes_summary: str
    patch_size_bytes: int
    confidence_score: float = Field(ge=0.0, le=1.0)
    generated_at: datetime
    model_used: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class SolverConfig(BaseModel):
    """Configuration for LLM Solver"""
    model: str = "gemini-3.1-pro-preview"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout_seconds: int = 60


class LLMSolver:
    """
    LLM-based solver for generating patches
    
    Workflow:
    1. Build system and user prompts from Issue context
    2. Call Gemini API to generate patch
    3. Parse unified diff format
    4. Validate patch quality
    5. Return PatchResult
    """
    
    def __init__(self, config: Optional[SolverConfig] = None):
        """Initialize LLMSolver with configuration"""
        self.config = config or SolverConfig()
        self.solver_id = self._generate_solver_id()
        
        # Load settings from YAML
        self.settings = self._load_settings()
        
        # Initialize Gemini API
        api_key = os.getenv("GEMINI_API_KEY", self.settings.get("llm", {}).get("api_key"))
        if not api_key or api_key.startswith("${"):
            raise ValueError("GEMINI_API_KEY not set in environment or settings.yaml")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(self.config.model)
        
        logger.info(f"LLMSolver initialized (ID: {self.solver_id})")
    
    def _generate_solver_id(self) -> str:
        """Generate unique solver ID for tracking"""
        import uuid
        return f"solver-{uuid.uuid4().hex[:8]}"
    
    def _load_settings(self) -> Dict[str, Any]:
        """Load configuration from settings.yaml"""
        settings_path = Path(__file__).parent.parent / "config" / "settings.yaml"
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"settings.yaml not found at {settings_path}")
            return {}
    
    def solve_issue(
        self,
        issue_id: str,
        issue_title: str,
        issue_description: str,
        code_context: CodeContext,
        repository_path: str
    ) -> PatchResult:
        """
        Main entry point: Generate patch for Issue
        
        Args:
            issue_id: Unique Issue identifier
            issue_title: Issue title
            issue_description: Full Issue description
            code_context: CodeContext from Ingestor
            repository_path: Path to cloned repository
        
        Returns:
            PatchResult containing generated patch
        
        Raises:
            ValueError: If context is invalid
            RuntimeError: If API call fails
        """
        logger.info(f"Solving issue {issue_id}...")
        
        try:
            # Build prompts
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(
                issue_id, issue_title, issue_description, code_context
            )
            
            logger.debug(f"System prompt ({len(system_prompt)} chars)")
            logger.debug(f"User prompt ({len(user_prompt)} chars)")
            
            # Call Gemini API
            llm_response = self._call_gemini_api(system_prompt, user_prompt)
            
            # Parse response
            diff_text = self._extract_diff_from_response(llm_response)
            changes_summary = self._extract_summary_from_response(llm_response)
            
            # Validate diff
            files_affected = self._parse_diff(diff_text)
            confidence_score = self._calculate_confidence_score(diff_text, len(files_affected))
            
            # Create PatchResult
            patch_result = PatchResult(
                issue_id=issue_id,
                solver_id=self.solver_id,
                original_code=self._read_original_code(repository_path, files_affected),
                patched_code=self._read_patched_code_from_diff(diff_text),
                diff=diff_text,
                files_affected=files_affected,
                changes_summary=changes_summary,
                patch_size_bytes=len(diff_text.encode('utf-8')),
                confidence_score=confidence_score,
                generated_at=datetime.now(),
                model_used=self.config.model,
                prompt_tokens=len(user_prompt.split()),
                completion_tokens=len(llm_response.split())
            )
            
            logger.info(f"✓ Issue {issue_id} solved (confidence: {confidence_score:.2f})")
            return patch_result
        
        except Exception as e:
            logger.error(f"✗ Failed to solve issue {issue_id}: {str(e)}")
            raise
    
    def _build_system_prompt(self) -> str:
        """Build system prompt defining LLM role and responsibilities"""
        return """You are a senior open-source software engineer specializing in rapid bug fixes.

Your task: Analyze the provided Issue description and code context, then generate a unified diff format patch.

Requirements:
1. Carefully analyze stack traces and related code snippets
2. Generate a minimal, targeted patch that directly addresses the root cause
3. Output MUST be in unified diff format (starting with --- and +++ lines)
4. Avoid unnecessary formatting changes or refactoring
5. Ensure the fix addresses the fundamental issue, not just symptoms
6. Include a brief explanation of the fix before the diff

Output format:
---
Explanation: [1-2 sentences explaining the fix]

[Unified diff format patch]
---"""
    
    def _build_user_prompt(
        self,
        issue_id: str,
        issue_title: str,
        issue_description: str,
        code_context: CodeContext
    ) -> str:
        """Build user prompt with Issue context"""
        
        # Format stack traces
        stack_traces_text = ""
        if code_context.stack_traces:
            stack_traces_text = "Stack Traces:\n"
            for i, st in enumerate(code_context.stack_traces, 1):
                stack_traces_text += f"{i}. File: {st.file_path}, Line {st.line_number}\n"
                stack_traces_text += f"   Function: {st.function_name}\n"
                stack_traces_text += f"   Code: {st.code_line}\n"
                if st.error_message:
                    stack_traces_text += f"   Error: {st.error_message}\n"
        
        # Format code snippets
        code_snippets_text = ""
        if code_context.code_snippets:
            code_snippets_text = "\nRelevant Code Snippets:\n"
            for i, snippet in enumerate(code_context.code_snippets, 1):
                code_snippets_text += f"\n{i}. {snippet.file_path} (lines {snippet.start_line}-{snippet.end_line}):\n"
                code_snippets_text += f"```{snippet.language}\n{snippet.content}\n```\n"
        
        # Build complete prompt
        prompt = f"""Issue ID: {issue_id}
Repository: {code_context.repository}
Language: {code_context.language}
Branch: {code_context.repository_branch}

Issue Title:
{issue_title}

Issue Description:
{issue_description}

{stack_traces_text}
{code_snippets_text}

Related Files:
{', '.join(code_context.related_files) if code_context.related_files else 'N/A'}

Context Summary:
{code_context.summary}

Task: Generate a unified diff format patch to fix this issue.
The patch should be directly applicable to the repository's {code_context.repository_branch} branch.
Focus on the minimal changes needed to resolve the issue."""
        
        return prompt
    
    def _call_gemini_api(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call Gemini API to generate patch
        
        Args:
            system_prompt: System prompt defining role
            user_prompt: User prompt with Issue context
        
        Returns:
            API response text
        
        Raises:
            RuntimeError: If API call fails
        """
        try:
            logger.info(f"Calling Gemini API (model: {self.config.model})...")
            
            response = self.model.generate_content(
                f"{system_prompt}\n\n{user_prompt}",
                generation_config=genai.types.GenerationConfig(
                    temperature=self.config.temperature,
                    max_output_tokens=self.config.max_tokens
                )
            )
            
            if response.text:
                logger.info("✓ API response received")
                return response.text
            else:
                raise RuntimeError("Empty response from Gemini API")
        
        except Exception as e:
            logger.error(f"✗ Gemini API call failed: {str(e)}")
            raise RuntimeError(f"Gemini API error: {str(e)}")
    
    def _extract_diff_from_response(self, response: str) -> str:
        """Extract unified diff from LLM response"""
        # Find the first occurrence of --- (diff start marker)
        start = response.find('--- ')
        if start == -1:
            start = response.find('---')
            if start == -1:
                raise ValueError("No unified diff found in API response")
        
        # Extract from --- onwards
        rest = response[start:]
        lines = rest.split('\n')
        
        diff_lines = []
        in_diff = False
        
        for line in lines:
            # Unified diff lines start with ---, +++, @@, +, -, or space
            if line.startswith(('--- ', '+++ ', '@@', '-', '+', ' ')):
                in_diff = True
                diff_lines.append(line)
            elif in_diff:
                # Stop when we hit a line that doesn't look like diff
                if line.strip() and not line.startswith(('--- ', '+++ ', '@@', '-', '+', ' ', '\\')):
                    break
                elif line.strip() == '':
                    # Keep empty lines within diff
                    diff_lines.append(line)
                else:
                    diff_lines.append(line)
        
        if not diff_lines:
            raise ValueError("No unified diff found in API response")
        
        diff = '\n'.join(diff_lines).strip()
        return diff
    
    def _extract_summary_from_response(self, response: str) -> str:
        """Extract brief summary/explanation from response"""
        # Look for "Explanation:" section
        if 'Explanation:' in response:
            start = response.find('Explanation:') + len('Explanation:')
            end = response.find('\n---', start)
            if end == -1:
                end = response.find('---', start)
            if end == -1:
                end = min(start + 200, len(response))
            return response[start:end].strip()
        
        # Fallback: first 200 chars before diff
        if '---' in response:
            start = response.find('---')
            return response[:start].strip()[:200]
        
        return "Patch generated to fix the issue"
    
    def _parse_diff(self, diff: str) -> List[str]:
        """
        Parse unified diff and extract affected files
        
        Args:
            diff: Unified diff format string
        
        Returns:
            List of affected file paths
        
        Raises:
            ValueError: If diff format is invalid
        """
        files = []
        
        # Unified diff format: --- a/path/to/file +++ b/path/to/file
        file_pattern = r'^---\s+a/(.+?)\n\+\+\+\s+b/(.+?)$'
        matches = re.findall(file_pattern, diff, re.MULTILINE)
        
        for old_path, new_path in matches:
            if new_path not in files:
                files.append(new_path)
        
        if not files:
            raise ValueError("No files found in diff")
        
        logger.info(f"Diff affects {len(files)} file(s): {files}")
        return files
    
    def _calculate_confidence_score(self, diff: str, num_files: int) -> float:
        """
        Calculate confidence score for patch quality
        
        Factors:
        - Diff size (too small = incomplete, too large = risky)
        - Number of files (1-3 is ideal)
        - Diff structure validity
        
        Returns:
            Float between 0.0 and 1.0
        """
        score = 0.5  # Start with neutral score
        
        diff_lines = len([l for l in diff.split('\n') if l.startswith(('+', '-', '@@'))])
        
        # Size factor: 10-200 lines is ideal
        if 10 <= diff_lines <= 200:
            score += 0.3
        elif 5 <= diff_lines < 300:
            score += 0.15
        
        # File count factor: 1-3 files is ideal
        if 1 <= num_files <= 3:
            score += 0.15
        elif num_files <= 5:
            score += 0.05
        
        # Heuristic: check for common patterns
        if '@@' in diff and '---' in diff and '+++' in diff:
            score += 0.05
        
        # Sanity check
        score = min(1.0, max(0.0, score))
        
        logger.info(f"Confidence score: {score:.2f}")
        return score
    
    def _read_original_code(self, repo_path: str, files: List[str]) -> str:
        """Read original code from affected files"""
        try:
            code = ""
            for file_path in files[:3]:  # Limit to first 3 files
                full_path = os.path.join(repo_path, file_path)
                if os.path.exists(full_path):
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        code += f"--- {file_path} ---\n{content[:500]}\n"
            return code[:2000]  # Limit total size
        except Exception as e:
            logger.warning(f"Failed to read original code: {e}")
            return ""
    
    def _read_patched_code_from_diff(self, diff: str) -> str:
        """Extract patched code from diff"""
        # Extract lines starting with + (new code)
        lines = []
        for line in diff.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                lines.append(line[1:])
        
        return '\n'.join(lines[:100])  # Limit to first 100 lines
    
    def apply_patch_to_repo(
        self,
        patch_result: PatchResult,
        repository_path: str
    ) -> bool:
        """
        Apply patch to local repository (dry-run first)
        
        Args:
            patch_result: PatchResult from solve_issue
            repository_path: Path to repository
        
        Returns:
            True if patch applied successfully
        """
        try:
            logger.info(f"Applying patch to {repository_path}...")
            
            # Write patch to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
                f.write(patch_result.diff)
                patch_file = f.name
            
            try:
                # Dry run first
                result = subprocess.run(
                    ['patch', '--dry-run', '-p1', '-i', patch_file],
                    cwd=repository_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode != 0:
                    logger.error(f"Patch dry-run failed: {result.stderr}")
                    return False
                
                logger.info("✓ Patch dry-run successful")
                
                # Actually apply
                result = subprocess.run(
                    ['patch', '-p1', '-i', patch_file],
                    cwd=repository_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    logger.info("✓ Patch applied successfully")
                    return True
                else:
                    logger.error(f"Patch application failed: {result.stderr}")
                    return False
            
            finally:
                # Cleanup temp file
                os.unlink(patch_file)
        
        except Exception as e:
            logger.error(f"✗ Error applying patch: {e}")
            return False
    
    def save_result(self, patch_result: PatchResult, output_path: str) -> None:
        """Save PatchResult to JSON file"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(patch_result.model_dump(mode='json'), f, indent=2, default=str)
            logger.info(f"✓ Result saved to {output_path}")
        except Exception as e:
            logger.error(f"✗ Failed to save result: {e}")
            raise
    
    def load_result(self, input_path: str) -> PatchResult:
        """Load PatchResult from JSON file"""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return PatchResult(**data)
        except Exception as e:
            logger.error(f"✗ Failed to load result: {e}")
            raise


# Example usage
if __name__ == "__main__":
    print("LLMSolver module loaded")
