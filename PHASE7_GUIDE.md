# Phase 7: Main Orchestrator - Complete Integration Guide

## ✅ 完成功能

### 1. **完整 End-to-End 流程** (`bounty_bot/main.py`)

Phase 7 實現了完整的自動化 Pipeline，連接所有 Phase 2-6：

```
Phase 2: Monitor (發現懸賞) 
  ↓
Phase 3: Ingest (提取上下文) 
  ↓
Phase 4: Solve (生成補丁) 
  ↓
Phase 5: Test (驗證補丁) 
  ↓
Phase 6: Submit (提交 PR) 
  ↓
💰 Bounty Earned!
```

### 2. **BountyBot 主控制器** (`bounty_bot/main.py::BountyBot`)

#### 核心功能
- ✅ **模塊集成**: 整合 Phase 2-6 的所有模塊
- ✅ **靈活階段控制**: 支持部分或完整 Pipeline 執行
- ✅ **完整統計**: 追蹤每個階段的進度和結果
- ✅ **Daemon 模式**: 24/7 持續運行和監控
- ✅ **錯誤恢復**: 優雅的錯誤處理和日誌記錄

#### 主要方法

| 方法 | 說明 |
|------|------|
| `run_full_pipeline()` | 執行完整 Pipeline (Phase 2-7) |
| `run_single_poll()` | Phase 2 - 監控懸賞 Issue |
| `ingest_issues()` | Phase 3 - 提取代碼上下文 |
| `solve_patches()` | Phase 4 - 生成補丁 |
| `test_patches()` | Phase 5 - 驗證補丁 |
| `submit_patches()` | Phase 6 - 提交 PR |
| `run_daemon()` | Daemon 模式 - 持續運行 |

### 3. **運行模式**

#### 單次運行 (Single Run)

```bash
# Phase 2 only
python bounty_bot/main.py

# Phase 2-3
python bounty_bot/main.py --phases 2-3

# Phase 2-7 (完整 Pipeline)
python bounty_bot/main.py --phases 2-7
```

#### Daemon 模式 (Continuous)

```bash
# 運行完整 Pipeline，每 5 分鐘輪詢一次
python bounty_bot/main.py --phases 2-7 --daemon --interval 300

# 運行 Phase 2-5，每 10 分鐘執行
python bounty_bot/main.py --phases 2-5 --daemon --interval 600

# 詳細日誌模式
python bounty_bot/main.py --phases 2-7 --daemon --log-level DEBUG
```

## 🚀 完整使用示例

### 場景 1: 完整自動化懸賞獵人

```bash
# 終端 1: 啟動 Daemon
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
export GITHUB_USERNAME=your_username
export GEMINI_API_KEY=your_api_key
export GIT_USER_EMAIL=bot@example.com

python bounty_bot/main.py --phases 2-7 --daemon --interval 300 --log-level INFO
```

**工作流程**:
1. 每 5 分鐘監控 Algora/GitHub 尋找懸賞
2. 找到新 Issue → 自動提取代碼上下文
3. 調用 Gemini 生成修復補丁
4. 在 Docker 沙盒驗證補丁
5. 如果通過 → 自動創建 PR
6. 循環重複

### 場景 2: 分階段開發和測試

```bash
# Phase 2-3: Monitor + Ingest (快速測試)
python bounty_bot/main.py --phases 2-3

# Phase 4: 只測試補丁生成
python bounty_bot/main.py --phases 4 < generated_issues.json

# Phase 5-6: 測試和提交驗證
python bounty_bot/main.py --phases 5-6
```

### 場景 3: 手動控制流程

```bash
# 手動逐步運行
python bounty_bot/main.py --phases 2-3  # 監控並提取上下文
python bounty_bot/main.py --phases 4-4  # 生成補丁
python bounty_bot/main.py --phases 5-5  # 測試
python bounty_bot/main.py --phases 6-6  # 提交 PR
```

## 📊 輸出和結果

### Pipeline 執行流程

每次 Pipeline 執行都會輸出：

