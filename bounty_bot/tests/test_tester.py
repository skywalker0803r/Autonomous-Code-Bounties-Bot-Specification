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


def test_run_tests_can_run_locally_without_docker(tmp_path: Path):
    (tmp_path / "test_local.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    tester = DockerTester(TesterConfig(execution_mode="local", timeout_seconds=30))

    result = tester.run_tests(str(tmp_path), build=True)

    assert result.status == "READY_FOR_PR"
    assert result.passed is True
    assert result.image == "local"
    assert result.tests_passed == 1


def test_build_image_uses_repository_dockerfile(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    client = MagicMock()
    tester = DockerTester(TesterConfig(image="test-image"), client=client)

    assert tester.build_image(str(tmp_path)) == "test-image"
    client.images.build.assert_called_once_with(
        path=str(tmp_path),
        tag="test-image",
        rm=True,
        container_limits=tester._container_limits(),
        dockerfile="Dockerfile",
    )


def test_build_image_disables_network_for_repository_dockerfile_when_configured(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    client = MagicMock()
    tester = DockerTester(TesterConfig(image="test-image", build_network_disabled=True), client=client)

    tester.build_image(str(tmp_path))
    assert client.images.build.call_args.kwargs["network_mode"] == "none"


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
        container_limits=tester._container_limits(),
        dockerfile="docker/sandbox.Dockerfile",
    )
    # The trusted fallback Dockerfile must never get network_mode="none" -
    # it needs network to install pytest/git/etc. at build time.
    assert "network_mode" not in client.images.build.call_args.kwargs


def test_strip_unsafe_symlinks_removes_only_escaping_links(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    (repo / "sub" / "real.txt").write_text("hello", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("SECRET", encoding="utf-8")

    good_link = repo / "good_link.txt"
    evil_link = repo / "evil_link.txt"
    try:
        good_link.symlink_to(repo / "sub" / "real.txt")
        evil_link.symlink_to(outside / "secret.txt")
    except (OSError, NotImplementedError):
        import pytest
        pytest.skip("symlinks not supported in this environment")

    DockerTester._strip_unsafe_symlinks(str(repo))

    assert good_link.exists()
    assert not evil_link.is_symlink()