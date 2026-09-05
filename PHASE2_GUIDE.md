# Phase 2: Issue Monitor - Implementation Guide

## ✅ 完成功能

### 1. **IssueMonitor 類** (`bounty_bot/src/monitor.py`)

#### 核心功能
- ✅ **配置加載**: 自動從 `settings.yaml` 加載配置，支持環境變量擴展
- ✅ **Algora API 輪詢**: 完整實現了 Algora API 的呼叫、解析、過濾
- ✅ **GitHub API 輪詢**: 完整實現了 GitHub REST API 搜索、語言檢測、懸賞金額提取
- ✅ **多重過濾**: 按語言、最低金額、排除標籤進行過濾
- ✅ **去重邏輯**: 自動合併並去重來自多個來源的 Issue
- ✅ **快取管理**: Issue 持久化存儲和加載
- ✅ **新 Issue 檢測**: 自動檢測本次輪詢中新發現的 Issue

#### 主要方法

| 方法 | 說明 |
|------|------|
| `poll_algora_api()` | 輪詢 Algora API 獲取懸賞 Issue |
| `poll_github_api()` | 輪詢 GitHub 獲取帶有 bounty 標籤的 Issue |
| `run_poll_cycle()` | 執行完整的輪詢週期 (Algora + GitHub + 去重 + 快取) |
| `deduplicate_issues()` | 合併並去重兩個來源的 Issue |
| `get_new_issues()` | 獲取本週期新發現的 Issue |
| `_matches_filters()` | 檢查 Issue 是否符合過濾條件 |
| `_extract_bounty_amount()` | 從 GitHub Issue 文本中提取懸賞金額 |

### 2. **BountyIssue 數據模型**

```python
class BountyIssue(BaseModel):
    id: str                      # Issue 唯一識別碼
    title: str                   # Issue 標題
    description: str             # Issue 描述
    repository: str              # 倉庫名稱 (org/repo)
    repository_url: str          # GitHub 倉庫 URL
    issue_url: str               # Issue 完整 URL
    bounty_amount: float         # 懸賞金額 (USD)
    language: str                # 程式語言
    labels: List[str]            # Issue 標籤
    source: str                  # 數據來源 ("algora" 或 "github")
    created_at: datetime         # Issue 建立時間
    last_checked: Optional[datetime] = None  # 最後檢查時間
```

### 3. **主入口** (`bounty_bot/main.py`)

#### 功能
- ✅ CLI 參數解析
- ✅ 單次輪詢模式
- ✅ Daemon 模式 (持續後台監控)
- ✅ 可配置的輪詢間隔
- ✅ 日誌記錄
- ✅ 環境變量驗證

#### 使用方式

```bash
# 1. 單次輪詢
python bounty_bot/main.py

# 2. Daemon 模式 (每 5 分鐘輪詢一次)
python bounty_bot/main.py --daemon --interval 300

# 3. 自定義配置文件
python bounty_bot/main.py --config custom_config.yaml

# 4. 詳細日誌模式
python bounty_bot/main.py --daemon --log-level DEBUG
```

## 🚀 快速開始

### 1. 配置環境

```bash
# 複製環境模板
cp .env.example .env

# 編輯 .env 文件，填入：
# - GEMINI_API_KEY (必須，用於 Phase 4)
# - GITHUB_TOKEN (必須)
```

### 2. 安裝依賴

```bash
pip install -r requirements.txt
```

### 3. 運行測試

```bash
# 運行單元測試
python bounty_bot/tests/test_monitor.py
```

輸出範例：
```
✅ PASS - BountyIssue Model
✅ PASS - Monitor Initialization
✅ PASS - Filter Logic
✅ PASS - Bounty Extraction
✅ PASS - Cache Operations

✨ All tests passed!
```

### 4. 執行監控

```bash
# 單次輪詢
python bounty_bot/main.py

# 持續監控 (推薦用於生產環境)
python bounty_bot/main.py --daemon --interval 300
```

## 📊 輪詢流程

