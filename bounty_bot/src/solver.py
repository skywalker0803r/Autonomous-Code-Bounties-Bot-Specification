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
import queue
import threading
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
import subprocess
import tempfile
import shutil
import textwrap

from pydantic import BaseModel, Field
import yaml
from git import Repo
from git.exc import GitCommandError

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - handled lazily at runtime
    genai = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PatchDeclinedError(RuntimeError):
    """
    Raised when the LLM explicitly declined to produce a patch - e.g. it
    judged the issue text to be a prompt-injection attempt, bait content
    trying to get an automated agent to fabricate financial/cryptographic
    data, or otherwise not a legitimate, patchable bug - rather than a
    genuine technical failure (bad diff format, truncated response, etc).

    Callers should surface this differently from a real failure: it means
    the safety behavior worked as intended, not that something is broken.
    """


# Phrases that show up when the LLM is explaining *why* it refused to
# generate a patch, as opposed to explaining a bug fix. Heuristic, not
# exhaustive - false negatives just fall back to being reported as an
# ordinary "No unified diff found" failure, which is the prior behavior.
_DECLINE_MARKERS = [
    "i'm not going to",
    "i am not going to",
    "i won't",
    "i will not",
    "i don't think i should",
    "i do not think i should",
    "i want to flag",
    "flagging this",
    "i'm flagging",
    "not going to fabricate",
    "not going to generate",
    "not a legitimate",
    "isn't a legitimate",
    "is not a legitimate",
    "prompt injection",
    "prompt-injection",
    "social-engineering",
    "social engineering",
    "bait content",
    "not something i should",
    "not something to act on",
    "i'd treat this issue",
]


def _looks_like_decline(response: str) -> bool:
    text = response.lower()
    return any(marker in text for marker in _DECLINE_MARKERS)


