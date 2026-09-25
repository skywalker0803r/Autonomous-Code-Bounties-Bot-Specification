"""
Code Ingestor Module - Phase 3 Implementation
提取 Issue 相關的代碼上下文和堆棧跟蹤

功能：
1. Shallow clone target repository
2. Extract stack traces from issue description
3. Use AST (Python) or Tree-sitter to parse code context
4. Generate compressed code snippets for LLM input
"""

import os
import re
import json
import logging
import tempfile
import shutil
import ast
from typing import List, Dict, Optional, Tuple, Set
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from dataclasses import dataclass, field, asdict
from pydantic import BaseModel, Field
import requests
from git import Repo
from git.exc import GitCommandError

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Common words filtered out of issue-text/file-path keyword matching in
# CodeIngestor._find_related_files - generic enough (endpoint, missing, api,
# src, ...) that matching on them would rank files no more relevantly than
# not matching at all.
_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "into", "your",
    "issue", "bounty", "bug", "fix", "add", "adds", "added", "should",
    "when", "where", "what", "reissue", "via", "via", "api", "app", "apps",
    "src", "lib", "index", "test", "tests", "missing", "endpoint", "route",
    "routes", "file", "files", "code", "does", "not", "can", "using",
}


# ==================== Data Models ====================

class CodeSnippet(BaseModel):
    """Single code snippet with context"""
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)
    context: str = ""  # 代碼片段的上下文描述

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class StackTrace(BaseModel):
    """Extracted stack trace from issue"""
    file_path: str
    function_name: str
    line_number: int
    code_line: str
    error_message: str = ""

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class CodeContext(BaseModel):
    """Complete code context for an issue"""
    issue_id: str
    repository: str
    repository_url: str
    language: str
    repository_path: str = ""
    
    # Stack traces found in issue description
    stack_traces: List[StackTrace] = Field(default_factory=list)
    
    # Code snippets extracted from repository
    code_snippets: List[CodeSnippet] = Field(default_factory=list)
    
    # Relevant file paths for issue
    related_files: List[str] = Field(default_factory=list)

    # Sample of the repository's file tree, for context on structure/naming
    # conventions when the issue calls for a new file rather than an edit.
    repository_file_list: List[str] = Field(default_factory=list)

    # Summary of context
    summary: str = ""
    
    # Metadata
    extracted_at: datetime = Field(default_factory=datetime.now)
    repository_branch: str = "main"
    clone_size_mb: float = 0.0

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ==================== Stack Trace Extractor ====================

class StackTraceExtractor:
    """Extract stack traces from issue description"""

    # Common stack trace patterns for different languages
    PATTERNS = {
        'python': [
            r'File\s+"([^"]+)",\s+line\s+(\d+),\s+in\s+(\w+)\s+(.*)',
            r'(\S+\.py):(\d+):\s+(\w+):\s+(.*)',
            r'Traceback.*?(?=Traceback|\Z)',
        ],
        'javascript': [
            r'at\s+(\w+)\s+\(([^:]+):(\d+):(\d+)\)',
            r'at\s+([^:]+):(\d+):(\d+)',
        ],
        'typescript': [
            r'at\s+(\w+)\s+\(([^:]+):(\d+):(\d+)\)',
            r'at\s+([^:]+):(\d+):(\d+)',
        ],
        'rust': [
            r'(?:at\s+)?([^\s():]+\.rs):(\d+)(?::\d+)?',
        ],
    }

    @staticmethod
    def extract_from_text(text: str, language: str = "python") -> List[StackTrace]:
        """
        Extract stack traces from issue description
        
        Args:
            text: Issue description text
            language: Programming language (for pattern matching)
        
        Returns:
            List of StackTrace objects
        """
        stack_traces = []
        language = (language or "").lower()
        patterns = StackTraceExtractor.PATTERNS.get(language, [])
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.MULTILINE | re.DOTALL)
            for match in matches:
                try:
                    groups = match.groups()
                    if language == 'python' and len(groups) >= 4:
                        stack_trace = StackTrace(
                            file_path=groups[0],
                            line_number=int(groups[1]),
                            function_name=groups[2],
                            code_line=groups[3] if len(groups) > 3 else "",
                            error_message=""
                        )
                        stack_traces.append(stack_trace)
                    elif language in ['javascript', 'typescript'] and len(groups) >= 3:
                        # JavaScript/TypeScript format
                        stack_trace = StackTrace(
                            file_path=groups[1] if len(groups) > 1 else "",
                            function_name=groups[0],
                            line_number=int(groups[2]),
                            code_line=""
                        )
                        stack_traces.append(stack_trace)
                    elif language == 'rust' and len(groups) >= 2:
                        stack_traces.append(StackTrace(
                            file_path=groups[0],
                            function_name="<unknown>",
                            line_number=int(groups[1]),
                            code_line=""
                        ))
                except (ValueError, IndexError) as e:
                    logger.debug(f"Failed to parse stack trace: {e}")
                    continue
        
        logger.info(f"Extracted {len(stack_traces)} stack traces from issue description")
        return stack_traces


