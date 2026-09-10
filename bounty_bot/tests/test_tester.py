from pathlib import Path
from unittest.mock import MagicMock

from bounty_bot.src.tester import DockerTester, TesterConfig


def test_run_tests_returns_ready_for_pr_on_zero_exit(tmp_path: Path):
    container = MagicMock()
    container.wait.return_value = {"StatusCode": 0}
    container.logs.side_effect = [b"5 passed, 1 skipped\n", b""]
    client = MagicMock()
    client.containers.run.return_value = container

    result = DockerTester(client=client).run_tests(str(tmp_path))

    assert result.status == "READY_FOR_PR"
    assert result.passed is True
    assert result.tests_run == 6
    client.containers.run.assert_called_once()
    assert container.remove.called


def test_run_tests_marks_nonzero_exit_as_failed(tmp_path: Path):
    container = MagicMock()
    container.wait.return_value = {"StatusCode": 1}
    container.logs.side_effect = [b"1 failed, 2 passed\n", b"failure output"]
    client = MagicMock()
    client.containers.run.return_value = container

    result = DockerTester(client=client).run_tests(str(tmp_path), test_command="pytest tests/test_app.py")

    assert result.status == "TESTS_FAILED"
    assert result.passed is False
    assert result.exit_code == 1
    assert result.tests_failed == 1
    assert result.tests_passed == 2


def test_build_image_uses_repository_dockerfile(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    client = MagicMock()
    tester = DockerTester(TesterConfig(image="test-image"), client=client)

    assert tester.build_image(str(tmp_path)) == "test-image"
    client.images.build.assert_called_once_with(
        path=str(tmp_path), tag="test-image", rm=True, dockerfile="Dockerfile"
    )


def test_build_image_falls_back_to_project_sandbox_dockerfile(tmp_path: Path):
    repo_path = tmp_path / "issue-repo"
    repo_path.mkdir()
    client = MagicMock()
    tester = DockerTester(TesterConfig(image="test-image"), client=client)

    assert tester.build_image(str(repo_path)) == "test-image"
    project_root = Path(__file__).resolve().parents[1]
    client.images.build.assert_called_once_with(
        path=str(project_root),
        tag="test-image",
        rm=True,
        dockerfile="docker/sandbox.Dockerfile",
    )