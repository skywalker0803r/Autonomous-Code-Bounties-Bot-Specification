"""Docker sandbox test runner for generated patches."""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

try:
    import docker
    from docker.errors import DockerException
except ImportError:  # pragma: no cover
    docker = None

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
    test_command: str = "pytest --tb=short -v"
    network_disabled: bool = True


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
    error: Optional[str] = None
    completed_at: datetime = Field(default_factory=datetime.now)


class DockerTester:
    """Build and run repository tests inside an isolated Docker container."""

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
        kwargs: Dict[str, Any] = {"path": str(path), "tag": tag, "rm": True}
        dockerfile = path / "Dockerfile"
        if dockerfile.exists():
            kwargs["dockerfile"] = dockerfile.name

        logger.info("Building Docker image %s from %s", tag, path)
        self._get_client().images.build(**kwargs)
        return tag

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
            return TestResult(
                status="READY_FOR_PR" if exit_code == 0 else "TESTS_FAILED",
                passed=exit_code == 0,
                exit_code=exit_code,
                command=command,
                image=image,
                duration_seconds=(datetime.now() - started_at).total_seconds(),
                stdout=stdout,
                stderr=stderr,
                **counts,
            )
        except (DockerException, OSError, ValueError) as exc:
            return self._failure_result(command, image, started_at, str(exc))

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
    def _parse_pytest_summary(output: str) -> Dict[str, int]:
        """Parse the common pytest terminal summary without requiring pytest XML."""
        summary = {"tests_run": 0, "tests_passed": 0, "tests_failed": 0, "tests_skipped": 0}
        match = re.search(r"(?:=+\s*)?(\d+\s+(?:passed|failed|skipped)(?:,\s*\d+\s+(?:passed|failed|skipped))*)(?:\s*=+)?\s*$", output, re.MULTILINE)
        if not match:
            return summary
        text = match.group(1)
        for number, label in re.findall(r"(\d+)\s+(passed|failed|skipped)", text):
            summary[f"tests_{label}"] = int(number)
        summary["tests_run"] = sum(summary[f"tests_{key}"] for key in ("passed", "failed", "skipped"))
        return summary