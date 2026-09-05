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
    bot.ingest_issues = MagicMock(return_value=1)
    bot.solver = object()
    bot.solve_patches = MagicMock(return_value={issue.id: object()})
    bot.tester = object()
    bot.test_patches = MagicMock(
        return_value={issue.id: SimpleNamespace(status="READY_FOR_PR")}
    )
    bot.submitter = None
    bot.submit_patches = MagicMock()

    stats = bot.run_full_pipeline()

    assert stats["phase_5"] == {"tested": 1, "ready": 1}
    assert stats["phase_6"] == {"submitted": 0, "success": 0, "skipped": True}
    bot.submit_patches.assert_not_called()