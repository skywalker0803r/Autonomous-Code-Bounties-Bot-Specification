# Phase 5: Docker Tester - Implementation Guide

## ✅ 完成功能

### 1. **DockerTester 類** (`bounty_bot/src/tester.py`)

#### 核心功能
- ✅ **Docker 映像構建**: 從目標倉庫構建隔離的 Docker 映像
- ✅ **沙盒測試執行**: 在資源限制的容器中運行測試套件
- ✅ **標準輸出解析**: 捕獲並解析 pytest 結果
- ✅ **資源隔離**: 內存限制（4GB）、CPU 限制（2核）、禁用網絡
- ✅ **超時保護**: 可配置的執行超時（默認 300 秒）
- ✅ **錯誤處理**: 基礎設施失敗獨立報告

#### 主要方法

| 方法 | 說明 |
|------|------|
| `run_tests()` | 主入口：在 Docker 沙盒中執行測試 |
| `build_image()` | 從倉庫構建 Docker 映像 |
| `_parse_pytest_summary()` | 從輸出解析 pytest 摘要 |
| `_get_client()` | 獲取 Docker 客戶端（支持依賴注入） |

### 2. **數據模型**

#### TestResult
```python
class TestResult(BaseModel):
    status: str                      # "READY_FOR_PR", "TESTS_FAILED", "INFRASTRUCTURE_FAILED"
    passed: bool                     # 測試是否全部通過
    exit_code: Optional[int]         # 容器退出碼
    command: str                     # 執行的測試命令
    image: str                       # Docker 映像名稱
    duration_seconds: float          # 執行時間
    stdout: str                      # 標準輸出
    stderr: str                      # 標準錯誤
    tests_run: int                   # 運行的測試數量
    tests_passed: int                # 通過的測試數量
    tests_failed: int                # 失敗的測試數量
    tests_skipped: int               # 跳過的測試數量
    error: Optional[str]             # 錯誤信息
    completed_at: datetime           # 完成時間
```

#### TesterConfig
```python
class TesterConfig(BaseModel):
    image: str = "bounty-sandbox"
    memory_limit: str = "4g"
    cpu_limit: float = 2.0
    timeout_seconds: int = 300
    test_command: str = "pytest --tb=short -v"
    network_disabled: bool = True
```

### 3. **工作流程**

#### 基本使用
```python
from bounty_bot.src.tester import DockerTester, TesterConfig

# 創建配置
config = TesterConfig(
    image="bounty-sandbox",
    memory_limit="4g",
    timeout_seconds=300
)

# 初始化測試器
tester = DockerTester(config)

# 執行測試
result = tester.run_tests(
    repository_path="/path/to/repo",
    build=True  # 先構建映像
)

# 檢查結果
if result.status == "READY_FOR_PR":
    print("✓ 補丁已驗證，可以提交 PR")
elif result.status == "TESTS_FAILED":
    print("✗ 測試失敗")
    print(result.stdout)
else:
    print("✗ 基礎設施失敗:", result.error)
```

#### 結果狀態

| 狀態 | 說明 | 下一步 |
|------|------|--------|
| `READY_FOR_PR` | 所有測試通過 | 提交 PR (Phase 6) |
| `TESTS_FAILED` | 測試失敗 | 返回 Phase 4 重新修復 |
| `INFRASTRUCTURE_FAILED` | Docker/環境問題 | 檢查環境並重試 |

## 🚀 快速開始

### 1. 構建沙盒映像

```bash
# 使用提供的 Dockerfile
docker build -f bounty_bot/docker/sandbox.Dockerfile -t bounty-sandbox .
```

### 2. 準備測試倉庫

確保目標倉庫包含：
- `Dockerfile` 或 `docker-compose.yml`（用於構建）
- 測試文件（`pytest`、`unittest` 等）
- 依賴聲明（`requirements.txt`、`package.json` 等）

### 3. 運行測試

```bash
python bounty_bot/tests/test_tester.py
```

## 🏗️ Docker 沙盒配置

### Dockerfile (`bounty_bot/docker/sandbox.Dockerfile`)

沙盒映像包含：
- Python 運行時和測試工具
- 隔離的文件系統
- 資源限制（內存、CPU）
- 網絡隔離

```dockerfile
FROM python:3.11-slim

# 安裝依賴
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 設置工作目錄
WORKDIR /app

# 複製應用代碼
COPY . /app

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 默認命令
CMD ["pytest", "--tb=short", "-v"]
```

## 📊 性能特點

- **隔離性**: 每次運行都在新容器中執行
- **可重現性**: 完全控制的環境，結果一致
- **安全性**: 禁用網絡，防止外部通信
- **資源限制**: 防止資源耗盡
- **超時保護**: 防止無限循環

## 🔧 故障排除

### Docker 不可用
```
錯誤: Docker SDK is not installed
解決: pip install docker
```

### 映像構建失敗
```
檢查: Dockerfile 是否存在且有效
檢查: 倉庫是否包含所需的依賴文件
```

### 測試超時
```
原因: 測試執行時間過長
解決: 增加 timeout_seconds 或優化測試
```

### 內存限制
```
原因: 測試需要超過 4GB 內存
解決: 修改 memory_limit 配置
```

## 📝 測試結果持久化

```python
# 保存測試結果
with open("test_result.json", "w") as f:
    json.dump(result.dict(default=str), f, indent=2)

# 加載和分析
import json
with open("test_result.json", "r") as f:
    data = json.load(f)
    print(f"通過: {data['tests_passed']}, 失敗: {data['tests_failed']}")
```

## 🎯 與其他 Phase 的集成

- **Phase 4 输入**: 接收 `PatchResult` 和補丁應用的代碼
- **Phase 6 输出**: `TestResult.status == "READY_FOR_PR"` 觸發 PR 提交

## ✨ 主要優勢

1. **完全隔離**: 無法危害主機系統
2. **可重現**: 同一補丁多次測試結果相同
3. **快速反饋**: 快速識別不工作的補丁
4. **詳細日誌**: 完整的標準輸出和錯誤信息
5. **資源安全**: 內存和 CPU 限制防止濫用

## 🐛 調試

### 查看容器日誌
```bash
docker logs <container_id>
```

### 交互式容器
```bash
docker run -it bounty-sandbox bash
```

### 保存失敗的容器
```python
config = TesterConfig(
    image="bounty-sandbox",
    # auto_remove=False  # 保留容器以便調試
)
```
