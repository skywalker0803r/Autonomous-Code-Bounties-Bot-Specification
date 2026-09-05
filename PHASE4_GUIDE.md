# Phase 4: LLM Solver - Implementation Guide

## ✅ 完成功能

### 1. **LLMSolver 類** (`bounty_bot/src/solver.py`)

#### 核心功能
- ✅ **系統提示詞生成**: 基於 Issue 上下文構建清晰的系統提示詞
- ✅ **Gemini API 呼叫**: 調用 Google Gemini API 生成補丁
- ✅ **Unified Diff 解析**: 解析 LLM 生成的統一 Diff 格式補丁
- ✅ **補丁應用**: 將生成的補丁安全地應用到本地倉庫
- ✅ **錯誤處理**: 完善的異常捕捉和驗證機制
- ✅ **上下文管理**: 整合 CodeContext，提供完整的代碼上下文給 LLM

#### 主要方法

| 方法 | 說明 |
|------|------|
| `solve_issue()` | 主入口：根據 Issue 和代碼上下文生成補丁 |
| `_build_system_prompt()` | 構建系統提示詞 (角色、責任、要求) |
| `_build_user_prompt()` | 構建用戶提示詞 (Issue 描述、上下文) |
| `_call_gemini_api()` | 調用 Gemini API 生成補丁 |
| `_parse_diff()` | 解析統一 Diff 格式 |
| `_apply_patch()` | 應用補丁到本地倉庫 |
| `_validate_patch()` | 驗證補丁的有效性 |
| `_cleanup()` | 清理臨時文件 |

### 2. **數據模型**

#### PatchResult
```python
class PatchResult(BaseModel):
    issue_id: str
    solver_id: str                  # Solver 實例 ID (用於追蹤)
    original_code: str              # 原始代碼
    patched_code: str               # 打補丁後的代碼
    diff: str                       # 統一 Diff 格式
    files_affected: List[str]       # 受影響的文件列表
    changes_summary: str            # 修改摘要
    patch_size_bytes: int           # 補丁大小
    confidence_score: float         # 信心分數 (0.0-1.0)
    generated_at: datetime
    model_used: str                 # 使用的 LLM 模型
    prompt_tokens: int              # 使用的 prompt tokens
    completion_tokens: int          # 使用的 completion tokens
```

#### SolverConfig
```python
class SolverConfig(BaseModel):
    model: str = "gemini-3.1-pro-preview"
    temperature: float = 0.7        # 創意度 (0.0-1.0)
    max_tokens: int = 4096          # 最大輸出 tokens
    timeout_seconds: int = 60       # API 呼叫超時時間
```

### 3. **API 提示詞結構**

#### 系統提示詞 (System Prompt)
```
你是一位資深的開源軟體工程師，擅長於快速修復 Bug。
你的任務是根據提供的 Issue 描述和代碼上下文，生成一個統一 Diff 格式的補丁。

要求：
1. 仔細分析堆棧跟蹤和相關代碼
2. 生成最小化的、針對性的補丁
3. 補丁必須是統一 Diff 格式
4. 避免不必要的格式變更或重構
5. 確保修復直接解決根本原因
6. 提供簡要的修復說明
```

#### 用戶提示詞 (User Prompt)
```
Issue ID: {issue_id}
Repository: {repository}
Language: {language}

Issue Description:
{issue_title}
{issue_description}

Stack Traces:
{stack_traces}

Related Code Snippets:
{code_snippets}

請生成一個統一 Diff 格式的補丁來修復此問題。
補丁應該直接應用到倉庫的主分支代碼上。
```

## 🚀 快速開始

### 1. 安裝依賴

已在 `requirements.txt` 中配置：
```bash
pip install -r requirements.txt
```

核心依賴：
- `google-generativeai>=0.3.0` - Google Gemini API
- `GitPython==3.1.40` - Git 操作
- `pydantic==2.5.0` - 數據模型

### 2. 配置環境

確保 `.env` 文件包含：
```bash
GEMINI_API_KEY=your_api_key_here
GITHUB_TOKEN=your_github_token_here
```

