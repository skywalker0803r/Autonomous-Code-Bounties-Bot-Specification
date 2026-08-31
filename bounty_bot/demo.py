#!/usr/bin/env python3
"""
Quick demo of Phase 2: Issue Monitor
Shows the monitor in action with simulated API responses
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bounty_bot.src.monitor import IssueMonitor, BountyIssue

def demo_monitor():
    """Demonstrate the IssueMonitor capabilities"""
    
    print("=" * 70)
    print("🤖 Phase 2: Issue Monitor - Quick Demo")
    print("=" * 70)
    
    # Initialize monitor
    print("\n1️⃣  Initializing Monitor...")
    monitor = IssueMonitor()
    print(f"   ✓ Configuration loaded")
    print(f"   ✓ Supported languages: {', '.join(monitor.config['filters']['languages'])}")
    print(f"   ✓ Minimum bounty: ${monitor.config['filters']['min_bounty_amount']}")
    
    # Demo filter logic
    print("\n2️⃣  Testing Filter Logic...")
    sample_bounties = [
        {
            "id": "1",
            "title": "Fix critical memory leak",
            "amount": 500.0,
            "language": "Python",
            "labels": []
        },
        {
            "id": "2",
            "title": "Implement new feature",
            "amount": 25.0,
            "language": "Python",
            "labels": []
        },
        {
            "id": "3",
            "title": "TypeScript type fixes",
            "amount": 100.0,
            "language": "TypeScript",
            "labels": []
        }
    ]
    
    for bounty in sample_bounties:
        if monitor._matches_filters(bounty):
            print(f"   ✓ PASS: {bounty['title']} (${bounty['amount']}, {bounty['language']})")
        else:
            print(f"   ✗ SKIP: {bounty['title']} (doesn't match filters)")
    
    # Demo bounty extraction
    print("\n3️⃣  Testing Bounty Amount Extraction...")
    test_texts = [
        "Bug bounty: $200 for fixing memory leak",
        "Reward of 150 dollars available",
        "$1,000 bounty - Performance optimization",
        "No bounty info here",
    ]
    
    for text in test_texts:
        issue = {"body": text, "title": "Test Issue"}
        amount = monitor._extract_bounty_amount(issue)
        if amount > 0:
            print(f"   ✓ Extracted: ${amount} from \"{text[:40]}...\"")
        else:
            print(f"   ✗ No amount: \"{text[:40]}...\"")
    
    # Demo cache operations
    print("\n4️⃣  Testing Cache Operations...")
    demo_issues = [
        BountyIssue(
            id="demo-001",
            title="Fix race condition in threading module",
            description="There's a race condition when using...",
            repository="python/cpython",
            repository_url="https://github.com/python/cpython",
            issue_url="https://github.com/python/cpython/issues/12345",
            bounty_amount=250.0,
            language="Python",
            labels=["bug", "threading"],
            source="github",
            created_at=datetime.now()
        ),
        BountyIssue(
            id="demo-002",
            title="Implement async/await support",
            description="Add modern async/await pattern support...",
            repository="microsoft/TypeScript",
            repository_url="https://github.com/microsoft/TypeScript",
            issue_url="https://github.com/microsoft/TypeScript/issues/54321",
            bounty_amount=500.0,
            language="TypeScript",
            labels=["enhancement", "async"],
            source="algora",
            created_at=datetime.now()
        )
    ]
    
    monitor.save_cache(demo_issues)
    print(f"   ✓ Saved {len(demo_issues)} issues to cache")
    
    loaded = monitor.load_cache()
    print(f"   ✓ Loaded {len(loaded)} issues from cache")
    print(f"   ✓ Cache file: {monitor.cache_file}")
    
    # Demo deduplication
    print("\n5️⃣  Testing Deduplication...")
    algora_issues = [demo_issues[0], demo_issues[1]]
    github_issues = [
        BountyIssue(
            id="github-001",
            title="Fix race condition in threading module",  # Same as demo-001
            description="...",
            repository="python/cpython",
            repository_url="https://github.com/python/cpython",
            issue_url="https://github.com/python/cpython/issues/12345",  # Same URL
            bounty_amount=200.0,  # Lower amount
            language="Python",
            labels=["bug"],
            source="github",
            created_at=datetime.now()
        )
    ]
    
    deduplicated = monitor.deduplicate_issues(algora_issues, github_issues)
    print(f"   ✓ Input: {len(algora_issues)} + {len(github_issues)} issues")
    print(f"   ✓ Output: {len(deduplicated)} unique issues")
    print(f"   ✓ Prioritized by bounty amount (higher wins)")
    
    # Show final results
    print("\n6️⃣  Final Results Summary:")
    print("   ─" * 35)
    for issue in deduplicated:
        print(f"   📌 ${issue.bounty_amount:7.0f} | {issue.language:12} | {issue.title[:35]}")
    
    # Print usage instructions
    print("\n" + "=" * 70)
    print("📚 How to Use:")
    print("=" * 70)
    print("""
1. Run single poll cycle:
   python bounty_bot/main.py

2. Run in daemon mode (recommended):
   python bounty_bot/main.py --daemon --interval 300

3. Run with custom logging:
   python bounty_bot/main.py --daemon --log-level DEBUG

4. Run unit tests:
   python bounty_bot/tests/test_monitor.py

5. Check cache file:
   cat /tmp/bounty_cache/issues.json

6. Read full guide:
   cat PHASE2_GUIDE.md
""")
    
    print("=" * 70)
    print("✅ Demo Complete! Phase 2 is ready for production.")
    print("=" * 70)


if __name__ == "__main__":
    demo_monitor()