```
======================================================================
🚀 STARTING FULL PIPELINE (Phase 2-7)
======================================================================

📡 Phase 2: Monitoring for bounty issues...
Found 3 new issues

🔍 Phase 3: Extracting code context...
Ingested 3/3 issues

🧠 Phase 4: Generating patches...
Generated 2/3 patches

🧪 Phase 5: Testing patches...
Tested 2/3 patches, 2 ready for PR

📤 Phase 6: Submitting pull requests...
Submitted 2/3 PRs, 2 successful

======================================================================
✨ PIPELINE COMPLETE
======================================================================
Phase 2 (Monitor): 3 issues found
Phase 3 (Ingest):  3 issues ingested
Phase 4 (Solve):   2 patches generated
Phase 5 (Test):    2 patches tested, 2 ready
Phase 6 (Submit):  2 PRs submitted, 2 successful
Total Time: 127.3 seconds
======================================================================
```

### 結果統計

結果會以 JSON 格式保存在：
- `/tmp/bounty_cache/contexts/{issue_id}_context.json` - 代碼上下文
- `/tmp/bounty_cache/patches/{issue_id}_patch.json` - 補丁結果
- `/tmp/bounty_cache/submissions/{issue_id}.json` - PR 提交結果

## 🔧 環境配置

### 必需的環境變量

```bash
# .env 文件
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx      # GitHub Personal Access Token
GITHUB_USERNAME=your_username               # GitHub 用戶名
GEMINI_API_KEY=AIzaSy...                   # Google Gemini API Key
GIT_USER_EMAIL=bot@autonomousbounties.dev  # Git Commit 郵箱

# 可選
LOG_LEVEL=INFO                              # 日誌級別 (DEBUG/INFO/WARNING/ERROR)
```

### 配置文件

`bounty_bot/config/settings.yaml`:
```yaml
monitor:
  algora_url: "https://api.algora.io"
  github_url: "https://api.github.com"
  poll_languages: ["python", "javascript", "typescript"]
  min_bounty_amount: 50
  exclude_labels: ["closed", "duplicate"]

solver:
  model: "gemini-3.1-pro-preview"
  temperature: 0.7
  max_tokens: 4096
  timeout_seconds: 60

tester:
  memory_limit: "4g"
  cpu_limit: 2.0
  timeout_seconds: 300

submitter:
  repo_clone_dir: "/tmp/bounty_repos"
  branch_prefix: "fix/bounty"
  timeout_seconds: 300
```

## 📈 監控和日誌

### 啟用詳細日誌

```bash
python bounty_bot/main.py --phases 2-7 --log-level DEBUG
```

### 日誌示例

```
2026-09-02 12:34:56,789 - bounty_bot.src.monitor - INFO - ✓ Polling Algora API...
2026-09-02 12:34:57,123 - bounty_bot.src.monitor - INFO - Found 2 new issues
2026-09-02 12:34:58,456 - bounty_bot.src.ingestor - INFO - 📥 Ingesting: Fix critical bug
2026-09-02 12:35:12,789 - bounty_bot.src.solver - INFO - 🧠 Solving: Fix critical bug
2026-09-02 12:35:45,234 - bounty_bot.src.tester - INFO - 🧪 Testing: Fix critical bug
2026-09-02 12:36:18,567 - bounty_bot.src.submitter - INFO - 📤 Submitting: Fix critical bug
2026-09-02 12:36:22,890 - bounty_bot.src.submitter - INFO - ✓ PR created: https://github.com/org/repo/pull/123
```

## 🎯 階段依賴關係

```
Phase 2 必須完成 → Phase 3 可開始
  Phase 3 必須完成 → Phase 4 可開始
    Phase 4 必須完成 → Phase 5 可開始
      Phase 5 必須完成 → Phase 6 可開始
```

如果某個階段失敗，會自動跳過後續階段。

## 🔄 狀態轉移

### Issue 生命週期

```
Issue 發現 (Phase 2)
  ↓ 成功 ✓
Issue 上下文提取 (Phase 3)
  ↓ 成功 ✓
補丁生成 (Phase 4)
  ├─ 失敗 ✗ → 跳過測試和提交
  ↓ 成功 ✓
補丁驗證 (Phase 5)
  ├─ 失敗 ✗ → 跳過提交（需要返工 Phase 4）
  ↓ 通過 ✓ (READY_FOR_PR)
PR 提交 (Phase 6)
  ├─ 成功 → 💰 Bounty 準備就緒
  └─ 失敗 → ⚠️ 需要手動介入
```

