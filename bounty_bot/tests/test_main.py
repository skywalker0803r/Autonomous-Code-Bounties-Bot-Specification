from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from bounty_bot.main import BountyBot


def test_dry_run_skips_pr_submission_after_successful_tests():
    issue = SimpleNamespace(id="issue-1")
    bot = object.__new__(BountyBot)
    bot.phases = "2-7"
    bot.dry_run = True
    bot.monitor = MagicMock()
    bot.monitor.run_poll_cycle.return_value = [issue]
    bot.ingestor = SimpleNamespace(cache_dir="/tmp/bounty_cache/repos")
    bot.ingest_issues = MagicMock(return_value=1)
    bot.solver = object()
    bot.solve_patches = MagicMock(return_value={issue.id: object()})
    bot.tester = object()
    bot.test_patches = MagicMock(
        return_value={issue.id: SimpleNamespace(status="READY_FOR_PR")}
    )
    bot.repository_paths = {issue.id: "/tmp/repository"}
    bot.submitter = None
    bot.submit_patches = MagicMock()

    stats = bot.run_full_pipeline()

    assert stats["phase_5"] == {"tested": 1, "ready": 1}
    assert stats["phase_6"] == {"submitted": 0, "success": 0, "skipped": True}
    bot.submit_patches.assert_not_called()


def test_solve_patches_passes_context_and_repository_path(tmp_path, monkeypatch):
    issue = SimpleNamespace(id="issue-1", title="Fix bug", description="Bounty $50")
    context_path = tmp_path / "repository"
    context_path.mkdir()
    context = SimpleNamespace(repository_path=str(context_path))
    patch = SimpleNamespace(diff="", confidence_score=1.0, dict=lambda **kwargs: {})
    bot = object.__new__(BountyBot)
    bot.solver = MagicMock()
    bot.solver.solve_issue.return_value = patch
    bot.solver.apply_patch_to_repo.return_value = True
    bot.ingestor = MagicMock()
    bot.ingestor.load_context.return_value = context
    bot.repository_paths = {}
    monkeypatch.setattr("bounty_bot.main.Path.exists", lambda path: True)

    assert bot.solve_patches([issue]) == {issue.id: patch}
    bot.solver.solve_issue.assert_called_once_with(
        issue.id, issue.title, issue.description, context, str(context_path)
    )
    bot.solver.apply_patch_to_repo.assert_called_once_with(patch, str(context_path))
    assert bot.repository_paths == {issue.id: str(context_path)}


def test_cleanup_repositories_removes_only_ingestor_cache_paths(tmp_path):
    repository_path = tmp_path / "repositories" / "issue-1"
    repository_path.mkdir(parents=True)
    external_path = tmp_path / "external"
    external_path.mkdir()
    bot = object.__new__(BountyBot)
    bot.ingestor = SimpleNamespace(cache_dir=str(repository_path.parent))
    bot.repository_paths = {
        "issue-1": str(repository_path),
        "external": str(external_path),
    }

    bot.cleanup_repositories()

    assert not repository_path.exists()
    assert external_path.exists()
    assert bot.repository_paths == {}