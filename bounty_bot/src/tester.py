"""Docker sandbox test runner for generated patches."""

import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

try:
    import docker
    from docker.errors import DockerException
    from docker.utils import parse_bytes
except ImportError:  # pragma: no cover
    docker = None
    parse_bytes = None

    class DockerException(Exception):
        """Fallback exception when the Docker SDK is unavailable."""


logger = logging.getLogger(__name__)


class TesterConfig(BaseModel):
    """Resource and execution settings for the Docker sandbox."""

    __test__ = False

    image: str = "bounty-sandbox"
    memory_limit: str = "4g"
    cpu_limit: float = Field(default=2.0, gt=0)
    timeout_seconds: int = Field(default=300, gt=0)
    # Run as `python -m pytest`, not a bare `pytest`, so the repo root (the
    # sandbox's cwd) is added to sys.path - many repos rely on this implicit
    # convention for root-relative imports (e.g. `from scripts.x import y`)
    # without a conftest.py, `pythonpath` setting, or installed package to
    # provide it, and a bare `pytest` invocation leaves those imports broken
    # regardless of patch quality.
    test_command: str = "python -m pytest --tb=short -v"
    execution_mode: str = "docker"
    network_disabled: bool = True
    # Bounty repos are untrusted third-party code, and when one ships its own
    # Dockerfile we build it (see build_image) - its RUN steps execute with
    # network access by default, same as any normal image build. Opt into
    # this to cut that off for repo-provided Dockerfiles specifically (the
    # project's own fallback sandbox.Dockerfile always keeps network, since
    # it needs it to install pytest/git/etc. and is trusted first-party code).
    # Off by default because most real Dockerfiles need network at build time
    # (apt-get/pip/npm) and would simply fail to build with this enabled.
    build_network_disabled: bool = False


class TestResult(BaseModel):
    """Result of one sandbox test execution."""

    status: str
    passed: bool
    exit_code: Optional[int] = None
    command: str
    image: str
    duration_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_errors: int = 0
    # pytest node ids ("path::Class::test_name") pulled from "FAILED "/
    # "ERROR " short-summary lines - lets a caller diff two runs' failures
    # against each other (e.g. patched vs. baseline) instead of only
    # comparing counts.
    failed_test_ids: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    completed_at: datetime = Field(default_factory=datetime.now)


