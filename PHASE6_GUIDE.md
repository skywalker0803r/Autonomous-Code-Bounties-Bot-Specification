# Phase 6: Auto Submitter - Implementation Guide

## ✅ 完成功能

### 1. **AutoSubmitter 類** (`bounty_bot/src/submitter.py`)

#### 核心功能
- ✅ **Fork 管理**: 自動創建或使用現有的 Fork
- ✅ **分支創建**: 自動創建特性分支 (fix/bounty-issue-{id})
- ✅ **補丁應用**: 使用 `git apply` 安全應用統一 Diff 補丁
- ✅ **Git 操作**: 自動提交 (Commit) 和推送 (Push)
- ✅ **PR 創建**: 通過 GitHub API 自動創建 Pull Request
- ✅ **GitHub 認證**: 支持 Token 認證和自動化 PR 描述

#### 主要方法

| 方法 | 說明 |
|------|------|
| `submit_patch()` | 主入口：從補丁到 PR 的完整流程 |
| `_get_or_create_fork()` | 獲取或創建 Fork 倉庫 |
| `_clone_fork()` | 克隆 Fork 到本地 |
| `_create_branch()` | 創建特性分支 |
| `_apply_patch()` | 應用統一 Diff 補丁 |
| `_commit_changes()` | 提交更改 |
| `_push_branch()` | 推送分支到遠程 |
| `_create_pull_request()` | 通過 GitHub API 創建 PR |

### 2. **數據模型**

#### SubmissionResult
```python
class SubmissionResult(BaseModel):
    issue_id: str                    # Bounty Issue ID
    submitter_id: str                # Submitter 實例 ID
    repository: str                  # 目標倉庫 (org/repo)
    fork_url: str                    # Fork URL
    branch_name: str                 # 特性分支名稱
    pr_url: Optional[str]            # PR URL (成功時)
    pr_number: Optional[int]         # PR 編號 (成功時)
    status: str                      # "PR_CREATED", "SUBMISSION_FAILED", "GIT_FAILED"
    commit_sha: Optional[str]        # 提交 SHA
    error_message: Optional[str]     # 錯誤信息 (失敗時)
    submitted_at: datetime           # 提交時間戳
    commit_message: str              # 提交信息
```

#### SubmitterConfig
```python
class SubmitterConfig(BaseModel):
    github_token: str                # GitHub 個人訪問令牌 (環境變量)
    github_username: str             # GitHub 用戶名 (環境變量)
    github_api_url: str = "https://api.github.com"
    git_user_name: str = "Autonomous Bounty Bot"
    git_user_email: str              # Git 用戶郵箱 (環境變量)
    repo_clone_dir: str = "/tmp/bounty_repos"
    branch_prefix: str = "fix/bounty"
    timeout_seconds: int = 300
```

### 3. **工作流程**

#### 完整 PR 提交流程

```
1. Fork 管理
   └─ 檢查是否存在 Fork
   └─ 如果不存在，通過 GitHub API 創建

2. 倉庫克隆
   └─ Shallow clone Fork (depth=1)
   └─ 使用 GitHub Token 認證

3. 分支創建
   └─ 從 main/master 創建新分支
   └─ 命名格式: fix/bounty-issue-{issue_id}

4. 補丁應用
   └─ 使用 git apply 應用 Unified Diff
   └─ 驗證補丁應用成功

5. 提交更改
   └─ 舞台所有修改 (git add -A)
   └─ 創建帶有描述性信息的 Commit

6. 推送分支
   └─ 推送分支到 Fork 遠程

7. 創建 PR
   └─ 通過 GitHub API 向原始倉庫提交 PR
   └─ 包含完整的 PR 描述和元數據
```

#### 基本使用

```python
from bounty_bot.src.submitter import AutoSubmitter, SubmitterConfig

# 創建配置（需要環境變量）
# export GITHUB_TOKEN=your_token_here
# export GITHUB_USERNAME=your_username_here
# export GIT_USER_EMAIL=bot@example.com

config = SubmitterConfig()
submitter = AutoSubmitter(config)

# 提交補丁
result = submitter.submit_patch(
    issue_id="123",
    issue_title="Fix: Critical Bug in Parser",
    repository_url="https://github.com/org/repo",
    repository="org/repo",
    patch_content=unified_diff_patch,
    issue_url="https://github.com/org/repo/issues/123"
)

# 檢查結果
if result.status == "PR_CREATED":
    print(f"✓ PR 已創建: {result.pr_url}")
else:
    print(f"✗ 提交失敗: {result.error_message}")
```

### 4. **GitHub Token 和認證**

#### 獲取 GitHub Token

1. 訪問 GitHub → Settings → Developer settings → Personal access tokens
2. 創建新 Token（Classic 或 Fine-grained）
3. 所需權限：
   - `repo` (完全倉庫訪問)
   - `workflow` (工作流程訪問)

#### 環境配置

```bash
# .env 文件
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_USERNAME=your_username
GIT_USER_EMAIL=bot@autonomousbounties.dev

# 或使用環境變量
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
export GITHUB_USERNAME=your_username
export GIT_USER_EMAIL=bot@autonomousbounties.dev
```

## 🚀 快速開始

### 1. 環境準備