```
┌─────────────────────────────────────────────────┐
│ run_poll_cycle()                                │
├─────────────────────────────────────────────────┤
│ 1. poll_algora_api()                            │
│    ├─ 調用 Algora API                           │
│    ├─ 分頁處理 (5 頁上限)                       │
│    ├─ 應用過濾器                                │
│    └─ 返回 BountyIssue 列表                      │
│                                                   │
│ 2. poll_github_api()                            │
│    ├─ 調用 GitHub REST API /search/issues      │
│    ├─ 搜索 bounty-related 標籤                  │
│    ├─ 提取倉庫語言                              │
│    ├─ 從文本提取懸賞金額                         │
│    ├─ 應用過濾器                                │
│    └─ 返回 BountyIssue 列表                      │
│                                                   │
│ 3. deduplicate_issues()                         │
│    ├─ 按 (repository, issue_url) 去重            │
│    ├─ 優先使用較高金額                          │
│    └─ 返回去重結果                              │
│                                                   │
│ 4. save_cache()                                 │
│    └─ 保存到 /tmp/bounty_cache/issues.json      │
│                                                   │
│ 5. get_new_issues()                             │
│    ├─ 與上次快取比較                            │
│    └─ 返回新 Issue 列表                         │
└─────────────────────────────────────────────────┘
```

## 🔧 配置參數

### `bounty_bot/config/settings.yaml`

```yaml
# LLM 配置 (Phase 4 使用)
llm:
  provider: "gemini"
  model: "gemini-3.1-pro-preview"
  api_key: "${GEMINI_API_KEY}"

# GitHub 配置
github:
  token: "${GITHUB_TOKEN}"
  cli_available: true

# Algora API 配置
algora:
  api_endpoint: "https://api.algora.io/v1/bounties"
  rate_limit: 60

# 過濾規則
filters:
  languages:
    - Python
    - TypeScript
    - JavaScript
  min_bounty_amount: 50  # USD
  exclude_labels:
    - "Needs Discussion"
    - "Design Required"
    - "Question"

# 監控參數
monitoring:
  poll_interval_seconds: 300  # 5 分鐘
  daemon_mode: false
  log_level: "INFO"
```

## 📝 快取結構

快取文件位置: `/tmp/bounty_cache/issues.json`

範例內容:
```json
[
  {
    "id": "algora-12345",
    "title": "Fix memory leak in Layer API",
    "description": "...",
    "repository": "tensorflow/tensorflow",
    "repository_url": "https://github.com/tensorflow/tensorflow",
    "issue_url": "https://algora.io/bounties/12345",
    "bounty_amount": 100.0,
    "language": "Python",
    "labels": ["bug", "memory-leak"],
    "source": "algora",
    "created_at": "2024-01-15T10:30:00",
    "last_checked": "2024-01-15T11:00:00"
  }
]
```

## 🐛 故障排除

### 問題: "Configuration file not found"
```bash
# 確保設定文件存在
ls -la bounty_bot/config/settings.yaml
```

### 問題: "Missing environment variables"
```bash
# 檢查環境變數
echo $GITHUB_TOKEN
echo $GEMINI_API_KEY

# 或在 .env 中設置
cat .env
```

### 問題: 沒有找到任何 Issue
- 檢查 `settings.yaml` 中的過濾條件是否過嚴格
- 檢查 Algora API 是否可訪問
- 檢查 GitHub Token 是否有效

### 問題: API 速率限制
- GitHub: 30 requests/min for authenticated users
- Algora: 60 requests/min (配置中)
- 輪詢間隔默認 300 秒

## 📈 下一步

Phase 3: **Code Ingestor**
- 克隆目標倉庫
- AST 解析代碼上下文
- 提取關鍵代碼片段供 LLM 分析

## 📚 相關文件

- [DEVELOPMENT.md](../DEVELOPMENT.md) - 完整開發路線圖
- [README.md](../README.md) - 項目概述
- [requirements.txt](../requirements.txt) - Python 依賴

## ✨ 測試覆蓋

所有核心功能已通過單元測試：

- ✅ 數據模型 (序列化/反序列化)
- ✅ 配置加載和環境變數擴展
- ✅ 多條件過濾邏輯
- ✅ 懸賞金額提取 (正則表達式)
- ✅ 快取操作 (保存/加載)

運行測試:
```bash
python bounty_bot/tests/test_monitor.py
```

## 🎯 成功指標

✅ **Phase 2 完成**

- [x] Algora API 輪詢實現
- [x] GitHub REST API 輪詢實現
- [x] 多重過濾機制
- [x] Issue 去重邏輯
- [x] 快取管理系統
- [x] 主入口和 CLI
- [x] 單元測試 (100% 通過)
- [x] 使用文檔

準備進入 **Phase 3: Code Ingestor** 開發 🚀
