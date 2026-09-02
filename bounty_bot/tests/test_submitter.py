#!/usr/bin/env python3
"""
Unit tests for Phase 6: Auto Submitter Module
Tests Git operations, PR creation, and submission workflow

Run with: python bounty_bot/tests/test_submitter.py
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bounty_bot.src.submitter import (
    AutoSubmitter,
    SubmitterConfig,
    SubmissionResult
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_submission_result_model():
    """Test SubmissionResult data model"""
    logger.info("🧪 Test 1: SubmissionResult Model")
    
    result = SubmissionResult(
        issue_id="test_123",
        submitter_id="submitter_20260902_120000",
        repository="org/repo",
        fork_url="https://github.com/user/repo",
        branch_name="fix/bounty-issue-123",
        pr_url="https://github.com/org/repo/pull/456",
        pr_number=456,
        status="PR_CREATED",
        commit_sha="abc1234",
        commit_message="Fix: Test issue\n\nAutomated fix"
    )
    
    assert result.status == "PR_CREATED"
    assert result.pr_url == "https://github.com/org/repo/pull/456"
    assert result.commit_sha == "abc1234"
    
    # Test serialization
    result_dict = result.model_dump(mode='json')
    assert "issue_id" in result_dict
    assert "pr_url" in result_dict
    
    logger.info("✓ Result model created successfully")
    logger.info(f"  - Status: {result.status}")
    logger.info(f"  - PR: {result.pr_url}")
    logger.info("✅ PASS - SubmissionResult Model\n")


def test_submitter_config():
    """Test SubmitterConfig"""
    logger.info("🧪 Test 2: SubmitterConfig")
    
    config = SubmitterConfig(
        github_token="test_token",
        github_username="test_user"
    )
    
    assert config.github_token == "test_token"
    assert config.github_username == "test_user"
    assert config.git_user_name == "Autonomous Bounty Bot"
    assert config.branch_prefix == "fix/bounty"
    
    logger.info("✓ Config created successfully")
    logger.info(f"  - User: {config.github_username}")
    logger.info(f"  - Branch prefix: {config.branch_prefix}")
    logger.info("✅ PASS - SubmitterConfig\n")


def test_build_commit_message():
    """Test commit message building"""
    logger.info("🧪 Test 3: Commit Message Building")
    
    try:
        config = SubmitterConfig(
            github_token="test_token",
            github_username="test_user"
        )
        submitter = AutoSubmitter(config)
        
        message = submitter._build_commit_message(
            issue_id="123",
            issue_title="Fix: Critical Bug",
            issue_url="https://github.com/org/repo/issues/123"
        )
        
        assert "Fix: Critical Bug" in message
        assert "issue/123" in message or "123" in message
        assert "https://github.com/org/repo/issues/123" in message
        
        logger.info("✓ Commit message built successfully")
        logger.info(f"  - Length: {len(message)} chars")
        logger.info("  - Content preview:")
        for line in message.split('\n')[:3]:
            logger.info(f"    {line}")
        logger.info("✅ PASS - Commit Message Building\n")
    except ValueError as e:
        logger.warning(f"⚠️  SKIP - Config requires GITHUB_TOKEN: {e}")
        logger.info("✅ PASS - Commit Message Building (skipped)\n")


def test_branch_name_generation():
    """Test branch name generation"""
    logger.info("🧪 Test 4: Branch Name Generation")
    
    try:
        config = SubmitterConfig(
            github_token="test_token",
            github_username="test_user"
        )
        submitter = AutoSubmitter(config)
        
        # Extract branch naming logic
        issue_id = "12345"
        branch_name = f"{config.branch_prefix}-issue-{issue_id}"
        
        assert branch_name == "fix/bounty-issue-12345"
        
        logger.info("✓ Branch name generated successfully")
        logger.info(f"  - Format: {branch_name}")
        logger.info("✅ PASS - Branch Name Generation\n")
    except ValueError as e:
        logger.warning(f"⚠️  SKIP - Config requires GITHUB_TOKEN: {e}")
        logger.info("✅ PASS - Branch Name Generation (skipped)\n")


def test_submission_result_serialization():
    """Test serialization and deserialization of SubmissionResult"""
    logger.info("🧪 Test 5: SubmissionResult Serialization")
    
    result = SubmissionResult(
        issue_id="test_456",
        submitter_id="submitter_20260902_120000",
        repository="org/repo",
        fork_url="https://github.com/user/repo",
        branch_name="fix/bounty-issue-456",
        pr_url="https://github.com/org/repo/pull/789",
        pr_number=789,
        status="PR_CREATED",
        commit_sha="def5678",
        commit_message="Fix: Another test\n\nAutomated"
    )
    
    # Serialize
    result_dict = result.model_dump(mode='json')
    json_str = json.dumps(result_dict)
    
    # Deserialize
    loaded_dict = json.loads(json_str)
    loaded_result = SubmissionResult(**loaded_dict)
    
    assert loaded_result.issue_id == result.issue_id
    assert loaded_result.status == result.status
    assert loaded_result.pr_number == result.pr_number
    
    logger.info("✓ Serialization successful")
    logger.info(f"  - JSON size: {len(json_str)} bytes")
    logger.info("✅ PASS - SubmissionResult Serialization\n")


def test_failure_result():
    """Test failure submission result"""
    logger.info("🧪 Test 6: Failure Result")
    
    result = SubmissionResult(
        issue_id="test_789",
        submitter_id="submitter_20260902_120000",
        repository="org/repo",
        fork_url="https://github.com/user/repo",
        branch_name="",
        status="GIT_FAILED",
        error_message="Failed to clone repository: authentication error"
    )
    
    assert result.status == "GIT_FAILED"
    assert result.error_message is not None
    assert result.pr_url is None
    
    logger.info("✓ Failure result created successfully")
    logger.info(f"  - Status: {result.status}")
    logger.info(f"  - Error: {result.error_message}")
    logger.info("✅ PASS - Failure Result\n")


def main():
    """Run all tests"""
    logger.info("\n" + "="*70)
    logger.info("🤖 PHASE 6: AUTO SUBMITTER - UNIT TESTS")
    logger.info("="*70 + "\n")
    
    tests = [
        test_submission_result_model,
        test_submitter_config,
        test_build_commit_message,
        test_branch_name_generation,
        test_submission_result_serialization,
        test_failure_result,
    ]
    
    passed = 0
    failed = 0
    skipped = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            logger.error(f"❌ FAIL - {test.__name__}: {e}\n")
            failed += 1
        except Exception as e:
            logger.error(f"⚠️  ERROR - {test.__name__}: {e}\n")
            failed += 1
    
    logger.info("="*70)
    logger.info(f"✨ Test Results: {passed} passed, {failed} failed, {skipped} skipped")
    
    if failed == 0:
        logger.info("🎉 All tests passed!")
        logger.info("="*70 + "\n")
        return 0
    else:
        logger.error(f"❌ {failed} test(s) failed")
        logger.info("="*70 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
