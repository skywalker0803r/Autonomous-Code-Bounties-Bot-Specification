# 🤖 Autonomous Code Bounties Bot
自動化開源懸賞領取系統 | Passive Income Through Automated Bug Bounty Hunting

> **目標**：完全自動化的開源懸賞獵人機器人。監控 Algora/GitHub Issue → 自動修復 → Docker 測試 → 自動提交 PR → 領取懸賞金

## ⚡ 快速開始（5 分鐘）

```bash
# 1. Clone 與安裝
git clone https://github.com/skywalker0803r/Autonomous-Code-Bounties-Bot-Specification.git
cd Autonomous-Code-Bounties-Bot-Specification
pip install -r requirements.txt

# 2. 配置環境
cp .env.example .env
# 編輯 .env，填入：
#   - GEMINI_API_KEY (從 Google AI Studio 獲取)
#   - GITHUB_TOKEN (個人訪問令牌，需要 repo 權限)
#   - GITHUB_USERNAME (你的 GitHub 用戶名)
#   - GIT_USER_EMAIL (Git Commit 郵箱)

# 3. 構建 Docker 沙盒
docker build -f bounty_bot/docker/sandbox.Dockerfile -t bounty-sandbox .

# 4. 執行單元測試
pytest bounty_bot/tests -q

# 5. 安全驗證完整流程（不會 fork、push 或建立 PR）
python bounty_bot/main.py --phases 2-7 --dry-run

# 6. 確認測試 repository 與憑證後，才執行真實提交
python bounty_bot/main.py --phases 2-7
```

`GIT_USER_EMAIL` 是選填項；未設定時會使用 `bot@autonomousbounties.dev`。

## 🎯 使用示例

```bash
# 監控懸賞 (Phase 2 only)
python bounty_bot/main.py

# 監控 + 提取上下文 (Phase 2-3)
python bounty_bot/main.py --phases 2-3

# 完整 Pipeline: 監控 → 提取 → 修復 → 測試 → 提交
python bounty_bot/main.py --phases 2-7

# 安全試跑：執行至測試階段，但不會建立 Fork、Push 或 PR
python bounty_bot/main.py --phases 2-7 --dry-run

# Daemon 模式: 每 5 分鐘自動執行
python bounty_bot/main.py --phases 2-7 --daemon --interval 300

# 詳細日誌
python bounty_bot/main.py --phases 2-7 --log-level DEBUG
```

## 📋 系統架構

```
┌─────────────┐
│   Monitor   │  輪詢 Algora/GitHub，識別 $50+ 的懸賞 Issue
└──────┬──────┘
       │
       ↓
┌─────────────┐
│  Ingestor   │  克隆倉庫，提取代碼上下文 (AST 解析)
└──────┬──────┘
       │
       ↓
┌─────────────┐
│   Solver    │  調用 Gemini API，生成修復補丁 (Diff)
└──────┬──────┘
       │
       ↓
┌─────────────┐
│   Tester    │  在 Docker 沙盒運行測試，驗證修復
└──────┬──────┘
       │
       ↓
┌─────────────┐
│ Submitter   │  自動創建分支、Commit、推送 PR
└──────┬──────┘
       │
       ↓
┌─────────────┐
│  Bounty! 💰 │  PR Merge 後自動發放懸賞金
└─────────────┘
```

## 📂 項目結構

```
bounty_bot/
├── config/
│   └── settings.yaml           # 配置 (LLM、GitHub、過濾規則)
├── src/
│   ├── __init__.py
│   ├── monitor.py              # [Phase 2] 懸賞 Issue 監控
│   ├── ingestor.py             # [Phase 3] 代碼上下文提取
│   ├── solver.py               # [Phase 4] LLM 補丁生成
│   ├── tester.py               # [Phase 5] Docker 沙盒測試
│   └── submitter.py            # [Phase 6] 自動 PR 提交
├── docker/
│   └── sandbox.Dockerfile      # 隔離測試環境
├── main.py                     # [Phase 7] 主入口 & 24/7 排程
└── requirements.txt            # Python 依賴
```

## 🎯 當前狀態

- **Phase 1 ✅** - 項目基礎設施已建立
- **Phase 2 ✅** - Monitor 模組完成實現 (Algora + GitHub API 輪詢)
- **Phase 3 ✅** - Code Ingestor 完成實現 (Stack Trace 提取 + AST 解析)
- **Phase 4 ✅** - LLM Solver 完成實現 (Gemini API 補丁生成)
- **Phase 5 ✅** - Docker Tester 完成（Docker 沙盒執行、資源限制、pytest 結果解析）
- **Phase 6 ✅** - Auto Submitter 完成（自動 Fork、分支、Commit、推送 PR）
- **Phase 7 ✅** - Main Orchestrator 完成（完整 End-to-End 自動化流程）
- **驗證 ✅** - 34 個單元測試通過，支援 `--dry-run` 安全驗收流程

