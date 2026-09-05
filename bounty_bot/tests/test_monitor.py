#!/usr/bin/env python3
"""
Test script for Phase 2: Monitor Module
Tests the IssueMonitor class with mock API responses
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bounty_bot.src.monitor import IssueMonitor, BountyIssue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_bounty_issue_model():
    """Test BountyIssue data model"""
    print("\n🧪 Test 1: BountyIssue Model")
    
    issue = BountyIssue(
        id="test-001",
        title="Fix memory leak in Layer API",
        description="There is a memory leak when using...",
        repository="tensorflow/tensorflow",
        repository_url="https://github.com/tensorflow/tensorflow",
        issue_url="https://github.com/tensorflow/tensorflow/issues/12345",
        bounty_amount=100.0,
        language="Python",
        labels=["bug", "memory-leak"],
        source="algora",
        created_at=datetime.now()
    )
    
    print(f"✓ Created BountyIssue: {issue.title}")
    print(f"  Repository: {issue.repository}")
    print(f"  Bounty: ${issue.bounty_amount}")
    print(f"  Language: {issue.language}")
    
    # Test JSON serialization
    json_data = issue.dict()
    print(f"✓ Serialized to JSON successfully")
    
    return True


def test_monitor_initialization():
    """Test Monitor initialization"""
    print("\n🧪 Test 2: Monitor Initialization")
    
    try:
        monitor = IssueMonitor()
        print(f"✓ Monitor initialized with config")
        print(f"  Supported languages: {monitor.config['filters']['languages']}")
        print(f"  Min bounty: ${monitor.config['filters']['min_bounty_amount']}")
        print(f"  Cache file: {monitor.cache_file}")
        return True
    except Exception as e:
        print(f"✗ Monitor initialization failed: {e}")
        return False


def test_filter_logic():
    """Test bounty filtering logic"""
    print("\n🧪 Test 3: Bounty Filtering Logic")
    
    monitor = IssueMonitor()
    
    test_cases = [
        {
            "bounty": {
                "id": "1",
                "title": "Fix bug",
                "amount": 100.0,
                "language": "Python",
                "labels": []
            },
            "expected": True,
            "reason": "Valid Python bounty ($100)"
        },
        {
            "bounty": {
                "id": "2",
                "title": "Feature request",
                "amount": 30.0,
                "language": "Python",
                "labels": []
            },
            "expected": False,
            "reason": "Below minimum bounty ($30 < $50)"
        },
        {
            "bounty": {
                "id": "3",
                "title": "Discussion needed",
                "amount": 100.0,
                "language": "Go",
                "labels": ["Needs Discussion"]
            },
            "expected": False,
            "reason": "Excluded label"
        },
        {
            "bounty": {
                "id": "4",
                "title": "TypeScript issue",
                "amount": 75.0,
                "language": "TypeScript",
                "labels": []
            },
            "expected": True,
            "reason": "Valid TypeScript bounty ($75)"
        }
    ]
    
    passed = 0
    for i, test in enumerate(test_cases, 1):
        result = monitor._matches_filters(test["bounty"])
        status = "✓" if result == test["expected"] else "✗"
        if result == test["expected"]:
            passed += 1
        print(f"{status} Case {i}: {test['reason']} (got {result}, expected {test['expected']})")
    
    return passed == len(test_cases)


def test_bounty_amount_extraction():
    """Test bounty amount extraction from GitHub issues"""
    print("\n🧪 Test 4: Bounty Amount Extraction")
    
    monitor = IssueMonitor()
    
    test_cases = [
        {
            "text": "Bug Bounty: $150 for fixing this issue",
            "expected": 150.0,
            "desc": "Simple dollar format"
        },
        {
            "text": "reward $1,000 for memory leak fix",
            "expected": 1000.0,
            "desc": "With comma separator"
        },
        {
            "text": "bounty 50 dollars",
            "expected": 50.0,
            "desc": "Without dollar sign"
        },
        {
            "text": "No bounty mentioned here",
            "expected": 0.0,
            "desc": "No bounty"
        }
    ]
    
    passed = 0
    for test in test_cases:
        issue_mock = {
            "body": test["text"],
            "title": ""
        }
        result = monitor._extract_bounty_amount(issue_mock)
        status = "✓" if result == test["expected"] else "✗"
        print(f"{status} {test['desc']}: ${result}")
        if result == test["expected"]:
            passed += 1
    
    return passed == len(test_cases)


def test_cache_operations():
    """Test cache save and load"""
    print("\n🧪 Test 5: Cache Operations")
    
    monitor = IssueMonitor()
    
    # Create test issues
    test_issues = [
        BountyIssue(
            id="test-001",
            title="Issue 1",
            description="Test issue 1",
            repository="org/repo1",
            repository_url="https://github.com/org/repo1",
            issue_url="https://github.com/org/repo1/issues/1",
            bounty_amount=100.0,
            language="Python",
            source="algora",
            created_at=datetime.now()
        ),
        BountyIssue(
            id="test-002",
            title="Issue 2",
            description="Test issue 2",
            repository="org/repo2",
            repository_url="https://github.com/org/repo2",
            issue_url="https://github.com/org/repo2/issues/2",
            bounty_amount=50.0,
            language="TypeScript",
            source="github",
            created_at=datetime.now()
        )
    ]
    
    # Save cache
    monitor.save_cache(test_issues)
    print(f"✓ Saved {len(test_issues)} issues to cache")
    
    # Load cache
    loaded_issues = monitor.load_cache()
    print(f"✓ Loaded {len(loaded_issues)} issues from cache")
    
    # Verify content
    if len(loaded_issues) == len(test_issues):
        print(f"✓ Cache content matches")
        return True
    else:
        print(f"✗ Cache content mismatch: expected {len(test_issues)}, got {len(loaded_issues)}")
        return False


def test_github_searches_labels_independently():
    """GitHub does not support OR between label qualifiers."""
    monitor = IssueMonitor()
    monitor.config['github']['token'] = 'test-token'
    response = MagicMock()
    response.json.return_value = {'items': []}

    with patch('bounty_bot.src.monitor.requests.get', return_value=response) as get:
        assert monitor.poll_github_api() == []

    assert [call.kwargs['params']['q'] for call in get.call_args_list] == [
        'is:issue is:open label:bounty',
        'is:issue is:open label:bug-bounty',
        'is:issue is:open label:"good first issue"',
    ]


def test_algora_poll_is_disabled_by_default():
    monitor = IssueMonitor()
    monitor.config['algora']['enabled'] = False

    with patch('bounty_bot.src.monitor.requests.get') as get:
        assert monitor.poll_algora_api() == []

    get.assert_not_called()


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("🚀 Running Monitor Module Tests (Phase 2)")
    print("=" * 60)
    
    tests = [
        ("BountyIssue Model", test_bounty_issue_model),
        ("Monitor Initialization", test_monitor_initialization),
        ("Filter Logic", test_filter_logic),
        ("Bounty Extraction", test_bounty_amount_extraction),
        ("Cache Operations", test_cache_operations),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Test '{name}' raised exception: {e}", exc_info=True)
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print(f"\n{'✨ All tests passed!' if passed == total else f'⚠️  {passed}/{total} tests passed'}")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
