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

### Phase 1: Core Infrastructure (CURRENT)
- [x] Project structure initialized
- [x] Configuration framework setup
- [x] Docker sandbox definition
- [ ] Environment setup guide

### Phase 2: Issue Monitor (NEXT)
**File:** `bounty_bot/src/monitor.py`
- Implement Algora API polling
- Implement GitHub REST API polling
- Filter by language, bounty amount, and labels
- Store identified issues in local cache

### Phase 3: Code Ingestor
**File:** `bounty_bot/src/ingestor.py`
- Shallow clone target repository
- Extract stack traces from issue description
- Use AST (Python) or Tree-sitter to parse code context
- Generate compressed code snippets for LLM input

### Phase 4: LLM Solver
**File:** `bounty_bot/src/solver.py`
- Build system prompt with issue context
- Call Gemini API for patch generation
- Parse unified diff format
- Apply patches to local repository

### Phase 5: Docker Tester
**File:** `bounty_bot/src/tester.py`
- Build Docker image from target repo
- Run test suite in container
- Parse test results
- Validate 100% pass rate before marking READY_FOR_PR

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
