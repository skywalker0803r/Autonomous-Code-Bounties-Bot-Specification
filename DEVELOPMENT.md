# Development Roadmap - Autonomous Code Bounties Bot

## Project Overview
系統旨在完全自動化監控、修復和提交開源懸賞 Issue，實現被動收入。

## Architecture Flow
```
Monitor (Algora/GitHub) 
  → Ingest (AST/Context) 
  → Solve (LLM Patch) 
  → Test (Docker Sandbox) 
  → Submit (Auto PR) 
  → Earn (Bounty)
```

## Development Phases

### Phase 1: Core Infrastructure (✅ COMPLETE)
- [x] Project structure initialized
- [x] Configuration framework setup
- [x] Docker sandbox definition
- [x] Environment setup guide

### Phase 2: Issue Monitor (✅ COMPLETE)
**File:** `bounty_bot/src/monitor.py`
- [x] Implement Algora API polling with pagination
- [x] Implement GitHub REST API polling
- [x] Filter by language, bounty amount, and labels
- [x] Extract bounty amounts from GitHub issue text
- [x] Store identified issues in local cache
- [x] Deduplicate issues from multiple sources
- [x] Main entry point with CLI (bounty_bot/main.py)
- [x] Full unit test coverage
- [x] Documentation (PHASE2_GUIDE.md)

See [PHASE2_GUIDE.md](PHASE2_GUIDE.md) for detailed implementation guide.

### Phase 3: Code Ingestor (✅ COMPLETE)
**File:** `bounty_bot/src/ingestor.py`
- [x] Shallow clone target repository (--depth=1)
- [x] Extract stack traces from issue description (Python/JavaScript/TypeScript)
- [x] Use AST (Python) to parse code context
- [x] Generate compressed code snippets for LLM input
- [x] Stack trace extraction with regex patterns
- [x] Code context serialization to JSON
- [x] Full unit test coverage
- [x] Documentation (PHASE3_GUIDE.md)

See [PHASE3_GUIDE.md](PHASE3_GUIDE.md) for detailed implementation guide.

### Phase 4: LLM Solver (✅ COMPLETE)
**File:** `bounty_bot/src/solver.py`
- [x] Build system prompt with issue context
- [x] Build user prompt with code context and stack traces
- [x] Call Gemini API for patch generation
- [x] Parse unified diff format from LLM response
- [x] Calculate confidence score for patch quality
- [x] Apply patches to local repository (dry-run and actual)
- [x] Serialize/deserialize patch results to JSON
- [x] Error handling and validation
- [x] Full unit test coverage
- [x] Documentation (PHASE4_GUIDE.md)

See [PHASE4_GUIDE.md](PHASE4_GUIDE.md) for detailed implementation guide.

### Phase 5: Docker Tester (✅ COMPLETE)
**File:** `bounty_bot/src/tester.py`
- [x] Build Docker image from target repo
- [x] Run test suite in a resource-limited container
- [x] Capture stdout/stderr and parse pytest result counts
- [x] Validate exit code 0 before marking `READY_FOR_PR`
- [x] Return structured infrastructure failures for missing Docker or timeouts

Usage:
```python
from bounty_bot.src.tester import DockerTester, TesterConfig

tester = DockerTester(TesterConfig(timeout_seconds=300))
result = tester.run_tests("/tmp/repos/issue-123", build=True)
if result.status == "READY_FOR_PR":
  print("Patch is ready for submission")
```

Tests are executed with networking disabled, a 4 GB memory limit, and two CPUs
by default. The runner uses dependency injection for the Docker client so unit
tests do not require a running Docker daemon.

### Phase 6: Auto Submitter
**File:** `bounty_bot/src/submitter.py`
- Create feature branch (fix/bounty-issue-{id})
- Commit changes with descriptive message
- Push to forked repository
- Create PR using GitHub CLI
- Monitor PR status

### Phase 7: Main Orchestrator
**File:** `bounty_bot/main.py`
- Implement 24/7 daemon loop
- Coordinate all modules
- Handle error recovery
- Log all operations