## 🚨 錯誤恢復

Phase 7 實現了優雅的錯誤恢復：

1. **部分失敗**: 某個 Issue 失敗不影響其他 Issue
2. **階段跳過**: 如果某階段失敗，自動跳過後續階段
3. **統計報告**: 最後生成完整的執行統計
4. **日誌記錄**: 所有失敗都會詳細記錄以便調試

```python
result = {
    'phase_2': {'found': 5},
    'phase_3': {'ingested': 4},
    'phase_4': {'patched': 3},
    'phase_5': {'tested': 3, 'ready': 2},
    'phase_6': {'submitted': 2, 'success': 1},
    'error': 'GitHub API rate limit exceeded'  # 如果有錯誤
}
```

## 📊 效能優化

### 並行化機會

當前實現順序執行以保證穩定性。未來可以優化：

```
Phase 2 → [Phase 3-a, Phase 3-b, Phase 3-c]  # 並行提取
        ↓
Phase 4 → [Phase 4-a, Phase 4-b, Phase 4-c]  # 並行生成
        ↓
Phase 5 → [Phase 5-a, Phase 5-b, Phase 5-c]  # 並行測試
        ↓
Phase 6 → [Phase 6-a, Phase 6-b, Phase 6-c]  # 並行提交
```

### 快取和重用

- Issue 上下文快取（Phase 3 結果重用）
- 補丁快取（防止重複生成）
- Docker 映像快取（加快測試速度）

## 🔐 安全考慮

1. **Token 管理**: 使用環境變量，不在代碼中存儲
2. **沙盒隔離**: Phase 5 使用 Docker 隔離測試環境
3. **網絡隔離**: 禁用測試容器的網絡訪問
4. **資源限制**: 限制內存和 CPU 使用

## 📝 與其他工具的集成

### CI/CD 集成

```bash
# GitHub Actions
- name: Run Bounty Bot
  run: |
    python bounty_bot/main.py --phases 2-7 --log-level DEBUG
```

### 監控和告警

```bash
# Cron job (每小時執行一次)
0 * * * * cd /path/to/bot && python bounty_bot/main.py --phases 2-7 >> bot.log 2>&1
```

## 🎓 學習資源

詳細的 Phase 實現指南：
- [Phase 2 Guide](PHASE2_GUIDE.md) - Issue 監控
- [Phase 3 Guide](PHASE3_GUIDE.md) - 代碼上下文提取
- [Phase 4 Guide](PHASE4_GUIDE.md) - LLM 補丁生成
- [Phase 5 Guide](PHASE5_GUIDE.md) - Docker 測試
- [Phase 6 Guide](PHASE6_GUIDE.md) - PR 自動提交

## 🐛 調試和故障排除

### 啟用 Debug 日誌

```bash
python bounty_bot/main.py --phases 2-7 --log-level DEBUG 2>&1 | tee debug.log
```

### 常見問題

| 問題 | 原因 | 解決方案 |
|------|------|--------|
| 找不到 Issue | API 限制或無懸賞 | 檢查 API 配置和 Token |
| 補丁生成失敗 | Gemini API 錯誤 | 驗證 API Key 和配額 |
| Docker 測試失敗 | 環境不兼容 | 檢查 Dockerfile 和依賴 |
| PR 提交失敗 | GitHub 認證問題 | 驗證 Token 權限 |

## 🎉 成功指標

成功的 Phase 7 執行應該：
- ✅ 找到新的懸賞 Issue
- ✅ 提取代碼上下文
- ✅ 生成有效的補丁
- ✅ 通過測試驗證
- ✅ 自動創建 PR
- ✅ 生成清晰的執行日誌

## 📞 支持

如有問題，請查看：
1. 完整的日誌輸出 (`--log-level DEBUG`)
2. 相應 Phase 的實現指南
3. 項目 Issue 和討論

## 🚀 未來改進

- [ ] 並行 Phase 執行
- [ ] 分佈式部署支持
- [ ] 機器學習模型增強
- [ ] 實時儀表板
- [ ] 自動領取懸賞
- [ ] 多語言支持增強