class DockerTester:
    """Build and run repository tests inside an isolated Docker container."""

    # pytest's own exit code for "ran successfully, but no tests matched".
    _NO_TESTS_COLLECTED_EXIT_CODE = 5

    def __init__(self, config: Optional[TesterConfig] = None, client: Any = None):
        self.config = config or TesterConfig()
        self.client = client

    def _get_client(self) -> Any:
        if self.client is None:
            if docker is None:
                raise DockerException("Docker SDK is not installed")
            self.client = docker.from_env()
        return self.client

    def build_image(self, repository_path: str, image_tag: Optional[str] = None) -> str:
        """Build a sandbox image using the repository as Docker build context."""
        path = Path(repository_path)
        if not path.is_dir():
            raise ValueError(f"Repository path does not exist: {repository_path}")

        tag = image_tag or self.config.image
        kwargs: Dict[str, Any] = {
            "path": str(path),
            "tag": tag,
            "rm": True,
            "container_limits": self._container_limits(),
        }
        dockerfile = path / "Dockerfile"
        temp_dockerfile: Optional[Path] = None
        # A repo's own Dockerfile is often a *deployment* image (e.g. one
        # that runs its production service), not a test image - it may
        # install a narrower "runtime" requirements file, drop dev tooling,
        # switch to a non-root user, or set an unrelated ENTRYPOINT/CMD, and
        # frequently never installs pytest at all. Using it as the sandbox
        # then means every run fails on "No module named pytest" regardless
        # of patch quality. Only trust it as the test sandbox when it
        # actually looks like it installs pytest; otherwise use our own
        # fallback image, which is built specifically to run the repo's
        # test suite.
        dockerfile_runs_tests = False
        if dockerfile.exists():
            try:
                dockerfile_runs_tests = "pytest" in dockerfile.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                dockerfile_runs_tests = False

        if dockerfile.exists() and dockerfile_runs_tests:
            kwargs["dockerfile"] = dockerfile.name
            if self.config.build_network_disabled:
                kwargs["network_mode"] = "none"
            # This repo is an untrusted bounty target, not our own code: its
            # Dockerfile's RUN instructions execute on the Docker daemon with
            # whatever the build gets (network, unless build_network_disabled).
            logger.warning(
                "Building Docker image %s from %s's own Dockerfile - this executes "
                "build instructions from an untrusted third-party repository "
                "(network_disabled=%s)",
                tag, path, self.config.build_network_disabled,
            )
        else:
            if dockerfile.exists():
                logger.info(
                    "%s has its own Dockerfile but it doesn't appear to install pytest "
                    "(likely a deployment image, not a test image) - using the project "
                    "sandbox Dockerfile instead",
                    path,
                )
            project_root = Path(__file__).resolve().parents[1]
            fallback_dockerfile = project_root / "docker" / "sandbox.Dockerfile"
            if not fallback_dockerfile.exists():
                raise FileNotFoundError(f"No Dockerfile found in {path} or {fallback_dockerfile}")
            # docker-py's build API requires the Dockerfile to live inside
            # whatever directory it tars up as the build context. Building
            # with `path=project_root` (this project's own source) instead
            # of the target repo meant `COPY . .` copied this project's
            # files and `pip install -r requirements.txt` installed *this
            # bot's* dependencies, not the target repo's - every target with
            # real dependencies beyond pytest failed with
            # ModuleNotFoundError regardless of patch quality. Copy the
            # fallback Dockerfile into the target repo temporarily instead
            # so the context is the repo actually being tested.
            temp_dockerfile = path / ".bounty_bot_sandbox.Dockerfile"
            temp_dockerfile.write_text(fallback_dockerfile.read_text(encoding="utf-8"), encoding="utf-8")
            kwargs["dockerfile"] = temp_dockerfile.name
            logger.info("Building Docker image %s from %s using project sandbox Dockerfile", tag, path)

        try:
            self._get_client().images.build(**kwargs)
        finally:
            if temp_dockerfile is not None:
                temp_dockerfile.unlink(missing_ok=True)
        return tag

    @staticmethod
    def _strip_unsafe_symlinks(repository_path: str) -> None:
        """
        Remove any symlink in the repo that resolves outside of it.

        The repo is bind-mounted read-write into the container (and copied
        into the build context). A hostile bounty repo could commit a
        symlink pointing at an absolute host path; if the test command or
        Dockerfile COPY follows it, the container could read or write
        whatever that path resolves to on the host through the mount. Since
        legitimate repos have no reason to symlink outside their own tree,
        any symlink that does is simply removed before anything touches it.
        """
        root = Path(repository_path).resolve()
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            for name in list(dirnames) + filenames:
                candidate = Path(dirpath) / name
                if not candidate.is_symlink():
                    continue
                try:
                    target = candidate.resolve()
                except OSError:
                    target = None
                if target is None or target == root or root not in target.parents:
                    logger.warning("Removing symlink escaping repo root: %s", candidate)
                    try:
                        candidate.unlink()
                    except OSError as exc:
                        logger.warning("Could not remove unsafe symlink %s: %s", candidate, exc)
            # Don't descend into symlinked directories - os.walk with
            # followlinks=False already skips their contents, but a
            # symlinked dir itself still shows up in dirnames above and gets
            # unlinked there.

    def _container_limits(self) -> Dict[str, Any]:
        """Bound the build step's own resource usage, independent of the network question above."""
        limits: Dict[str, Any] = {}
        if parse_bytes is not None:
            try:
                limits["memory"] = parse_bytes(self.config.memory_limit)
            except Exception:
                pass
        return limits

    def run_tests(
        self,
        repository_path: str,
        test_command: Optional[str] = None,
        image_tag: Optional[str] = None,
        build: bool = False,
    ) -> TestResult:
        """Run tests and return a result; infrastructure errors become failures."""
        command = test_command or self.config.test_command
        image = image_tag or self.config.image
        started_at = datetime.now()

        try:
            self._strip_unsafe_symlinks(repository_path)

            if self.config.execution_mode == "local":
                return self._run_tests_locally(repository_path, command, started_at)

            if build:
                image = self.build_image(repository_path, image)

            container = self._get_client().containers.run(
                image=image,
                command=["sh", "-lc", command],
                volumes={str(Path(repository_path).resolve()): {"bind": "/app", "mode": "rw"}},
                working_dir="/app",
                detach=True,
                mem_limit=self.config.memory_limit,
                nano_cpus=int(self.config.cpu_limit * 1_000_000_000),
                network_disabled=self.config.network_disabled,
                auto_remove=False,
            )
            try:
                wait_result = container.wait(timeout=self.config.timeout_seconds)
                exit_code = self._exit_code(wait_result)
                stdout = self._decode(container.logs(stdout=True, stderr=False))
                stderr = self._decode(container.logs(stdout=False, stderr=True))
            except Exception as exc:
                container.kill()
                return self._failure_result(command, image, started_at, f"Test execution failed: {exc}")
            finally:
                container.remove(force=True)

            counts = self._parse_pytest_summary(stdout + "\n" + stderr)
            # pytest exits 5 when it collected zero tests - e.g. a docs/skill
            # repo with no test suite at all. That's not a test failure, so
            # treat it the same as a pass rather than blocking the pipeline
            # on tests that were never going to exist.
            no_tests_collected = exit_code == self._NO_TESTS_COLLECTED_EXIT_CODE
            passed = exit_code == 0 or no_tests_collected
            return TestResult(
                status="READY_FOR_PR" if passed else "TESTS_FAILED",
                passed=passed,
                exit_code=exit_code,
                command=command,
                image=image,
                duration_seconds=(datetime.now() - started_at).total_seconds(),
                stdout=stdout,
                stderr=stderr,
                error="此倉庫沒有可執行的自動化測試，已視為通過。" if no_tests_collected else None,
                **counts,
            )
        except (DockerException, OSError, ValueError) as exc:
            return self._failure_result(command, image, started_at, str(exc))

    def _run_tests_locally(self, repository_path: str, command: str, started_at: datetime) -> TestResult:
        """Run tests in the current host environment when Docker is disabled."""
        logger.warning("Running bounty tests locally without Docker: %s", repository_path)
        stripped = command.lstrip()
        # Normalize any of "pytest ...", "python -m pytest ...", or
        # "python3 -m pytest ..." to run under *this* interpreter - a bare
        # "python"/"python3" on PATH may not be the venv sys.executable is in.
        for prefix in ("python -m ", "python3 -m ", ""):
            if stripped.startswith(prefix + "pytest"):
                command = f'"{sys.executable}" -m {stripped[len(prefix):]}'
                break
        try:
            completed = subprocess.run(
                command,
                cwd=str(Path(repository_path).resolve()),
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = self._decode(exc.stdout)
            stderr = self._decode(exc.stderr)
            return self._failure_result(command, "local", started_at, f"Test execution timed out: {stderr or stdout}")
        except OSError as exc:
            return self._failure_result(command, "local", started_at, str(exc))

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        counts = self._parse_pytest_summary(stdout + "\n" + stderr)
        no_tests_collected = completed.returncode == self._NO_TESTS_COLLECTED_EXIT_CODE
        passed = completed.returncode == 0 or no_tests_collected
        return TestResult(
            status="READY_FOR_PR" if passed else "TESTS_FAILED",
            passed=passed,
            exit_code=completed.returncode,
            command=command,
            image="local",
            duration_seconds=(datetime.now() - started_at).total_seconds(),
            stdout=stdout,
            stderr=stderr,
            error="此倉庫沒有可執行的自動化測試，已視為通過。" if no_tests_collected else None,
            **counts,
        )

    def _failure_result(self, command: str, image: str, started_at: datetime, error: str) -> TestResult:
        logger.error("Sandbox test failed: %s", error)
        return TestResult(
            status="INFRASTRUCTURE_FAILED",
            passed=False,
            command=command,
            image=image,
            duration_seconds=(datetime.now() - started_at).total_seconds(),
            error=error,
        )

    @staticmethod
    def _exit_code(wait_result: Any) -> int:
        if isinstance(wait_result, dict):
            return int(wait_result.get("StatusCode", 1))
        return int(wait_result)

    @staticmethod
    def _decode(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value or "")

    @staticmethod
    def _parse_failed_test_ids(output: str) -> list[str]:
        """Pull pytest node ids out of its "FAILED "/"ERROR " short-summary lines.

        Format is "FAILED path/to/test.py::Class::test_name" or "FAILED
        path/to/test.py::test_name - <reason>" (and the same for ERROR, used
        for collection failures) - take just the node id, not any trailing
        " - reason" pytest appends when it fits on the line.
        """
        ids = re.findall(r"^(?:FAILED|ERROR)\s+(\S+)", output, re.MULTILINE)
        return sorted(set(ids))

    @staticmethod
    def _parse_pytest_summary(output: str) -> Dict[str, Any]:
        """Parse the common pytest terminal summary without requiring pytest XML."""
        summary: Dict[str, Any] = {"tests_run": 0, "tests_passed": 0, "tests_failed": 0, "tests_skipped": 0, "tests_errors": 0}
        summary["failed_test_ids"] = DockerTester._parse_failed_test_ids(output)
        # pytest never pluralizes passed/failed/skipped ("5 failed"), but does
        # pluralize error/errors ("1 error" vs "3 errors") - a collection
        # error (bad import, syntax error in the patch) reports only this
        # label with no passed/failed/skipped at all. The summary line can
        # also carry extra trailing tokens this parser doesn't care about -
        # "15 warnings", "6 subtests passed" (pytest-subtests), a duration
        # ("in 61.77s (0:01:01)") - so anchoring the match to end-of-line (as
        # this used to) fails to match the instant any of those follow the
        # counts. Take the last (i.e. final) comma-chain of known-label
        # counts anywhere in the output instead, and ignore everything
        # after it.
        candidates = re.findall(
            r"\d+\s+(?:passed|failed|skipped|errors?)(?:,\s*\d+\s+(?:passed|failed|skipped|errors?))*",
            output,
        )
        if not candidates:
            return summary
        text = candidates[-1]
        for number, label in re.findall(r"(\d+)\s+(passed|failed|skipped|errors?)", text):
            key = "tests_errors" if label.startswith("error") else f"tests_{label}"
            summary[key] = int(number)
        summary["tests_run"] = sum(summary[key] for key in ("tests_passed", "tests_failed", "tests_skipped", "tests_errors"))
        return summary