```bash
# 安裝依賴
pip install -r requirements.txt

# 配置環境
cp .env.example .env
# 編輯 .env，填入 GitHub Token 和用戶名
```

### 2. 創建測試 Fork

```bash
# 手動創建 Fork 或通過腳本自動創建
python -c "
from bounty_bot.src.submitter import AutoSubmitter
submitter = AutoSubmitter()
# 首次運行時會自動創建 Fork
"
```

### 3. 運行測試

```bash
python bounty_bot/tests/test_submitter.py
```

## 🏗️ 詳細流程

### Fork 管理

```python
# 獲取或創建 Fork
fork_url = submitter._get_or_create_fork(
    repository_url="https://github.com/org/repo",
    repository="org/repo"
)
# 返回: https://github.com/username/repo
```

**邏輯**:
1. 檢查 `https://github.com/{username}/{repo}` 是否存在
2. 如果存在，直接返回
3. 如果不存在，通過 GitHub API 創建 Fork

### 克隆和分支

```python
# 克隆到本地
repo_path = submitter._clone_fork(fork_url, "issue_123")
# 返回: /tmp/bounty_repos/issue_123

# 創建分支
repo = Repo(repo_path)
branch = submitter._create_branch(repo, "123")
# 返回: fix/bounty-issue-123
```

### 補丁應用

```python
# 應用統一 Diff 補丁
submitter._apply_patch(repo, patch_content)

# 內部使用 git apply
# $ git apply /path/to/patch.diff
```

### 提交和推送

```python
# 構建提交信息
commit_msg = submitter._build_commit_message(
    issue_id="123",
    issue_title="Fix: Critical Bug",
    issue_url="https://github.com/org/repo/issues/123"
)

# 提交更改
commit_sha = submitter._commit_changes(repo, commit_msg)

# 推送分支
submitter._push_branch(repo, "fix/bounty-issue-123")
```

### PR 創建

```python
# 通過 GitHub API 創建 PR
pr_data = submitter._create_pull_request(
    fork_url=fork_url,
    repository="org/repo",
    branch_name="fix/bounty-issue-123",
    issue_title="Fix: Critical Bug",
    issue_url="https://github.com/org/repo/issues/123",
    commit_message=commit_msg
)
# 返回: {"html_url": "...", "number": 456, ...}
```

## 📊 錯誤處理

### 狀態碼

| 狀態 | 原因 | 建議 |
|------|------|------|
| `PR_CREATED` | PR 成功創建 | 監控 PR 狀態 |
| `SUBMISSION_FAILED` | API 或邏輯失敗 | 檢查日誌和 Token 權限 |
| `GIT_FAILED` | Git 操作失敗 | 檢查倉庫狀態和補丁格式 |

### 常見錯誤

```
错误: GITHUB_TOKEN environment variable is required
解決: export GITHUB_TOKEN=your_token_here

错误: Failed to create PR: 422 Unprocessable Entity
原因: 分支名稱重複或 PR 已存在
解決: 刪除現有分支或 PR，或修改分支名稱

错误: Patch application failed
原因: 補丁格式不正確或文件不匹配
解決: 驗證補丁格式和目標代碼版本
```

## 🔧 高級配置

### 自定義分支名稱

```python
config = SubmitterConfig()
config.branch_prefix = "feature/auto-fix"
submitter = AutoSubmitter(config)
```

### 自定義 PR 描述

修改 `_create_pull_request()` 中的 `pr_body` 以自定義 PR 描述格式。

### 超時配置

```python
config = SubmitterConfig(timeout_seconds=600)
submitter = AutoSubmitter(config)
```

## 📝 結果持久化

```python
# 保存提交結果
submitter.save_submission_result(
    result,
    "/tmp/bounty_cache/submissions/issue_123.json"
)

# 加載結果
loaded_result = AutoSubmitter.load_submission_result(
    "/tmp/bounty_cache/submissions/issue_123.json"
)
```

## 🎯 與其他 Phase 的集成

- **Phase 5 输入**: 接收 `TestResult.status == "READY_FOR_PR"` 時觸發
- **Phase 7 输出**: 被 Main Orchestrator 調用以提交 PR
- **后续步骤**: PR Merge 後可集成自動領取懸賞金功能

## ✨ 主要優勢

1. **完全自動化**: 無需手動干預
2. **安全認證**: 使用 Token 認證，不存儲密碼
3. **詳細日誌**: 完整的操作跟蹤
4. **錯誤恢復**: 優雅的錯誤處理
5. **可追蹤**: 結果持久化和分析

## 🔒 安全建議

1. 使用 Fine-grained Personal Access Token（更安全）
2. 定期輪換 Token
3. 限制 Token 權限到必要的倉庫
4. 不要在代碼中硬編碼 Token
5. 使用環境變量或密鑰管理系統

## 🐛 調試

### 查看詳細日誌

```python
import logging
logging.basicConfig(level=logging.DEBUG)

submitter = AutoSubmitter(config)
result = submitter.submit_patch(...)
```

### 保留臨時文件

修改 `_apply_patch()` 以不刪除補丁文件，便於檢查。

### 驗證 Fork 連接

```bash
# 測試 Fork URL
git clone https://github.com/username/repo --depth=1
```
