# Phase 3: Code Ingestor - Implementation Guide

## ✅ 完成功能

### 1. **CodeIngestor 類** (`bounty_bot/src/ingestor.py`)

#### 核心功能
- ✅ **Shallow Clone Repository**: 使用 `--depth=1` 快速克隆目標倉庫
- ✅ **Stack Trace Extraction**: 從 Issue 描述中提取堆棧跟蹤 (Python/JavaScript/TypeScript)
- ✅ **AST Code Parsing**: 使用 Python AST 解析代碼結構（函數、類、導入）
- ✅ **Code Context Extraction**: 從相關文件提取代碼片段
- ✅ **Compressed Context Generation**: 生成精簡的代碼上下文供 LLM 使用
- ✅ **Context Serialization**: 保存/加載代碼上下文為 JSON 格式

#### 主要類

| 類 | 說明 |
|------|------|
| `StackTraceExtractor` | 從 Issue 文本提取堆棧跟蹤 |
| `CodeParser` | 使用 AST 解析代碼和提取片段 |
| `CodeIngestor` | 主要協調器，整合上述功能 |

#### 主要方法

| 方法 | 說明 |
|------|------|
| `ingest_issue()` | 主入口：克隆倉庫並提取完整上下文 |
| `_clone_repository()` | Shallow clone Git 倉庫 |
| `_find_related_files()` | 根據堆棧跟蹤找到相關文件 |
| `_extract_code_snippets()` | 從文件提取代碼片段 |
| `_generate_context_summary()` | 生成上下文摘要 |
| `save_context()` | 保存 CodeContext 到 JSON |
| `load_context()` | 從 JSON 加載 CodeContext |

### 2. **數據模型**

#### StackTrace
```python
class StackTrace(BaseModel):
    file_path: str          # 文件路徑
    function_name: str      # 函數名稱
    line_number: int        # 行號 (1-indexed)
    code_line: str          # 代碼行內容
    error_message: str      # 錯誤信息 (可選)
```

#### CodeSnippet
```python
class CodeSnippet(BaseModel):
    file_path: str          # 文件路徑
    start_line: int         # 開始行號
    end_line: int           # 結束行號
    content: str            # 代碼內容
    language: str           # 編程語言 (python, javascript, typescript, etc.)
    relevance_score: float  # 相關性得分 (0.0-1.0)
    context: str            # 上下文描述
```

#### CodeContext
```python
class CodeContext(BaseModel):
    issue_id: str
    repository: str         # org/repo 格式
    repository_url: str
    language: str           # 主要編程語言
    stack_traces: List[StackTrace]
    code_snippets: List[CodeSnippet]
    related_files: List[str]
    summary: str
    extracted_at: datetime
    repository_branch: str
    clone_size_mb: float
```

## 🚀 快速開始

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

新增依賴：
- `tree-sitter` - 通用代碼解析器 (可選，用於未來擴展)
- `tree-sitter-python` - Python 語言支持
- `tree-sitter-javascript` - JavaScript 語言支持

### 2. 配置環境

確保 `.env` 文件包含：
```bash
GITHUB_TOKEN=your_token_here
```

### 3. 運行測試

```bash
python bounty_bot/tests/test_ingestor.py
```

輸出範例：
```
🤖 PHASE 3: CODE INGESTOR - UNIT TESTS
============================================================

🧪 Test 1: Python Stack Trace Extraction
✓ Extracted 1 stack traces
✅ PASS - Python Stack Trace Extraction

...

✨ Test Results: 9 passed, 0 failed
🎉 All tests passed!
```

### 4. 使用 CodeIngestor

```python
from bounty_bot.src.ingestor import CodeIngestor
from bounty_bot.src.monitor import BountyIssue

# 初始化
ingestor = CodeIngestor()

# 處理一個 Issue
context = ingestor.ingest_issue(
    issue_id="issue-123",
    repository_url="https://github.com/tensorflow/tensorflow",
    repository="tensorflow/tensorflow",
    language="python",
    issue_title="Fix memory leak in Layer API",
    issue_description=issue_text,  # 包含堆棧跟蹤
    branch="main"
)

# 保存上下文供後續使用
ingestor.save_context(context, "context.json")

# 查看結果
print(f"Stack traces: {len(context.stack_traces)}")
print(f"Code snippets: {len(context.code_snippets)}")
print(f"Related files: {context.related_files}")
```

