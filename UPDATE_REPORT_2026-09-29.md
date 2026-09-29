# 今日更新報告 — 2026-09-29

## 背景

延續昨天（2026-09-28）報告中「Bounty Bot 端到端驗證仍待完成」的狀態，今天實際觀察 Bounty Bot 執行懸賞任務的過程，發現懸賞測試環境有多層問題導致 AI 生成的修補程式明明正確，卻一直被判定失敗、無法送出 PR。逐一定位、修正並用兩個真實懸賞完整驗證到成功送出 PR 為止。

## 完成項目

### 沙箱測試環境修正（5 項，逐一疊代）

1. **`testing.mode` 改回 `docker`**（[settings.yaml](bounty_bot/config/settings.yaml)）：先前設為 `local`，測試直接在本機 Python 執行，沒有安裝目標倉庫自己的相依套件（如 flask、prometheus_client），導致任何有額外依賴的倉庫測試必定失敗。
2. **測試指令改為 `python -m pytest`**（[tester.py](bounty_bot/src/tester.py)）：原本用裸 `pytest` 執行，repo root 不會被加進 `sys.path`，許多倉庫用 `from scripts.x import y` 這種相對根目錄匯入的慣例會直接 `ModuleNotFoundError`。
3. **Dockerfile 偵測邏輯收斂**（[tester.py](bounty_bot/src/tester.py)）：原本只要倉庫自帶 `Dockerfile` 就直接拿來測試，但很多倉庫的 Dockerfile 其實是「正式部署映像」（例如 RustChain 節點服務），根本沒裝 pytest。改成只有偵測到該 Dockerfile 有安裝 pytest 才採用，否則改用專案自己的 `sandbox.Dockerfile`。
4. **pytest 結果摘要解析器修正**（[tester.py](bounty_bot/src/tester.py)）：舊的正則要求摘要行以 `=` 或行尾結尾，只要出現 `15 warnings`、`6 subtests passed`、`(0:01:01)` 這類額外字樣就整行解析失敗，導致明明「793 個通過、26 個失敗」卻回報「0 個通過，0 個失敗」，完全誤判。
5. **新增 baseline 對照策略，不再要求整個測試套件全過**（[pipeline.py](webapp/backend/pipeline.py)）：測試失敗時，自動 `git stash` 把修補程式暫時退掉，在「未套用修補的原始版本」上用同一套沙箱重跑一次測試取得基準失敗清單，只有修補程式**新增**的失敗才會真的擋下 PR；既有、與這次修補無關的失敗（例如需要對外網路的 DNS 測試、或需要環境變數才能啟動的既有檢查）會被記錄但不阻擋提交，比對完會自動還原修補程式。

### 新功能：懸賞頁面標註已提交過 PR

- 後端 [`BountyOut`](webapp/backend/models.py) 新增 `submitted_pr_url` 欄位，[`RunStore.pr_url_for_bounty()`](webapp/backend/store.py) 依 `bounty_id` 查最近一筆有提交 PR 的執行紀錄，[`GET /api/bounties`](webapp/backend/app.py) 附帶回傳。
- 前端 [`BountyCard`](webapp/frontend/src/components/BountyCard.tsx) 若懸賞已有對應 PR，顯示綠色「✓ PR 已提交」徽章，點擊直接連到該 PR。

## 驗證狀態

- **端到端驗證通過**：用兩個先前一直失敗的真實懸賞（Scottcjn/Rustchain 300 RTC、Scottcjn/rustchain-bounties 100 RTC）反覆重跑驗證，最終都成功送出 PR：
  - <https://github.com/Scottcjn/Rustchain/pull/8538>
  - <https://github.com/Scottcjn/rustchain-bounties/pull/17081>
- `bounty_bot/tests` 全部 70 個測試通過（新增 4 個回歸測試：Dockerfile pytest 偵測 x2、摘要解析警告/子測試後綴、`failed_test_ids` 解析）。
- 前端 `npm run build` 建置成功，TypeScript 檢查通過。
- 懸賞頁面 PR 徽章已在瀏覽器中實際驗證顯示正常（目前列表中有 10 個懸賞顯示已提交徽章）。

## 尚待處理

- 過程中另外發現一個獨立、未修的 patch 套用問題：Claude Code 針對「新增檔案」生成的 diff 有時 `git apply` 會判定成「修改既有檔案」而失敗（`depends on old contents`），目前靠既有的「失敗後請 AI 修正重試一次」機制自行復原，未深入根治。
- 所有修改目前都還在工作目錄，尚未 commit / 推送。

## 安全與存檔

- 本機 `.env` 仍由 `.gitignore` 忽略，未納入提交。
- 尚未建立 commit；異動檔案：`bounty_bot/config/settings.yaml`、`bounty_bot/src/tester.py`、`bounty_bot/tests/test_tester.py`、`webapp/backend/{app,models,pipeline,store}.py`、`webapp/frontend/src/{components/BountyCard.tsx,types.ts}`，共 9 個原始碼檔案，258 行新增、32 行刪除（前端 `dist/` 建置產物另計）。