## ✅ 驗證與部署

在設定真實憑證前，先執行下列命令驗證本地程式：

```bash
# 執行所有單元測試
pytest bounty_bot/tests -q

# 檢查 Docker 可用性
docker info

# 執行完整流程，但停止在 PR 提交前
python bounty_bot/main.py --phases 2-7 --dry-run
```

`--dry-run` 會略過 Phase 6，且不會初始化 GitHub Submitter，因此不會建立 fork、分支、commit、push 或 pull request。它仍可能呼叫 Monitor、Gemini 和 Docker；請使用測試 repository 與受控 API 額度進行驗證。

要啟用真實提交，請先確認 `GEMINI_API_KEY`、`GITHUB_TOKEN` 和 `GITHUB_USERNAME` 已設定，並以你擁有或明確授權的測試 repository 跑一次非 daemon 流程。確認產生的 patch 後，才啟用 daemon 模式。

## 📚 開發指南

| Phase | 說明 | 指南 |
|-------|------|------|
| 2 | 懸賞 Issue 監控 | [PHASE2_GUIDE.md](PHASE2_GUIDE.md) |
| 3 | 代碼上下文提取 | [PHASE3_GUIDE.md](PHASE3_GUIDE.md) |
| 4 | LLM 補丁生成 | [PHASE4_GUIDE.md](PHASE4_GUIDE.md) |
| 5 | Docker 沙盒測試 | [PHASE5_GUIDE.md](PHASE5_GUIDE.md) |
| 6 | 自動 PR 提交 | [PHASE6_GUIDE.md](PHASE6_GUIDE.md) |
| 7 | 完整流程整合 | [PHASE7_GUIDE.md](PHASE7_GUIDE.md) |

詳細開發路線圖見 [DEVELOPMENT.md](DEVELOPMENT.md)，架構和設計見 [API_REFERENCES.md](API_REFERENCES.md)

## 🔑 所需 API Keys

| 服務 | 說明 | 獲取方式 |
|------|------|--------|
| **Gemini API** | LLM 補丁生成 | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| **GitHub Token** | 自動 PR 提交 | GitHub → Settings → Developer settings → Personal access tokens |
| **Algora API** | 可選，懸賞列表 | [Algora 官網](https://algora.io) |

## 💡 工作流程示例

1. **Monitor** 發現：`tensorflow/tensorflow` Issue #12345 - "Fix memory leak in Layer API" ($100 懸賞)
2. **Ingestor** 解析：提取相關代碼片段，理解問題上下文
3. **Solver** 修復：Gemini API 生成補丁，應用到本地倉庫
4. **Tester** 驗證：Docker 運行 pytest，100% 通過 ✓
5. **Submitter** 提交：自動創建 PR，標題 "fix: resolve Issue #12345"
6. **收入**：PR Merge 後，Algora 發放 $100 到你的錢包

## ⚙️ 配置選項

見 [bounty_bot/config/settings.yaml](bounty_bot/config/settings.yaml)

關鍵設置：
- `filters.min_bounty_amount` - 最低懸賞金額 (默認 $50)
- `filters.languages` - 目標編程語言
- `docker.memory_limit` - Docker 容器記憶體限制
- `monitoring.poll_interval_seconds` - 檢查間隔 (默認 5 分鐘)

## 📚 API 文檔參考

- [Algora API 文檔](API_REFERENCES.md#algora)
- [GitHub REST API](API_REFERENCES.md#github)
- [Gemini API](API_REFERENCES.md#gemini)

## 🛡️ 安全與限制

- ✅ Docker 沙盒隔離 - 所有代碼在容器中執行
- ✅ 反垃圾機制 - 測試失敗絕不提交 PR
- ✅ 資源限制 - 最多 1 個並行測試，預留 12GB RAM
- ✅ 環境隔離 - API Keys 不提交到 Git (使用 .env)

## 🚀 下一步

1. 使用 `--dry-run` 在測試 repository 執行完整流程。
2. 驗證 Gemini、Docker 與 GitHub API 的憑證和權限。
3. 人工審閱產生的 patch，再執行一次非 daemon 的真實提交。
4. 確認 PR 工作流程穩定後，再啟用 daemon 模式。

## 📞 常見問題

**Q: 我需要自己的 GitHub Fork 嗎？**
A: 是的，Submitter 會推送到你的 Fork，然後向原倉庫發起 PR。

**Q: 如果補丁破壞了代碼怎麼辦？**
A: Docker 測試必須 100% 通過才會提交 PR。反垃圾機制會防止發送壞補丁。

**Q: 運行成本高嗎？**
A: 主要成本是 Gemini API 調用。詳見 DEVELOPMENT.md 的成本估算。

## 📝 許可證

MIT License - 詳見 LICENSE 文件

---

**最後更新**：2026-09-05 | **當前維護者**：Agent Network 🤖