## 📊 Ingestion 流程

```
┌─────────────────────────────────────────────────────┐
│ ingest_issue()                                      │
├─────────────────────────────────────────────────────┤
│ 1. StackTraceExtractor.extract_from_text()          │
│    ├─ 正則表達式匹配堆棧跟蹤                        │
│    └─ 返回 StackTrace 列表                          │
│                                                      │
│ 2. _clone_repository()                              │
│    ├─ 執行 git clone --depth=1                      │
│    └─ 返回克隆路徑                                  │
│                                                      │
│ 3. _find_related_files()                            │
│    ├─ 根據堆棧跟蹤找文件                            │
│    ├─ 按文件擴展名搜索相關文件                      │
│    └─ 返回相關文件列表                              │
│                                                      │
│ 4. _extract_code_snippets()                         │
│    ├─ 在堆棧跟蹤行周圍提取代碼                      │
│    ├─ 解析 Python AST 提取函數/類                   │
│    └─ 返回 CodeSnippet 列表                         │
│                                                      │
│ 5. _generate_context_summary()                      │
│    └─ 生成人類可讀的摘要                            │
│                                                      │
│ 6. Cleanup                                          │
│    └─ 刪除臨時克隆目錄                              │
└─────────────────────────────────────────────────────┘
```

## 🔑 特性詳解

### Stack Trace Extraction

支持的模式：

**Python:**
```
File "src/utils.py", line 42, in process_data
    result = calculate_sum(data)
```

**JavaScript/TypeScript:**
```
at processArray (app.js:45:12)
at main (index.js:120:5)
```

### Code Context Extraction

1. **堆棧跟蹤周圍代碼** - 自動提取錯誤發生位置周圍 5 行代碼
2. **相關函數/類** - 使用 AST 解析提取相關函數和類定義
3. **導入語句** - 提取文件的所有導入以理解依賴

### 相關性評分

```python
relevance_score: float  # 0.0-1.0
```

- `1.0` - 堆棧跟蹤直接指向
- `0.7` - 相關函數或類
- `0.5` - 同一文件的其他代碼

## 🧹 清理機制

Ingestor 會自動清理：
- 臨時克隆的倉庫目錄
- 大型日誌文件
- 緩存的上下文數據（可配置）

避免硬盤空間浪費。

## 📈 性能優化

1. **Shallow Clone** (`--depth=1`)
   - 典型倉庫從 100MB+ 減少到 10-50MB
   - 克隆時間從 30+ 秒減少到 2-5 秒

2. **有限文件掃描**
   - 最多搜索 20 個相關文件
   - 最多提取 5 個相關函數

3. **智能目錄過濾**
   - 跳過 `.git`, `node_modules`, `__pycache__` 等

## 🐛 錯誤處理

- 支持備用分支 (main → master)
- 優雅降級（無 GitHub token 時跳過某些功能）
- 完整異常日誌記錄

## 🔮 未來擴展

### Phase 4 集成
- Solver 模組將使用 `CodeContext` 生成修復補丁
- LLM prompt 將包含提取的代碼片段和堆棧跟蹤

### 支持更多語言
- 當前使用 Python AST (內置)
- 可使用 Tree-sitter 支持 Java、Go、Rust 等

### 高級功能
- 依賴圖分析
- 代碼相似度搜索
- 歷史修復模式挖掘

## 📊 測試結果

```
✨ Test Results: 9 passed, 0 failed
✅ PASS - Python Stack Trace Extraction
✅ PASS - JavaScript Stack Trace Extraction
✅ PASS - CodeSnippet Model
✅ PASS - CodeContext Model
✅ PASS - Language Detection
✅ PASS - CodeIngestor Initialization
✅ PASS - Repository Clone (Mocked)
✅ PASS - Complete Issue Ingestion (Mocked)
✅ PASS - Context Serialization
```

## 📝 集成檢查清單

- [x] StackTraceExtractor 實現並測試
- [x] CodeParser 實現並測試
- [x] CodeIngestor 實現並測試
- [x] 數據模型完整
- [x] 錯誤處理完善
- [x] 性能優化實施
- [x] 單元測試 100% 通過
- [ ] 集成 Monitor 模組（Phase 4 預留）
- [ ] 集成 Solver 模組（Phase 4）