從 [Google AI Studio](https://aistudio.google.com/app/apikey) 獲取 Gemini API Key。

### 3. 運行測試

```bash
python bounty_bot/tests/test_solver.py
```

輸出範例：
```
🤖 PHASE 4: LLM SOLVER - UNIT TESTS
============================================================

🧪 Test 1: Diff Parsing
✓ Parsed 2 file changes
✅ PASS - Diff Parsing

🧪 Test 2: System Prompt Generation
✓ Generated system prompt (285 chars)
✅ PASS - System Prompt Generation

🧪 Test 3: Patch Result Model
✓ PatchResult created successfully
✅ PASS - Patch Result Model

✨ Test Results: 8 passed, 0 failed
🎉 All tests passed!
```

### 4. 使用 LLMSolver

```python
from bounty_bot.src.solver import LLMSolver
from bounty_bot.src.ingestor import CodeIngestor
from bounty_bot.src.monitor import BountyIssue

# 初始化
solver = LLMSolver()
ingestor = CodeIngestor()

# 假設已有 BountyIssue 和 CodeContext
code_context = ingestor.ingest_issue(...)

# 生成補丁
patch_result = solver.solve_issue(
    issue_id="issue-123",
    issue_title="Fix memory leak in Layer API",
    issue_description="The memory leak occurs in...",
    code_context=code_context,
    repository_path="/tmp/tensorflow"
)

# 查看結果
print(f"Patch generated: {patch_result.files_affected}")
print(f"Changes: {patch_result.changes_summary}")
print(f"Confidence: {patch_result.confidence_score}")

# 查看 Diff
print(patch_result.diff)

# 下一步：將補丁傳遞給 Tester (Phase 5)
```

## 📊 Solver 流程

```
┌─────────────────────────────────────────────────────┐
│ solve_issue()                                       │
├─────────────────────────────────────────────────────┤
│ 1. _build_system_prompt()                           │
│    └─ 定義 AI 角色和責任                             │
│                                                      │
│ 2. _build_user_prompt()                             │
│    ├─ 格式化 Issue 信息                              │
│    ├─ 包含堆棧跟蹤                                  │
│    ├─ 包含代碼片段                                  │
│    └─ 添加生成指示                                  │
│                                                      │
│ 3. _call_gemini_api()                               │
│    ├─ 驗證 API Key                                  │
│    ├─ 發送請求到 Gemini                             │
│    ├─ 監控 tokens 使用                              │
│    └─ 捕捉 API 異常                                 │
│                                                      │
│ 4. _parse_diff()                                    │
│    ├─ 驗證 Diff 格式                                │
│    ├─ 提取文件路徑                                  │
│    ├─ 解析行號                                      │
│    └─ 驗證 Diff 有效性                              │
│                                                      │
│ 5. _validate_patch()                                │
│    ├─ 檢查補丁格式                                  │
│    ├─ 驗證文件存在性                                │
│    ├─ 測試補丁應用 (dry-run)                        │
│    └─ 生成信心分數                                  │
│                                                      │
│ 6. _apply_patch() (可選)                            │
│    ├─ 創建備份                                      │
│    ├─ 應用補丁                                      │
│    ├─ 驗證應用成功                                  │
│    └─ 返回 PatchResult                              │
│                                                      │
│ 7. _cleanup()                                       │
│    └─ 清理臨時資源                                  │
└─────────────────────────────────────────────────────┘
```

## 🔧 常見問題

### Q1: 如何改變 LLM 模型？
編輯 `settings.yaml`：
```yaml
llm:
  provider: "gemini"
  model: "gemini-2.0"  # 或其他模型
```

### Q2: Gemini API 請求超時怎麼辦？
在 `SolverConfig` 中增加 `timeout_seconds`：
```python
solver = LLMSolver(config=SolverConfig(timeout_seconds=120))
```

### Q3: 如何驗證生成的補丁品質？
使用 `confidence_score` 字段（0.0-1.0）：
- 0.8+ : 高信心補丁，可直接提交
- 0.5-0.8 : 中等信心，建議人工審查
- <0.5 : 低信心，需要進一步處理

### Q4: 補丁失敗了怎麼辦？
檢查：
1. Issue 描述是否包含完整的堆棧跟蹤
2. CodeContext 是否正確提取
3. Gemini API 配額是否充足
4. 代碼語言是否支持

## 📝 集成檢查清單

- [ ] GEMINI_API_KEY 已設置
- [ ] CodeIngestor 能正確提取上下文
- [ ] test_solver.py 所有測試通過
- [ ] 可以生成有效的 Diff 格式補丁
- [ ] 補丁可以安全應用到代碼倉庫
- [ ] 信心分數計算準確

## 🎯 下一步

完成 Phase 4 後，下一步是：

**Phase 5: Docker Tester**
- 在 Docker 容器中構建目標倉庫
- 應用生成的補丁
- 運行測試套件
- 驗證 100% 通過率

見 PHASE5_GUIDE.md (待實現)