def _extract_decline_reason(response: str, max_chars: int = 500) -> str:
    """First paragraph of the response, as a short human-readable reason."""
    paragraph = response.strip().split("\n\n", 1)[0].strip()
    if len(paragraph) > max_chars:
        paragraph = paragraph[:max_chars].rstrip() + "…"
    return paragraph


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
    repository_file_list: List[str] = Field(default_factory=list)
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
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout_seconds: int = 600
    base_url: Optional[str] = None


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
        self.last_apply_error = ""
        
        # Load settings from YAML
        self.settings = self._load_settings()
        llm_settings = self.settings.get("llm", {})

        # Choose the provider in a robust order:
        # 1) explicit constructor override
        # 2) YAML config (what the web UI's Settings page actually writes)
        # 3) environment keys that are actually present, as a last-resort
        #    guess when nothing above says anything
        # 4) sensible default
        # Env-var presence used to be checked BEFORE the YAML config, which
        # meant picking "gemini" in the Settings page silently did nothing
        # as long as OPENAI_API_KEY also happened to still be set in .env.
        configured_provider = self.config.provider or llm_settings.get("provider")
        if not configured_provider:
            if os.getenv("OPENAI_API_KEY"):
                configured_provider = "openai"
            elif os.getenv("GEMINI_API_KEY"):
                configured_provider = "gemini"
            else:
                configured_provider = "gemini"
        self.provider = configured_provider.lower()
        if self.provider not in {"gemini", "openai", "claude_code"}:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        # Only trust settings.yaml's `model` when it was written for the
        # provider we actually resolved to - otherwise a stale model from a
        # previously-selected provider (e.g. "gpt-4.1-mini" left over after
        # switching provider to claude_code) gets silently reused and sent
        # to the wrong backend.
        yaml_provider = (llm_settings.get("provider") or "").strip().lower()
        yaml_model = llm_settings.get("model") if yaml_provider == self.provider else None
        self.config.model = self.config.model or yaml_model
        if not self.config.model:
            self.config.model = {
                "gemini": "gemini-3.6-flash",
                "openai": "gpt-4.1-mini",
                "claude_code": "sonnet",
            }[self.provider]

        if self.provider == "claude_code":
            # Uses the locally-installed Claude Code CLI (the user's own
            # login/subscription) instead of a provider API key.
            claude_executable = shutil.which("claude")
            if not claude_executable:
                raise ValueError(
                    "llm.provider is claude_code but the 'claude' CLI was not found on PATH. "
                    "Install Claude Code and run 'claude /login' first."
                )
            self._claude_executable = claude_executable
            self.model = None
        elif self.provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY", llm_settings.get("api_key"))
            if not api_key or api_key.startswith("${"):
                self.model = None
                if genai is None:
                    logger.warning(
                        "Gemini provider selected, but google-generativeai is unavailable or incompatible. "
                        "Install a Python 3.12/3.13-compatible version or use OPENAI provider for tests."
                    )
                else:
                    raise ValueError("GEMINI_API_KEY not set in environment or settings.yaml")
            else:
                if genai is None:
                    self.model = None
                    logger.warning(
                        "Gemini provider selected, but google-generativeai could not be imported. "
                        "Install 'google-generativeai>=0.8.0' and a compatible 'protobuf>=5.29.0'."
                    )
                else:
                    genai.configure(api_key=api_key)
                    self.model = genai.GenerativeModel(self.config.model)
        else:
            api_key = os.getenv("OPENAI_API_KEY") if self.provider == "openai" else os.getenv("LOCAL_LLM_API_KEY", "ollama")
            if self.provider == "openai" and not api_key:
                raise ValueError("OPENAI_API_KEY is required when llm.provider is openai")
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ValueError("The openai package is required for llm.provider=openai") from exc
            base_url = self.config.base_url or llm_settings.get("local_base_url") if self.provider == "local" else None
            self.model = OpenAI(api_key=api_key, base_url=base_url, timeout=self.config.timeout_seconds)

        logger.info(
            f"LLMSolver initialized (ID: {self.solver_id}, "
            f"provider: {self.provider}, model: {self.config.model})"
        )
    
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
        repository_path: str,
        on_log: Optional[Callable[[str], None]] = None
    ) -> PatchResult:
        """
        Main entry point: Generate patch for Issue

        Args:
            issue_id: Unique Issue identifier
            issue_title: Issue title
            issue_description: Full Issue description
            code_context: CodeContext from Ingestor
            repository_path: Path to cloned repository
            on_log: Optional callback invoked with progress messages while
                generating (currently only the claude_code provider reports
                interim progress; other providers just ignore it)

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
            
            # Call the configured LLM provider
            llm_response = self._call_llm_api(system_prompt, user_prompt, on_log=on_log)

            # Parse response
            try:
                diff_text = self._extract_diff_from_response(llm_response)
            except ValueError:
                # The extraction failure message alone doesn't say what the
                # model actually returned, which makes it impossible to tell
                # whether it declined, ran out of context, or used a
                # different format - so log the raw response (full text to
                # the backend log, a truncated preview to on_log/the UI).
                logger.error(
                    "No unified diff found in LLM response for issue %s; "
                    "raw response follows:\n%s",
                    issue_id, llm_response,
                )
                if on_log:
                    preview = llm_response if len(llm_response) <= 4000 else (
                        llm_response[:4000] + "…（已截斷,完整內容見後端日誌）"
                    )
                    try:
                        on_log(f"[除錯] 找不到合法的 diff,原始回應內容：\n{preview}")
                    except Exception:
                        logger.debug("on_log callback raised", exc_info=True)
                if _looks_like_decline(llm_response):
                    raise PatchDeclinedError(_extract_decline_reason(llm_response)) from None
                raise
            changes_summary = self._extract_summary_from_response(llm_response)

            # LLMs sometimes drop directory prefixes (e.g. ".github/") from
            # diff headers; fix those against the real repo layout so the
            # diff is still applicable.
            diff_text = self._resolve_diff_paths(diff_text, repository_path)

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
        return """You are a senior open-source software engineer specializing in rapid bug fixes and small features.

Your task: Analyze the provided Issue description and code context, then generate a unified diff format patch.

Requirements:
1. Carefully analyze stack traces and related code snippets
2. Generate a minimal, targeted patch that directly addresses the root cause or request
3. Output MUST be in unified diff format (starting with --- and +++ lines), with paths relative to the
   repository root (e.g. "--- a/path/to/file", "+++ b/path/to/file") - do not invent or guess a path that
   isn't shown in the provided context unless you are creating a new file
