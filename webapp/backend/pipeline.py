"""Runs one bounty through Ingest -> Solve -> Test -> Submit in a background thread.

This is the web equivalent of BountyBot.run_full_pipeline() in
bounty_bot/main.py, scoped to a single issue and reporting progress into a
RunStore instead of just logging.
"""

from __future__ import annotations

import logging
import subprocess

from .store import RunStore, get_settings_snapshot

logger = logging.getLogger(__name__)


def _stash_patch(repository_path: str) -> bool:
    """Stash the applied patch (including any new files it added) so the
    repo is back to its pristine pre-patch state. Returns whether anything
    was actually stashed (a clean stash push with nothing to stash returns
    True from git but with "No local changes to save" in stdout)."""
    try:
        result = subprocess.run(
            ["git", "-C", repository_path, "stash", "push", "-u", "-m", "bounty-bot-baseline"],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "No local changes to save" not in (result.stdout or "")


def _restore_patch(repository_path: str) -> None:
    try:
        subprocess.run(
            ["git", "-C", repository_path, "stash", "pop"],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.exception("Failed to restore stashed patch in %s", repository_path)


def run_pipeline(run_id: str, bounty: dict, run_store: RunStore) -> None:
    def log(message: str) -> None:
        run_store.append_log(run_id, message)

    def fail(stage_key: str, message: str) -> None:
        # A failure on a bounty whose poster account already looks
        # suspicious (see IssueMonitor._assess_poster_suspicion) is more
        # likely to be a bait/scam issue than a real technical problem -
        # surface that alongside the actual error instead of leaving the
        # operator to guess why e.g. the sandbox or patch step failed.
        suspicion_level = bounty.get("suspicion_level", "low")
        if suspicion_level in ("medium", "high"):
            reasons = "、".join(bounty.get("suspicion_reasons") or [])
            label = "高度可疑" if suspicion_level == "high" else "可疑"
            message = f"{message}\n\n⚠️ 此懸賞發布者帳號被標記為{label}（{reasons}），失敗原因可能與此有關，建議查證後再重試"
        run_store.update_stage(run_id, stage_key, "failed")
        run_store.set_status(run_id, "failed")
        run_store.set_error(run_id, message)
        log(f"[錯誤] {message}")

    def decline(stage_key: str, message: str) -> None:
        # Distinct from fail(): the LLM actively refused to produce a patch
        # (prompt-injection bait, fabricated-data requests, etc) rather than
        # failing on a real technical error - this is the safety behavior
        # working as intended, so it's reported as its own status instead of
        # a red "failed" the same as a bug would produce.
        run_store.update_stage(run_id, stage_key, "skipped")
        run_store.set_status(run_id, "declined")
        run_store.set_error(run_id, message)
        log(f"[已略過] {message}")

    try:
        _run(run_id, bounty, run_store, log, fail, decline)
    except Exception as exc:  # noqa: BLE001 - last-resort guard so the thread never crashes silently
        logger.exception("Unexpected pipeline failure for run %s", run_id)
        fail("generating_patch", f"未預期的錯誤：{exc}")


def _run(run_id, bounty, run_store, log, fail, decline) -> None:
    from bounty_bot.src.ingestor import CodeIngestor
    from bounty_bot.src.solver import LLMSolver, SolverConfig, PatchDeclinedError
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
    except PatchDeclinedError as exc:
        decline("generating_patch", str(exc))
        return
    except Exception as exc:
        fail("generating_patch", f"生成修補程式失敗：{exc}")
        return

    if not applied:
        # LLM-generated diffs are usually right in substance but occasionally
        # have a malformed hunk header or inconsistent file path that git
        # apply rejects outright - give the model one shot at fixing its own
        # diff before failing the whole run and forcing a full manual retry.
        detail = getattr(solver, "last_apply_error", "").strip()
        log("修補程式套用失敗，請 AI 修正後重試一次...")
        try:
            repaired = solver.repair_patch(
                bounty["id"], bounty["title"], bounty.get("description", ""), context,
                context.repository_path, patch_result.diff, detail or "git apply/patch rejected the diff",
                on_log=log,
            )
        except Exception:
            repaired = None
        if repaired:
            applied = solver.apply_patch_to_repo(repaired, context.repository_path, on_log=log)
            if applied:
                patch_result = repaired
                detail = ""
            else:
                detail = getattr(solver, "last_apply_error", "").strip()

    if not applied:
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
        # Bounty repos often carry test failures that have nothing to do
        # with this patch - a test needing outbound network the sandbox
        # disables, a pre-existing broken test in an unrelated module, etc.
        # Requiring the *entire* suite to go green blocks every legitimate
        # patch in such a repo, even a correct one. So when some tests
        # failed (as opposed to an infrastructure-level failure, where
        # there's nothing meaningful to compare), re-run the suite with the
        # patch backed out and only treat failures the patch didn't already
        # have as blocking - anything that was already broken beforehand is
        # this repo's problem, not this patch's.
        new_failures: list[str] = []
        new_errors = 0
        pre_existing_failures = 0
        baseline_ok = False
        if test_result.status == "TESTS_FAILED" and test_result.tests_run:
            log("偵測到測試失敗，正在與未套用修補程式的基準版本比較，排除既有、與此修補無關的失敗...")
            stashed = False
            try:
                stashed = _stash_patch(context.repository_path)
                if stashed:
                    baseline_result = tester.run_tests(context.repository_path, build=True)
                    if baseline_result.status in ("READY_FOR_PR", "TESTS_FAILED"):
                        baseline_ok = True
                        new_failures = sorted(
                            set(test_result.failed_test_ids) - set(baseline_result.failed_test_ids)
                        )
                        pre_existing_failures = len(test_result.failed_test_ids) - len(new_failures)
                        new_errors = max(0, test_result.tests_errors - baseline_result.tests_errors)
            except Exception:
                logger.exception("Baseline test comparison failed for run %s", run_id)
            finally:
                if stashed:
                    _restore_patch(context.repository_path)

        if baseline_ok and not new_failures and new_errors == 0:
            log(
                f"測試有 {pre_existing_failures} 個既有失敗與此修補程式無關（未套用修補的基準版本一樣會失敗），已略過；"
                "沒有偵測到此修補程式新增的失敗，繼續提交 PR"
            )
        else:
            if test_result.tests_run:
                summary = f"{test_result.tests_passed} 個通過，{test_result.tests_failed} 個失敗"
                if test_result.tests_errors:
                    summary += f"，{test_result.tests_errors} 個錯誤"
                if baseline_ok:
                    summary += f"（其中 {len(new_failures)} 個是此修補程式新增的失敗，{pre_existing_failures} 個為既有失敗）"
            else:
                # test_result.error is only set when Docker itself couldn't
                # run (daemon unreachable, image build failed, etc). If the
                # container ran but produced no passed/failed/skipped/error
                # summary, that's something else - a crash, a timeout, or a
                # command that isn't pytest - so don't misattribute it to
                # Docker.
                summary = test_result.error or "測試容器已執行完成，但沒有偵測到結果摘要，請查看下方測試輸出"
            output_tail = (test_result.stderr or test_result.stdout or "").strip()
            if output_tail:
                log(f"測試輸出：\n{output_tail[-2000:]}")
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
    if submission.duplicate:
        # GitHub rejected the POST because a PR for this head/base already
        # exists (e.g. an earlier run/retry already pushed and opened one) -
        # submitter.py found and reused it instead of failing. Flag that
        # explicitly so this doesn't read as a fresh PR when it's really a
        # duplicate submission being recognized and deduped.
        run_store.set_duplicate_pr(run_id)
        log(f"⚠️ 重複提交：此懸賞先前已建立過 PR，沿用既有 PR：{submission.pr_url}")
    else:
        log(f"PR 已建立：{submission.pr_url}")

    try:
        from .store import sync_prs_gist
        sync_prs_gist(run_store)
    except Exception:
        logger.exception("Failed to sync PR tracker Gist for run %s", run_id)