# ==================== Code Parser ====================

class CodeParser:
    """Parse code and extract relevant context using AST"""

    @staticmethod
    def parse_python_file(file_path: str) -> Dict[str, any]:
        """
        Parse Python file using AST
        
        Returns:
            Dict with functions, classes, and line mapping
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            
            functions = []
            classes = []
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append({
                        'name': node.name,
                        'start_line': node.lineno,
                        'end_line': node.end_lineno or node.lineno,
                        'args': [arg.arg for arg in node.args.args],
                    })
                elif isinstance(node, ast.ClassDef):
                    classes.append({
                        'name': node.name,
                        'start_line': node.lineno,
                        'end_line': node.end_lineno or node.lineno,
                        'methods': [
                            n.name for n in node.body
                            if isinstance(n, ast.FunctionDef)
                        ]
                    })
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.name)
                    else:
                        imports.append(node.module or "")
            
            return {
                'file_path': file_path,
                'functions': functions,
                'classes': classes,
                'imports': list(set(imports)),
                'lines': content.split('\n'),
                'total_lines': len(content.split('\n'))
            }
        
        except Exception as e:
            logger.error(f"Failed to parse Python file {file_path}: {e}")
            return {}

    @staticmethod
    def extract_function(file_path: str, function_name: str) -> Optional[CodeSnippet]:
        """
        Extract specific function from Python file
        
        Args:
            file_path: Path to Python file
            function_name: Function name to extract
        
        Returns:
            CodeSnippet or None if not found
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == function_name:
                    start_line = node.lineno
                    end_line = node.end_lineno or node.lineno
                    
                    content = ''.join(lines[start_line - 1:end_line])
                    
                    return CodeSnippet(
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        content=content,
                        language='python',
                        context=f"Function: {function_name}"
                    )
        
        except Exception as e:
            logger.debug(f"Failed to extract function {function_name}: {e}")
        
        return None

    @staticmethod
    def get_lines_around(file_path: str, line_number: int, context_lines: int = 5) -> Optional[CodeSnippet]:
        """
        Get code snippet around a specific line
        
        Args:
            file_path: Path to code file
            line_number: Line number (1-indexed)
            context_lines: Number of lines to include before/after
        
        Returns:
            CodeSnippet or None if not found
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            start = max(0, line_number - context_lines - 1)
            end = min(len(lines), line_number + context_lines)
            
            content = ''.join(lines[start:end])
            
            return CodeSnippet(
                file_path=file_path,
                start_line=start + 1,
                end_line=end,
                content=content,
                language=CodeParser.detect_language(file_path),
                context=f"Context around line {line_number}"
            )
        
        except Exception as e:
            logger.debug(f"Failed to extract context around {file_path}:{line_number}: {e}")
        
        return None

    @staticmethod
    def read_whole_file(
        file_path: str, display_path: str, max_lines: int = 300
    ) -> Optional[CodeSnippet]:
        """
        Read a file's actual content as-is.

        There's no AST-based extractor here for non-Python languages, and
        without one, related non-Python files contributed nothing to the
        prompt at all - the LLM only ever saw their path, not their
        content, and had to guess/hallucinate the code it was meant to
        patch. Capped at max_lines so one huge file can't blow the prompt.
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()

            truncated = len(lines) > max_lines
            content = ''.join(lines[:max_lines])
            if truncated:
                content += f"\n... ({len(lines) - max_lines} more lines truncated)\n"

            return CodeSnippet(
                file_path=display_path,
                start_line=1,
                end_line=min(len(lines), max_lines),
                content=content,
                language=CodeParser.detect_language(file_path),
                context="File content (truncated)" if truncated else "Full file content"
            )
        except Exception as e:
            logger.debug(f"Failed to read {file_path}: {e}")
            return None

    @staticmethod
    def detect_language(file_path: str) -> str:
        """Detect programming language from file extension"""
        ext_to_lang = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.jsx': 'javascript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.go': 'go',
            '.rs': 'rust',
            '.rb': 'ruby',
            '.php': 'php',
        }
        ext = Path(file_path).suffix.lower()
        return ext_to_lang.get(ext, 'unknown')