## Implementation Guidelines

### Commit Message Format
When implementing each module, use this format:

```
feat(module-name): Brief implementation summary

Detailed description of:
- What this module does
- Key algorithms or APIs used
- How it integrates with other modules
- Prerequisites/dependencies
- How the next developer should extend this

TODO:
- [ ] Task 1
- [ ] Task 2
```

### Testing
- Add unit tests for each module
- Test integration between modules
- Mock external APIs (Algora, GitHub, Gemini)

### Error Handling
- Retry logic with exponential backoff
- Graceful degradation for API failures
- Detailed logging for debugging

## Environment Variables Required
```bash
GEMINI_API_KEY=xxx
GITHUB_TOKEN=xxx
GITHUB_USERNAME=xxx
ALGORA_API_KEY=xxx  # Optional
```

## Quick Start (After Implementation)
```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Build Docker sandbox
docker build -f bounty_bot/docker/sandbox.Dockerfile -t bounty-sandbox .

# Run bot
python bounty_bot/main.py --daemon --interval 300
```

## Success Metrics
- [ ] Can identify 5+ qualifying issues per day
- [ ] Successfully generate patches for 50%+ of identified issues
- [ ] 80%+ test pass rate for generated patches
- [ ] Auto-submit functional PRs with 90%+ merge rate
- [ ] Process 10+ bounties monthly (~$500+ passive income)

## Notes for Next Developer
- Start with Phase 2 (monitor.py)
- Use settings.yaml for all configuration
- Mock APIs in development/testing
- Keep modules loosely coupled
- Document integration points clearly

---

## 🌍 網咖快速開始 (Offline/New Machine)

如果你在一個新機器或網咖電腦上，要快速繼續開發：

### 步驟 1：環境準備（3 分鐘）
```bash
# Clone repo
git clone https://github.com/skywalker0803r/Autonomous-Code-Bounties-Bot-Specification.git
cd Autonomous-Code-Bounties-Bot-Specification

# 安裝依賴
pip install -r requirements.txt

# 複製環境配置
cp .env.example .env
```

### 步驟 2：填寫 API Keys（需要你自己的帳號）
編輯 `.env` 文件：
```bash
# 獲取 Gemini API Key: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your_key_here

# 獲取 GitHub Token: https://github.com/settings/tokens
# 需要 scope: repo, workflow
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_USERNAME=your_github_username
```

### 步驟 3：檢查項目狀態（1 分鐘）
```bash
# 查看當前進度
cat DEVELOPMENT.md | grep "Phase"

# 查看 TODO 列表
grep -n "TODO" bounty_bot/src/monitor.py
```

### 步驟 4：開始開發（立即）
按照下面的「推薦開發順序」從 Phase 2 開始

---

## 🚀 推薦開發順序（給接手的 Agent）

### 立即開始
1. 閱讀這個文件的「Architecture Flow」和「Development Phases」
2. 打開 [bounty_bot/src/monitor.py](bounty_bot/src/monitor.py) - 看 TODO 列表
3. 參考 [API_REFERENCES.md](API_REFERENCES.md) 的 API 文檔
4. 參考 [README.md](README.md) 的系統架構圖

### 第一個任務：Phase 2
從 **monitor.py** 開始，實現：
- [ ] Algora API 輪詢
- [ ] GitHub API 輪詢
- [ ] 過濾邏輯（語言、金額、標籤）
- [ ] 緩存管理

**預計時間**：2-3 小時

### 測試你的代碼
```bash
# 運行單元測試（寫在 tests/ 目錄）
pytest bounty_bot/tests/test_monitor.py -v

# 用 mock APIs 測試（不消耗配額）
# 見 API_REFERENCES.md 的 "Testing with Mock APIs"
```

### Git 提交規則
```
feat(monitor): Implement Algora API polling

詳細描述你做了什麼:
- Algora API 集成完成
- Filter logic 已實現
- Cache 系統已設置

下一步:
- [ ] Phase 3: Implement ingestor.py
- [ ] Add integration tests

TODO 列表見 bounty_bot/src/ingestor.py
```