4. Avoid unnecessary formatting changes or refactoring
5. Ensure the fix addresses the fundamental issue, not just symptoms
6. Include a brief explanation of the fix before the diff
7. If the task requires a file that does not yet exist (e.g. "Related Files" is empty and the request is to
   add something new), create it using the standard unified-diff "new file" form:
       diff --git a/path/to/new_file b/path/to/new_file
       new file mode 100644
       --- /dev/null
       +++ b/path/to/new_file
       @@ -0,0 +1,N @@
       +...file contents...
   Choose the path and naming style by following the conventions visible in the "Repository Files" listing
   (e.g. where similar files live and how they're named) rather than guessing a generic location.

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
{', '.join(code_context.related_files) if code_context.related_files else 'N/A (no existing file looks directly related - this may require creating a new file; see Repository Files below for naming/location conventions)'}

Repository Files (sample, for structure/convention reference):
{', '.join(code_context.repository_file_list) if code_context.repository_file_list else 'N/A'}

Context Summary:
{code_context.summary}

Task: Generate a unified diff format patch to fix this issue.
The patch should be directly applicable to the repository's {code_context.repository_branch} branch.
Focus on the minimal changes needed to resolve the issue.
Even when Related Files is N/A, you must return an applicable unified diff if the
issue can be resolved by adding or updating a repository file. Do not return only
an explanation or a Markdown document outside the diff."""
        
        return prompt
    
    def _call_llm_api(self, system_prompt: str, user_prompt: str, on_log: Optional[Callable[[str], None]] = None) -> str:
        """Call the configured LLM provider and return its text response."""
        if self.provider == "gemini":
            return self._call_gemini_api(system_prompt, user_prompt)
        if self.provider == "claude_code":
            return self._call_claude_code_api(system_prompt, user_prompt, on_log=on_log)
        return self._call_openai_api(system_prompt, user_prompt)

    def _call_claude_code_api(
        self, system_prompt: str, user_prompt: str, on_log: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Generate a patch via the local Claude Code CLI instead of a hosted
        provider API - uses whatever account the CLI is logged into
        (subscription or API key), so no llm.api_key is required.

        Runs with no tool access and a neutral cwd (never the untrusted
        cloned bounty repo) so this is a plain, isolated text completion:
        it can't read/write repo files itself, and won't auto-load a
        CLAUDE.md or hooks from a third-party repo. The actual patch is
        still applied afterwards through the existing git apply/patch flow.

        Streams (--output-format stream-json) rather than waiting for a
        single blocking response, so callers can surface progress via
        on_log while a generation is still in flight.
        """
        def emit(message: str) -> None:
            if on_log:
                try:
                    on_log(message)
                except Exception:
                    logger.debug("on_log callback raised", exc_info=True)

        # A plain mkdtemp (not TemporaryDirectory's context manager) because
        # on Windows the directory can still be briefly held open right
        # after the child process exits, making immediate cleanup flaky
        # (WinError 32). It's just an empty throwaway dir either way.
        neutral_cwd = tempfile.mkdtemp(prefix="bounty_bot_claude_")
        proc: Optional[subprocess.Popen] = None
        try:
            logger.info(f"Calling Claude Code CLI (model: {self.config.model})...")
            emit("正在啟動 Claude Code CLI...")

            proc = subprocess.Popen(
                [
                    self._claude_executable,
                    "--print",
                    "--output-format", "stream-json",
                    "--include-partial-messages",
                    "--verbose",
                    "--model", self.config.model,
                    "--allowedTools", "",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=neutral_cwd,
                text=True,
                encoding="utf-8",
            )

            prompt_text = f"{system_prompt}\n\n{user_prompt}"

            def _feed_stdin() -> None:
                # Writing from a separate thread (mirroring what
                # subprocess.run's own communicate() does internally) avoids
                # a classic deadlock: a large prompt can exceed the OS pipe
                # buffer, so writing it fully before anything reads stdout
                # would block forever once the child starts producing output.
                try:
                    proc.stdin.write(prompt_text)
                except Exception:
                    logger.debug("Writing to claude CLI stdin failed", exc_info=True)
                finally:
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass

            threading.Thread(target=_feed_stdin, daemon=True).start()

            line_queue: "queue.Queue[Optional[str]]" = queue.Queue()

            def _pump_stdout() -> None:
                try:
                    for line in proc.stdout:
                        line_queue.put(line)
                finally:
                    line_queue.put(None)  # sentinel: stdout closed

            threading.Thread(target=_pump_stdout, daemon=True).start()

            deadline = time.monotonic() + self.config.timeout_seconds
            final_payload: Optional[dict] = None
            chars_seen = 0
            chars_reported = 0

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    proc.kill()
                    raise RuntimeError(f"Claude Code CLI timed out after {self.config.timeout_seconds}s")
                try:
                    line = line_queue.get(timeout=remaining)
                except queue.Empty:
                    proc.kill()
                    raise RuntimeError(f"Claude Code CLI timed out after {self.config.timeout_seconds}s")

                if line is None:
                    break  # stdout closed - the process is finishing up

                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Best-effort progress reporting: these event shapes come
                # from a live capture of this CLI version, but stream-json
                # is an evolving internal format, so every lookup here is
                # defensive - if a shape changes, we just skip that event
                # instead of failing the whole generation.
                etype = evt.get("type")
                if etype == "system" and evt.get("subtype") == "init":
                    emit("Claude Code CLI 已連線")
                elif etype == "system" and evt.get("subtype") == "status" and evt.get("status"):
                    emit(f"Claude Code：{evt['status']}")
                elif etype == "stream_event":
                    delta = ((evt.get("event") or {}).get("delta") or {})
                    text = delta.get("text")
                    if text:
                        chars_seen += len(text)
                        if chars_seen - chars_reported >= 200:
                            emit(f"Claude Code 生成中...（約 {chars_seen} 字元）")
                            chars_reported = chars_seen
                elif etype == "result":
                    final_payload = evt

            try:
                proc.wait(timeout=max(1.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                proc.kill()
                raise RuntimeError(f"Claude Code CLI timed out after {self.config.timeout_seconds}s")

            if final_payload is None:
                stderr_text = (proc.stderr.read() if proc.stderr else "") or ""
                raise RuntimeError(f"claude CLI ended without a result event: {stderr_text.strip()[:500]}")

            if final_payload.get("is_error"):
                raise RuntimeError(f"claude CLI error: {final_payload.get('result') or final_payload}")

            content = final_payload.get("result")
            if content:
                emit("Claude Code 回應完成")
                logger.info("✓ Claude Code CLI response received")
                return content
            raise RuntimeError("Empty response from Claude Code CLI")

        except RuntimeError as e:
            if proc is not None and proc.poll() is None:
                proc.kill()
            logger.error(f"✗ Claude Code CLI call failed: {str(e)}")
            raise
        except Exception as e:
            if proc is not None and proc.poll() is None:
                proc.kill()
            logger.error(f"✗ Claude Code CLI call failed: {str(e)}")
            raise RuntimeError(f"Claude Code CLI error: {str(e)}") from e
        finally:
            shutil.rmtree(neutral_cwd, ignore_errors=True)

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
            if self.model is None or genai is None:
                raise RuntimeError(
                    "Gemini SDK is unavailable or incompatible in this environment. "
                    "Install a compatible version with: pip install 'google-generativeai>=0.8.0' 'protobuf>=5.29.0'"
                )

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

    def _call_openai_api(self, system_prompt: str, user_prompt: str) -> str:
        """Call OpenAI Chat Completions and return the assistant text."""
        try:
            logger.info(f"Calling OpenAI API (model: {self.config.model})...")
            response = self.model.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.config.temperature,
                max_completion_tokens=self.config.max_tokens,
            )
            content = response.choices[0].message.content
            if content:
                logger.info("✓ API response received")
                return content
            raise RuntimeError("Empty response from OpenAI API")
        except Exception as e:
            logger.error(f"✗ OpenAI API call failed: {str(e)}")
            raise RuntimeError(f"OpenAI API error: {str(e)}") from e
    
    def _extract_diff_from_response(self, response: str) -> str:
        """Extract unified diff from LLM response"""
        # Models often indent a fenced diff as part of a Markdown list or quote.
        # Remove that common indentation while preserving diff content spacing.
        lines = textwrap.dedent(response.replace("\r\n", "\n")).split("\n")
        start = next(
            (
                index
                for index, line in enumerate(lines)
                if line.startswith("diff --git ")
                or line.startswith("--- a/")
                or line.startswith("--- /dev/null")
            ),
            None,
        )
        if start is None:
            raise ValueError("No unified diff found in API response")

        diff_lines = []
        diff_prefixes = (
            "diff --git ",
            "index ",
            "new file mode ",
            "deleted file mode ",
            "old mode ",
            "new mode ",
            "similarity index ",
            "rename from ",
            "rename to ",
            "--- ",
            "+++ ",
            "@@",
            "+",
            "-",
            " ",
            "\\ No newline",
        )
        for line in lines[start:]:
            if line.strip().startswith("```"):
                break
            if line.strip() and not line.startswith(diff_prefixes):
                break
            diff_lines.append(line)

        diff = "\n".join(diff_lines).strip()
        if not diff or "--- " not in diff or "+++ " not in diff:
            raise ValueError("No unified diff found in API response")
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

    def _resolve_diff_paths(self, diff: str, repository_path: str) -> str:
        """
        Rewrite diff header paths that don't exist in the repo to the real
        path, when exactly one repo file unambiguously matches.

        LLMs occasionally drop leading directory segments (e.g. write
        "workflows/stale.yml" instead of ".github/workflows/stale.yml"),
        which makes an otherwise-correct diff unapplicable.
        """
        try:
            repo_files = []
            for root, dirs, files in os.walk(repository_path):
                dirs[:] = [d for d in dirs if d != '.git']
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), repository_path)
                    repo_files.append(rel.replace(os.sep, '/'))
        except OSError:
            return diff

        def resolve_path(path: str) -> Optional[str]:
            norm = path.strip().replace('\\', '/').lstrip('/')
            if not norm or norm == 'dev/null':
                return None
            if os.path.exists(os.path.join(repository_path, norm)):
                return None  # already correct, nothing to do
            candidates = [rf for rf in repo_files if rf == norm or rf.endswith('/' + norm)]
            if len(candidates) != 1:
                basename = norm.rsplit('/', 1)[-1]
                candidates = [rf for rf in repo_files if rf.rsplit('/', 1)[-1] == basename]
            return candidates[0] if len(candidates) == 1 else None

        def fix_header_line(match: re.Match) -> str:
            marker, prefix, path, trailing = match.group(1), match.group(2) or '', match.group(3), match.group(4) or ''
            resolved = resolve_path(path)
            if resolved:
                logger.info(f"Resolved diff path '{path}' -> '{resolved}'")
                return f"{marker} {prefix}{resolved}{trailing}"
            return match.group(0)

        pattern = re.compile(r'^(---|\+\+\+)\s+((?:a/|b/)?)(.+?)((?:\t.*)?)$', re.MULTILINE)
        return pattern.sub(fix_header_line, diff)

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
        # (also accept diffs without the a/ b/ prefix, and trailing tab-separated
        # timestamps, since not every LLM follows the git convention exactly)
        file_pattern = r'^---\s+(?:a/)?(.+?)(?:\t.*)?\n\+\+\+\s+(?:b/)?(.+?)(?:\t.*)?$'
        matches = re.findall(file_pattern, diff, re.MULTILINE)

        for old_path, new_path in matches:
            new_path = new_path.strip()
            if new_path in ('/dev/null', ''):
                new_path = old_path.strip()
            if new_path and new_path not in files:
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
        repository_path: str,
        on_log: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Apply patch to local repository (dry-run first)

        Args:
            patch_result: PatchResult from solve_issue
            repository_path: Path to repository
            on_log: Optional callback for surfacing *why* application failed
                (git apply/patch stderr, the diff itself) - the return value
                alone doesn't say enough to debug a bad LLM-generated diff.

        Returns:
            True if patch applied successfully
        """
        def emit(message: str) -> None:
            if on_log:
                try:
                    on_log(message)
                except Exception:
                    logger.debug("on_log callback raised", exc_info=True)

        try:
            logger.info(f"Applying patch to {repository_path}...")

            # Write patch to temp file. Explicit UTF-8 (not the platform
            # default - cp950/cp1252/etc on Windows) since generated diffs
            # can contain arbitrary Unicode (emoji, non-ASCII identifiers).
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.patch', delete=False, newline='\n', encoding='utf-8'
            ) as f:
                f.write(patch_result.diff)
                if not patch_result.diff.endswith('\n'):
                    f.write('\n')
                patch_file = f.name

            try:
                # Prefer `git apply --recount`: LLM-generated diffs frequently have
                # correct content but slightly-off hunk line counts, which `patch`
                # rejects outright as "malformed" but `git apply --recount`
                # tolerates by recalculating the counts itself.
                git_dry_run = subprocess.run(
                    ['git', 'apply', '--check', '--recount', '--whitespace=fix', '-p1', patch_file],
                    cwd=repository_path,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=30
                )

                if git_dry_run.returncode == 0:
                    result = subprocess.run(
                        ['git', 'apply', '--recount', '--whitespace=fix', '-p1', patch_file],
                        cwd=repository_path,
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        timeout=30
                    )
                    if result.returncode == 0:
                        logger.info("✓ Patch applied successfully (git apply)")
                        return True
                    logger.error(f"git apply failed after successful dry-run: {result.stderr}")
                else:
                    logger.warning(f"git apply --check failed, falling back to patch: {git_dry_run.stderr}")

                # Fallback: classic `patch` utility. Not guaranteed to be on
                # PATH even when installed (e.g. Git for Windows ships its
                # own copy under usr/bin without adding it to PATH), so
                # resolve it explicitly instead of trusting the bare name.
                patch_executable = self._resolve_patch_executable()
                if not patch_executable:
                    logger.error(
                        "git apply failed and no 'patch' executable could be found "
                        "(checked PATH and Git's bundled usr/bin) - cannot fall back"
                    )
                    emit("[除錯] 找不到 patch 執行檔，且 git apply 失敗：" + git_dry_run.stderr[:1000])
                    return False

                result = subprocess.run(
                    [patch_executable, '--dry-run', '-p1', '--fuzz=3', '-i', patch_file],
                    cwd=repository_path,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=30
                )

                if result.returncode != 0:
                    logger.error(f"Patch dry-run failed: {result.stderr}")
                    emit(
                        "[除錯] 套用修補程式失敗，git apply 與 patch 都被拒絕：\n"
                        f"git apply --check: {git_dry_run.stderr[:800]}\n"
                        f"patch --dry-run: {result.stderr[:800]}\n"
                        f"產生的 diff（前 3000 字）：\n{patch_result.diff[:3000]}"
                    )
                    return False

                logger.info("✓ Patch dry-run successful")

                # Actually apply
                result = subprocess.run(
                    [patch_executable, '-p1', '--fuzz=3', '-i', patch_file],
                    cwd=repository_path,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=30
                )

                if result.returncode == 0:
                    logger.info("✓ Patch applied successfully (patch)")
                    return True
                else:
                    logger.error(f"Patch application failed: {result.stderr}")
                    emit(f"[除錯] patch 執行失敗（dry-run 通過但實際套用失敗）：{result.stderr[:1000]}")
                    return False

            finally:
                # Cleanup temp file
                os.unlink(patch_file)

        except Exception as e:
            self.last_apply_error = str(e)
            logger.error(f"✗ Error applying patch: {e}")
            return False

    @staticmethod
    def _resolve_patch_executable() -> Optional[str]:
        """
        Find the `patch` utility, including on Windows where it may be
        installed (bundled with Git) without being on PATH.
        """
        found = shutil.which("patch")
        if found:
            return found

        git_executable = shutil.which("git")
        if not git_executable:
            return None

        # Git for Windows ships patch.exe under usr/bin, a few directories
        # up from wherever git.exe itself lives (cmd/, bin/, or
        # mingw64/bin/ depending on install) - walk up looking for it.
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
