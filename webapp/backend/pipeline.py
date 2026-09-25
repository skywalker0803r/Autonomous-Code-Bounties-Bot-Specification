"""Runs one bounty through Ingest -> Solve -> Test -> Submit in a background thread.

This is the web equivalent of BountyBot.run_full_pipeline() in
bounty_bot/main.py, scoped to a single issue and reporting progress into a
RunStore instead of just logging.
"""

from __future__ import annotations

import logging

from .store import RunStore, get_settings_snapshot

logger = logging.getLogger(__name__)


def run_pipeline(run_id: str, bounty: dict, run_store: RunStore) -> None:
    def log(message: str) -> None:
        run_store.append_log(run_id, message)

    def fail(stage_key: str, message: str) -> None:
        run_store.update_stage(run_id, stage_key, "failed")
        run_store.set_status(run_id, "failed")
        run_store.set_error(run_id, message)
        log(f"[錯誤] {message}")

    try:
        _run(run_id, bounty, run_store, log, fail)
    except Exception as exc:  # noqa: BLE001 - last-resort guard so the thread never crashes silently
        logger.exception("Unexpected pipeline failure for run %s", run_id)
        fail("generating_patch", f"未預期的錯誤：{exc}")


def _run(run_id, bounty, run_store, log, fail) -> None:
    from bounty_bot.src.ingestor import CodeIngestor
    from bounty_bot.src.solver import LLMSolver, SolverConfig
    from bounty_bot.src.tester import DockerTester, TesterConfig
    from bounty_bot.src.submitter import AutoSubmitter, SubmitterConfig

    settings = get_settings_snapshot()

    run_store.update_stage(run_id, "issue_found", "done")
    log(f"[發現 Issue] {bounty['title']}")

    # --- repo_loaded + analyzing (CodeIngestor does both in one call) ---
    run_store.update_stage(run_id, "repo_loaded", "running")
    try:
        ingestor = CodeIngestor()
        context = ingestor.ingest_issue(
            issue_id=bounty["id"],
            repository_url=bounty["repository_url"],
            repository=bounty["repository"],
            language=bounty["language"],
            issue_title=bounty["title"],
            issue_description=bounty.get("description", ""),
            branch="main",
        )
    except Exception as exc:
        fail("repo_loaded", f"無法載入倉庫：{exc}")
        return

    if not context or not context.repository_path:
        fail("repo_loaded", "無法載入倉庫，或找不到與 Issue 相關的程式碼")
        return

    run_store.update_stage(run_id, "repo_loaded", "done")
    run_store.update_stage(run_id, "analyzing", "done")
    log(f"已載入 {bounty['repository']}，找到 {len(context.related_files)} 個相關檔案")

    # --- generating_patch ---
    run_store.update_stage(run_id, "generating_patch", "running")
    try:
        solver = LLMSolver(SolverConfig())
    except Exception as exc:
        fail("generating_patch", f"無法初始化 AI 供應商，請確認 API 金鑰是否已設定：{exc}")
        return

    try:
        patch_result = solver.solve_issue(
            bounty["id"], bounty["title"], bounty.get("description", ""), context, context.repository_path,
            on_log=log,
        )
        applied = solver.apply_patch_to_repo(patch_result, context.repository_path, on_log=log)
    except Exception as exc:
        fail("generating_patch", f"生成修補程式失敗：{exc}")
        return

    if not applied:
        detail = getattr(solver, "last_apply_error", "").strip()
        message = "修補程式無法套用到倉庫"
        if detail:
            message = f"{message}：{detail}"
        fail("generating_patch", message)
        return

    run_store.update_stage(run_id, "generating_patch", "done")
    log(f"修補程式已生成（信心分數 {patch_result.confidence_score:.2f}）")

    # --- testing ---
    run_store.update_stage(run_id, "testing", "running")
    try:
        tester = DockerTester(
            TesterConfig(
                memory_limit=settings["advanced"]["docker_memory_limit"],
                cpu_limit=settings["advanced"]["docker_cpu_limit"],
                execution_mode=settings.get("testing_mode", "docker"),
            )
        )
        test_result = tester.run_tests(context.repository_path, build=True)
    except Exception as exc:
        fail("testing", f"測試執行失敗：{exc}")
        return

    if test_result.status != "READY_FOR_PR":
        if test_result.tests_run:
            summary = f"{test_result.tests_passed} 個通過，{test_result.tests_failed} 個失敗"
        else:
            summary = test_result.error or "沙盒環境無法執行測試（請確認 Docker 是否已安裝並啟動）"
        fail("testing", f"測試未通過：{summary}")
        return

    run_store.update_stage(run_id, "testing", "done")
    if test_result.tests_run:
        log(f"測試通過（{test_result.tests_passed} 個通過，耗時 {test_result.duration_seconds:.1f} 秒）")
    else:
        log(test_result.error or "此倉庫沒有可執行的自動化測試，已視為通過")

    # --- pr_submitted ---
    if not settings.get("auto_submit_pr", True):
        run_store.update_stage(run_id, "pr_submitted", "skipped")
        run_store.set_status(run_id, "success")
        log("已停用「自動提交 PR」，流程在測試通過後結束")
        return

    run_store.update_stage(run_id, "pr_submitted", "running")
    try:
        submitter = AutoSubmitter(SubmitterConfig())
        submission = submitter.submit_patch(
            issue_id=bounty["id"],
            issue_title=bounty["title"],
            repository_url=bounty["repository_url"],
            repository=bounty["repository"],
            patch_content=patch_result.diff,
            issue_url=bounty["issue_url"],
            bounty_source=bounty.get("source", "github"),
        )
    except Exception as exc:
        fail("pr_submitted", f"提交 PR 失敗，請確認 GitHub 連線設定：{exc}")
        return

    if submission.status != "PR_CREATED":
        fail("pr_submitted", submission.error_message or "PR 提交失敗")
        return

    run_store.update_stage(run_id, "pr_submitted", "done")
    run_store.set_pr_url(run_id, submission.pr_url)
    run_store.set_status(run_id, "success")
    log(f"PR 已建立：{submission.pr_url}")
