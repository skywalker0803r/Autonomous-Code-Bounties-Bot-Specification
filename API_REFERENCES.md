# API References - Autonomous Code Bounties Bot

## Overview
This document contains links and basic documentation for all external APIs used by the bounty bot system.

---

## Algora API

### Endpoint
```
https://api.algora.io/v1/bounties
```

### Documentation
- **Official Docs**: https://algora.io/docs/api
- **API Base URL**: https://api.algora.io/v1
- **Authentication**: API Key (optional, but recommended)

### Key Endpoints

#### List Bounties
```
GET https://api.algora.io/v1/bounties
Query Parameters:
  - language: string (Python, TypeScript, JavaScript, etc.)
  - min_amount: float (minimum bounty in USD)
  - status: string (open, closed)
```

### Example Integration
```python
import requests

headers = {"Authorization": f"Bearer {ALGORA_API_KEY}"}
response = requests.get(
    "https://api.algora.io/v1/bounties",
    params={
        "language": "Python",
        "min_amount": 50,
        "status": "open"
    },
    headers=headers
)
bounties = response.json()
```

### Rate Limiting
- 60 requests per minute

---

## GitHub REST API

### Documentation
- **Official Docs**: https://docs.github.com/en/rest
- **API Base URL**: https://api.github.com
- **Authentication**: Personal Access Token (Required for this bot)

### Key Endpoints for Bounty Bot

#### Search Issues
```
GET https://api.github.com/search/issues
Query: label:bounty state:open language:Python
```

**Reference**: https://docs.github.com/en/rest/search/search?apiVersion=2022-11-28#search-issues-and-pull-requests

#### Get Repository Details
```
GET https://api.github.com/repos/{owner}/{repo}
```
Used to determine repository primary language.

**Reference**: https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#get-a-repository

#### Create Pull Request
```
POST https://api.github.com/repos/{owner}/{repo}/pulls
```

**Reference**: https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#create-a-pull-request

### Example Integration (via gh CLI)
```bash
# Much simpler than REST API - use this in submitter.py
gh pr create \
  --title "fix: resolve Issue #123" \
  --body "Automated fix verified by test suite" \
  --repo owner/repo
```

### Rate Limiting
- 60 requests per minute (unauthenticated)
- 5,000 requests per hour (authenticated)

### Personal Access Token Setup
1. Go to: https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Grant scopes:
   - `repo` (Full control of private repositories)
   - `workflow` (Update GitHub Action workflows)
4. Copy token to `.env` as `GITHUB_TOKEN`

---

## Google Generative AI (Gemini) API

### Documentation
- **Official Docs**: https://ai.google.dev/docs
- **API Reference**: https://ai.google.dev/tutorials/python_quickstart
- **API Key**: Get from https://aistudio.google.com/app/apikey

### Key Models for This Bot

#### Gemini 2.5 Pro (Recommended)
- **Model ID**: `gemini-2.5-pro`
- **Best For**: Code patch generation, complex reasoning
- **Context Window**: 1 million tokens
- **Cost**: ~$1.25 / 1M input tokens, $5 / 1M output tokens

**Docs**: https://ai.google.dev/api/rest/v1beta/models/generateContent

#### Gemini 1.5 Flash (Budget Option)
- **Model ID**: `gemini-1.5-flash`
- **Context Window**: 1 million tokens
- **Cost**: ~$0.075 / 1M input tokens, $0.3 / 1M output tokens

### Example Integration
```python
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-pro")

response = model.generate_content(
    f"""
    Fix this bug based on the issue description and code context:
    
    Issue: {issue_description}
    
    Code:
    {code_snippet}
    
    Provide ONLY the unified diff format patch, nothing else.
    """
)

patch = response.text
```

### Rate Limiting
- 10 requests per minute (free tier)
- Upgrade for higher limits

### Free Tier Restrictions
- Max 1,500 requests per day
- Max 2 concurrent requests

### Setup
1. Go to: https://aistudio.google.com/app/apikey
2. Click "Create API Key"
3. Copy to `.env` as `GEMINI_API_KEY`

---

## Environment Variables Summary

Create `.env` file with these keys:

```bash
# Google Gemini API
GEMINI_API_KEY=your_key_here

# GitHub
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_USERNAME=your_github_username

# Algora (Optional)
ALGORA_API_KEY=your_algora_api_key_here

# Logging
LOG_LEVEL=INFO
```

---

## Testing with Mock APIs

For local development without spending API quota:

### Mock Algora
```python
# In tests, replace requests.get() with a mock
from unittest.mock import patch

@patch('requests.get')
def test_algora_polling(mock_get):
    mock_get.return_value.json.return_value = {
        "bounties": [
            {
                "id": "test-1",
                "title": "Fix bug",
                "amount": 100,
                "language": "Python"
            }
        ]
    }
    # Test your code
```

### Mock GitHub API
```python
from unittest.mock import patch

@patch('requests.get')
def test_github_search(mock_get):
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "number": 123,
                "title": "Bug fix needed",
                "repository_url": "https://api.github.com/repos/owner/repo"
            }
        ]
    }
```

### Mock Gemini API
```python
from unittest.mock import patch

@patch('google.generativeai.GenerativeModel.generate_content')
def test_patch_generation(mock_generate):
    mock_generate.return_value.text = "--- a/file.py\n+++ b/file.py\n..."
```

---

## Useful CLI Tools

### GitHub CLI (gh)
Pre-installed and used for PR submission. Super convenient!

```bash
# Login
gh auth login

# Create PR
gh pr create --title "Title" --body "Body" --repo owner/repo

# Check PR status
gh pr status

# View PR
gh pr view 123
```

**Docs**: https://cli.github.com/manual

---

## Cost Estimation (Monthly)

Assuming 10 bounties processed per day:

| Service | Calls/Month | Cost |
|---------|-------------|------|
| Gemini API | 300 calls | ~$0.50 |
| GitHub API | 600 calls | Free (within limit) |
| Algora API | 300 calls | Free |
| **Total** | | **~$0.50** |

If patches work 50% of time and avg bounty is $75:
- Monthly income: ~$1,125
- API costs: ~$0.50
- **ROI: 225,000%** 🚀

---

## Debugging API Issues

### Enable Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# For requests library
import http.client
http.client.HTTPConnection.debuglevel = 1
```

### Common Issues

**"Invalid API Key"**
- Check `.env` file has correct key
- Test key at: https://aistudio.google.com/app/apikey

**"Rate Limited"**
- Wait 60+ seconds before retrying
- Implement exponential backoff in code

**"401 Unauthorized on GitHub"**
- Verify `GITHUB_TOKEN` has `repo` scope
- Token might be expired or revoked

---

**Last Updated**: 2026-08-30