# ==================== Code Ingestor ====================

class CodeIngestor:
    """
    Main code ingestor for extracting repository context
    
    Responsibilities:
    1. Shallow clone target repository
    2. Extract stack traces from issue description
    3. Find related code files and functions
    4. Generate compressed code snippets for LLM
    """

    def __init__(self, cache_dir: str = "/tmp/bounty_cache/repos"):
        """
        Initialize the code ingestor
        
        Args:
            cache_dir: Directory to cache cloned repositories
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        logger.info(f"CodeIngestor initialized with cache directory: {cache_dir}")

    def ingest_issue(
        self,
        issue_id: str,
        repository_url: str,
        repository: str,
        language: str,
        issue_title: str,
        issue_description: str,
        branch: str = "main"
    ) -> Optional[CodeContext]:
        """
        Main ingest method: clone repo and extract context
        
        Args:
            issue_id: Issue identifier
            repository_url: GitHub repository URL
            repository: Repository name (owner/repo)
            language: Programming language
            issue_title: Issue title
            issue_description: Issue description with stack traces
            branch: Branch to clone (default: main)
        
        Returns:
            CodeContext object or None if failed
        """
        logger.info(f"Starting ingestion for issue {issue_id} in {repository}")
        
        # Step 1: Extract stack traces from issue description
        stack_traces = StackTraceExtractor.extract_from_text(
            issue_description,
            language=language
        )
        
        # Step 2: Shallow clone repository (always clones the repo's actual
        # default branch - see _clone_repository - so re-derive the real
        # branch name rather than trusting the caller-supplied guess).
        repo_path = self._clone_repository(repository_url, branch)
        if not repo_path:
            logger.error(f"Failed to clone repository {repository_url}")
            return None

        try:
            branch = Repo(repo_path).active_branch.name
        except Exception:
            pass  # keep the caller-supplied guess (e.g. detached HEAD)
        
        # Step 3: Find related files based on stack traces
        related_files = self._find_related_files(
            repo_path,
            stack_traces,
            language,
            issue_title,
            issue_description
        )
        repository_file_list = self._list_repository_files(repo_path)

        # Step 4: Extract code snippets
        code_snippets = self._extract_code_snippets(
            repo_path,
            related_files,
            stack_traces,
            language
        )

        # Step 5: Generate summary
        summary = self._generate_context_summary(
            issue_title,
            issue_description,
            stack_traces,
            code_snippets
        )

        # Calculate repository size
        repo_size_mb = self._get_directory_size(repo_path) / (1024 * 1024)

        # Create CodeContext object
        context = CodeContext(
            issue_id=issue_id,
            repository=repository,
            repository_url=repository_url,
            language=language,
            repository_path=repo_path,
            stack_traces=stack_traces,
            code_snippets=code_snippets,
            related_files=related_files,
            repository_file_list=repository_file_list,
            summary=summary,
            repository_branch=branch,
            clone_size_mb=repo_size_mb
        )

        logger.info(f"✓ Successfully ingested issue {issue_id}: "
                   f"{len(stack_traces)} traces, {len(code_snippets)} snippets")

        return context

    def _clone_repository(self, repo_url: str, branch: str = "main") -> Optional[str]:
        """
        Shallow clone repository

        Args:
            repo_url: Git repository URL
            branch: Unused for the clone itself (kept for signature/API
                compatibility) - always clones the repo's actual default
                branch instead of guessing "main"/"master", since plenty of
                real repos use neither.

        Returns:
            Path to cloned repository or None if failed
        """
        # Only ever hand plain https:// URLs to `git clone`. Git supports
        # other transports (ext::, fd::, file://, ssh with arbitrary hosts)
        # that can run arbitrary commands or read local files if a URL from
        # an untrusted source ever reaches here - bounty repo URLs are
        # expected to always be GitHub's own https clone_url.
        if urlparse(repo_url).scheme != "https":
            logger.error(f"Refusing to clone non-https repository URL: {repo_url}")
            return None

        try:
            # Create unique directory for this clone
            repo_name = repo_url.split('/')[-1].replace('.git', '')
            clone_path = os.path.join(self.cache_dir, f"{repo_name}_{datetime.now().timestamp()}")

            logger.info(f"Shallow cloning {repo_url} to {clone_path}")

            # Use shallow clone (--depth=1) to minimize bandwidth and time.
            # Deliberately not passing branch=... : that forces git to
            # resolve a specific ref instead of following the remote's
            # actual default, which fails outright for any repo whose
            # default branch isn't "main"/"master".
            repo = Repo.clone_from(
                repo_url,
                clone_path,
                depth=1,
                no_checkout=False
            )

            logger.info(f"✓ Successfully cloned repository to {clone_path}")
            return clone_path

        except GitCommandError as e:
            logger.error(f"Git clone failed for {repo_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to clone repository {repo_url}: {e}")
            return None

    # Maps a GitHub repo's primary "language" (as reported by the GitHub API)
    # to the source extensions worth scanning for it. Kept broad since a
    # narrow map means any repo whose primary language isn't listed here
    # silently yields zero related files, even though the repo is full of
    # relevant code.
    LANGUAGE_EXTENSIONS = {
        'python': ['.py'],
        'javascript': ['.js', '.jsx', '.mjs', '.cjs'],
        'typescript': ['.ts', '.tsx'],
        'java': ['.java'],
        'go': ['.go'],
        'rust': ['.rs'],
        'c': ['.c', '.h'],
        'c++': ['.cpp', '.cc', '.cxx', '.hpp', '.hh'],
        'c#': ['.cs'],
        'ruby': ['.rb'],
        'php': ['.php'],
        'swift': ['.swift'],
        'kotlin': ['.kt', '.kts'],
        'scala': ['.scala'],
        'shell': ['.sh', '.bash'],
        'markdown': ['.md', '.mdx'],
        'html': ['.html', '.htm'],
        'css': ['.css', '.scss'],
    }

    # Used when the repo's language is unmapped (e.g. "Markdown"/"Unknown"
    # for doc- or skill-only repos) or yields nothing, so those repos still
    # get a usable file list instead of an empty one.
    FALLBACK_EXTENSIONS = sorted(
        {ext for exts in LANGUAGE_EXTENSIONS.values() for ext in exts}
        | {'.json', '.yaml', '.yml', '.txt'}
    )

    def _find_related_files(
        self,
        repo_path: str,
        stack_traces: List[StackTrace],
        language: str,
        issue_title: str = "",
        issue_description: str = ""
    ) -> List[str]:
        """
        Find files related to the issue

        Args:
            repo_path: Path to cloned repository
            stack_traces: Stack traces extracted from issue
            language: Programming language
            issue_title: Issue title, used to rank files by relevance
            issue_description: Issue description, used to rank files by relevance

        Returns:
            List of related file paths (relative to repo), most relevant first
        """
        stack_trace_files = set()

        # Add files from stack traces
        for trace in stack_traces:
            file_path = os.path.join(repo_path, trace.file_path.lstrip('/'))
            if os.path.exists(file_path):
                stack_trace_files.add(trace.file_path)
                logger.debug(f"Found stack trace file: {trace.file_path}")

        # Search for files matching the repo's language extension(s). If the
        # language is unmapped, or the language-specific scan comes up
        # empty, fall back to a broad extension set instead of giving up
        # (e.g. a skills/doc repo whose GitHub "language" is Markdown).
        extensions = self.LANGUAGE_EXTENSIONS.get((language or '').lower(), [])
        found_by_extension = self._scan_files_by_extension(repo_path, extensions) if extensions else set()

        if not found_by_extension:
            found_by_extension = self._scan_files_by_extension(repo_path, self.FALLBACK_EXTENSIONS)

        all_files = stack_trace_files | found_by_extension
        logger.info(f"Found {len(all_files)} related files")

        # `_scan_files_by_extension` returns whatever os.walk/set ordering
        # happens to produce, which has no relation to the issue - on a repo
        # with more matching files than the cap below, that silently drops
        # the file the issue is actually about while keeping unrelated ones.
        # Rank by keyword overlap with the issue text first so the truncation
        # keeps the files that matter; stack-trace files always sort first
        # since they're a confirmed hit, not a guess.
        keywords = self._extract_keywords(f"{issue_title} {issue_description}")

        def relevance(file_rel: str) -> tuple:
            is_stack_trace_file = file_rel in stack_trace_files
            path_words = self._extract_keywords(file_rel.replace('/', ' ').replace('_', ' '))
            score = len(keywords & path_words)
            return (is_stack_trace_file, score)

        ranked = sorted(all_files, key=relevance, reverse=True)
        return ranked[:20]

    @staticmethod
    def _extract_keywords(text: str) -> Set[str]:
        """Lowercase, camelCase/snake_case/path-aware word set for simple relevance matching."""
        # Split camelCase ("reviewRoutes" -> "review Routes") before the
        # generic non-alnum split, so path/identifier words match issue
        # text words regardless of casing convention.
        spaced = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', text)
        words = re.findall(r'[a-zA-Z]{3,}', spaced.lower())
        # Crude singular/plural normalization ("reviews" endpoint vs.
        # "review"Controller.js) - stripping a trailing 's' handles the
        # common case without pulling in a real stemmer for this.
        normalized = {w[:-1] if len(w) > 4 and w.endswith('s') else w for w in words}
        return {w for w in normalized if w not in _STOPWORDS}

    def _scan_files_by_extension(self, repo_path: str, extensions: List[str], limit: int = 2000) -> Set[str]:
        """
        Walk the repo and collect file paths matching any of `extensions`.

        `limit` is a safety ceiling for pathological repos, not the final
        related-file count - it used to default to 20 and return as soon as
        that many were found in raw os.walk order, which silently dropped
        the file an issue was actually about on any repo with >20 matching
        files (walk order has nothing to do with relevance). Callers rank
        and truncate the real candidate list themselves.
        """
        found: Set[str] = set()
        for root, dirs, files in os.walk(repo_path):
            # Skip common non-code directories
            dirs[:] = [d for d in dirs if d not in [
                '.git', '__pycache__', 'node_modules', '.venv',
                'venv', 'dist', 'build', '.pytest_cache'
            ]]

            for file in files:
                if len(found) >= limit:
                    return found
                if any(file.endswith(ext) for ext in extensions):
                    rel_path = os.path.relpath(os.path.join(root, file), repo_path).replace(os.sep, '/')
                    found.add(rel_path)
        return found

    def _list_repository_files(self, repo_path: str, limit: int = 60) -> List[str]:
        """
        List a sample of the repository's file paths, regardless of
        language, so the LLM has some awareness of project structure and
        naming conventions even when no single file is clearly "related"
        (e.g. a request to add a brand-new file).
        """
        paths: List[str] = []
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in [
                '.git', '__pycache__', 'node_modules', '.venv',
                'venv', 'dist', 'build', '.pytest_cache'
            ]]
            for file in sorted(files):
                if len(paths) >= limit:
                    return paths
                paths.append(os.path.relpath(os.path.join(root, file), repo_path).replace(os.sep, '/'))
        return paths

    def _extract_code_snippets(
        self,
        repo_path: str,
        related_files: List[str],
        stack_traces: List[StackTrace],
        language: str
    ) -> List[CodeSnippet]:
        """
        Extract code snippets from related files
        
        Args:
            repo_path: Path to cloned repository
            related_files: List of related file paths
            stack_traces: Stack traces to extract context around
            language: Programming language
        
        Returns:
            List of CodeSnippet objects
        """
        snippets = []
        
        # Extract snippets around stack trace lines
        for trace in stack_traces:
            file_path = os.path.join(repo_path, trace.file_path.lstrip('/'))
            if os.path.exists(file_path):
                snippet = CodeParser.get_lines_around(
                    file_path,
                    trace.line_number,
                    context_lines=5
                )
                if snippet:
                    snippet.relevance_score = 1.0
                    snippets.append(snippet)
                    logger.debug(f"Extracted snippet from {trace.file_path}:{trace.line_number}")
        
        # Extract top-level functions/classes from related files
        for file_rel in related_files[:5]:  # Limit to first 5 files
            file_path = os.path.join(repo_path, file_rel)
            if not os.path.exists(file_path):
                continue

            if file_rel.endswith('.py'):
                try:
                    parsed = CodeParser.parse_python_file(file_path)

                    # Extract key functions
                    for func in parsed.get('functions', [])[:3]:  # Top 3 functions
                        snippet = CodeParser.extract_function(file_path, func['name'])
                        if snippet:
                            snippet.relevance_score = 0.7
                            snippets.append(snippet)

                except Exception as e:
                    logger.debug(f"Failed to parse {file_rel}: {e}")
            else:
                # No AST-based extractor for non-Python languages (JS/TS/Go/
                # etc.) - hand over the file's real content instead of
                # nothing, so the solver has actual code to diff against.
                snippet = CodeParser.read_whole_file(file_path, file_rel)
                if snippet:
                    snippet.relevance_score = 0.6
                    snippets.append(snippet)
        
        logger.info(f"Extracted {len(snippets)} code snippets")
        return snippets

    def _generate_context_summary(
        self,
        title: str,
        description: str,
        stack_traces: List[StackTrace],
        code_snippets: List[CodeSnippet]
    ) -> str:
        """
        Generate a summary of extracted context
        
        Returns:
            Context summary string
        """
        summary_parts = [
            f"Issue: {title}",
            f"Extracted {len(stack_traces)} stack traces",
            f"Extracted {len(code_snippets)} code snippets"
        ]
        
        if stack_traces:
            summary_parts.append("\nStack Traces:")
            for trace in stack_traces[:3]:  # Show first 3 traces
                summary_parts.append(
                    f"  - {trace.file_path}:{trace.line_number} in {trace.function_name}"
                )
        
        return "\n".join(summary_parts)

    @staticmethod
    def _get_directory_size(path: str) -> int:
        """Get total size of directory in bytes"""
        total = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    total += os.path.getsize(filepath)
        except Exception as e:
            logger.debug(f"Failed to calculate directory size: {e}")
        return total

    def save_context(self, context: CodeContext, output_path: str) -> bool:
        """
        Save CodeContext to JSON file
        
        Args:
            context: CodeContext object to save
            output_path: Path to save JSON file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(output_path, 'w') as f:
                json.dump(context.dict(), f, indent=2, default=str)
            
            logger.info(f"✓ Saved context to {output_path}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to save context: {e}")
            return False

    def load_context(self, input_path: str) -> Optional[CodeContext]:
        """
        Load CodeContext from JSON file
        
        Args:
            input_path: Path to JSON file
        
        Returns:
            CodeContext object or None if failed
        """
        try:
            with open(input_path, 'r') as f:
                data = json.load(f)
            
            context = CodeContext(**data)
            logger.info(f"✓ Loaded context from {input_path}")
            return context
        
        except Exception as e:
            logger.error(f"Failed to load context: {e}")
            return None
