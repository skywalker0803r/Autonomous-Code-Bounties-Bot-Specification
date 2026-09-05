#!/usr/bin/env python3
"""
Test script for Phase 4: LLM Solver Module
Tests the LLMSolver class with mock API responses
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock, Mock
import tempfile

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bounty_bot.src.solver import (
    LLMSolver,
    SolverConfig,
    PatchResult,
    CodeContext,
    CodeSnippet,
    StackTrace
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Test Helper Functions
# ============================================================================

def create_mock_code_context() -> CodeContext:
    """Create a mock CodeContext for testing"""
    return CodeContext(
        issue_id="issue-123",
        repository="tensorflow/tensorflow",
        repository_url="https://github.com/tensorflow/tensorflow",
        language="Python",
        stack_traces=[
            StackTrace(
                file_path="tensorflow/python/keras/layers/dense.py",
                function_name="Dense.__call__",
                line_number=145,
                code_line="    weights = self._build_weights(input_shape)",
                error_message="Memory leak in weight initialization"
            )
        ],
        code_snippets=[
            CodeSnippet(
                file_path="tensorflow/python/keras/layers/dense.py",
                start_line=140,
                end_line=150,
                content="""def __call__(self, inputs):
    if not self.built:
        self.build(inputs.shape)
    weights = self._build_weights(input_shape)
    return tf.matmul(inputs, weights)""",
                language="python",
                relevance_score=0.95,
                context="Main layer computation logic"
            )
        ],
        related_files=["tensorflow/python/keras/layers/dense.py"],
        summary="Memory leak in Dense layer weight initialization",
        extracted_at=datetime.now(),
        repository_branch="main",
        clone_size_mb=1234.5
    )


def create_mock_patch_diff() -> str:
    """Create a mock unified diff"""
    return """--- a/tensorflow/python/keras/layers/dense.py
+++ b/tensorflow/python/keras/layers/dense.py
@@ -140,12 +140,13 @@
 
 def __call__(self, inputs):
     if not self.built:
         self.build(inputs.shape)
-    weights = self._build_weights(input_shape)
+    weights = self._get_cached_weights(input_shape)
     return tf.matmul(inputs, weights)
 
-def _build_weights(self, shape):
+def _get_cached_weights(self, shape):
     # Properly cache weights to avoid memory leak
     if not hasattr(self, '_weight_cache'):
         self._weight_cache = {}
+    # Clear stale cache entries
     return self._weight_cache.get(shape)
"""


# ============================================================================
# Phase 4 Tests
# ============================================================================

def test_patch_result_model():
    """Test PatchResult data model"""
    print("\n🧪 Test 1: PatchResult Model")
    
    result = PatchResult(
        issue_id="issue-123",
        solver_id="solver-abc123",
        original_code="def func(): pass",
        patched_code="def func(): return None",
        diff=create_mock_patch_diff(),
        files_affected=["tensorflow/python/keras/layers/dense.py"],
        changes_summary="Fixed memory leak in weight initialization",
        patch_size_bytes=512,
        confidence_score=0.85,
        generated_at=datetime.now(),
        model_used="gemini-2.5-pro",
        prompt_tokens=2048,
        completion_tokens=512
    )
    
    print(f"✓ Created PatchResult")
    print(f"  Issue: {result.issue_id}")
    print(f"  Files affected: {result.files_affected}")
    print(f"  Confidence: {result.confidence_score:.2f}")
    print(f"  Tokens: {result.prompt_tokens} prompt, {result.completion_tokens} completion")
    
    # Test JSON serialization
    json_data = result.model_dump()
    print(f"✓ Serialized to JSON successfully")
    
    assert result.confidence_score >= 0.0 and result.confidence_score <= 1.0
    assert len(result.diff) > 0
    print("✅ PASS - PatchResult Model\n")
    return True


def test_solver_config():
    """Test SolverConfig data model"""
    print("\n🧪 Test 2: SolverConfig Model")
    
    config = SolverConfig(
        model="gemini-2.5-pro",
        temperature=0.7,
        max_tokens=4096,
        timeout_seconds=60
    )
    
    print(f"✓ Created SolverConfig")
    print(f"  Model: {config.model}")
    print(f"  Temperature: {config.temperature}")
    print(f"  Max tokens: {config.max_tokens}")
    
    # Test defaults
    default_config = SolverConfig()
    assert default_config.temperature == 0.7
    print(f"✓ Default config values work correctly")
    
    print("✅ PASS - SolverConfig Model\n")
    return True


def test_gemini_generation_config_uses_supported_fields():
    with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
        solver = LLMSolver()
        solver.model = MagicMock()
        solver.model.generate_content.return_value = MagicMock(text="response")

        assert solver._call_gemini_api("system", "user") == "response"

    generation_config = solver.model.generate_content.call_args.kwargs['generation_config']
    assert generation_config.temperature == solver.config.temperature
    assert generation_config.max_output_tokens == solver.config.max_tokens
    assert not hasattr(generation_config, 'timeout')


def test_diff_parsing():
    """Test unified diff parsing"""
    print("\n🧪 Test 3: Diff Parsing")
    
    with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
        solver = LLMSolver()
        
        diff = create_mock_patch_diff()
        files = solver._parse_diff(diff)
        
        print(f"✓ Parsed diff successfully")
        print(f"  Files affected: {files}")
        
        assert len(files) == 1
        assert files[0] == "tensorflow/python/keras/layers/dense.py"
        
        print("✅ PASS - Diff Parsing\n")
        return True


def test_system_prompt_generation():
    """Test system prompt generation"""
    print("\n🧪 Test 4: System Prompt Generation")
    
    with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
        solver = LLMSolver()
        
        prompt = solver._build_system_prompt()
        
        print(f"✓ Generated system prompt ({len(prompt)} chars)")
        assert "open-source" in prompt.lower()
        assert "bug fix" in prompt.lower() or "patch" in prompt.lower()
        assert "unified diff" in prompt.lower()
        
        print(f"  Key phrases present ✓")
        print("✅ PASS - System Prompt Generation\n")
        return True


def test_user_prompt_generation():
    """Test user prompt generation"""
    print("\n🧪 Test 5: User Prompt Generation")
    
    with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
        solver = LLMSolver()
        code_context = create_mock_code_context()
        
        prompt = solver._build_user_prompt(
            issue_id="issue-123",
            issue_title="Fix memory leak in Layer API",
            issue_description="There's a memory leak when...",
            code_context=code_context
        )
        
        print(f"✓ Generated user prompt ({len(prompt)} chars)")
        assert "issue-123" in prompt
        assert "tensorflow/tensorflow" in prompt
        assert "Stack Traces:" in prompt
        assert "Code Snippets:" in prompt
        
        print(f"  Issue info included ✓")
        print(f"  Stack traces included ✓")
        print(f"  Code snippets included ✓")
        print("✅ PASS - User Prompt Generation\n")
        return True


def test_extract_diff_from_response():
    """Test diff extraction from API response"""
    print("\n🧪 Test 6: Diff Extraction from Response")
    
    with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
        solver = LLMSolver()
        
        response = """Explanation: Fixed the memory leak by implementing proper weight caching.

--- a/tensorflow/python/keras/layers/dense.py
+++ b/tensorflow/python/keras/layers/dense.py
@@ -140,7 +140,7 @@
 
 def __call__(self, inputs):
     if not self.built:
         self.build(inputs.shape)
-    weights = self._build_weights(input_shape)
+    weights = self._get_cached_weights(input_shape)
     return tf.matmul(inputs, weights)"""
        
        diff = solver._extract_diff_from_response(response)
        
        print(f"✓ Extracted diff from response ({len(diff)} chars)")
        assert "---" in diff
        assert "+++" in diff
        
        print(f"  Diff markers present ✓")
        print("✅ PASS - Diff Extraction\n")
        return True


def test_confidence_scoring():
    """Test confidence score calculation"""
    print("\n🧪 Test 7: Confidence Score Calculation")
    
    with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
        solver = LLMSolver()
        
        # Test various diff sizes
        test_cases = [
            (create_mock_patch_diff(), 1, "Small, single-file patch"),
            (create_mock_patch_diff() * 3, 3, "Medium, multi-file patch"),
            ("--- a/file1\n+++ b/file1\n@@ -1,1 +1,1 @@\n-old\n+new", 1, "Tiny patch"),
        ]
        
        for diff, num_files, description in test_cases:
            score = solver._calculate_confidence_score(diff, num_files)
            print(f"  {description}: {score:.2f}")
            assert 0.0 <= score <= 1.0
        
        print(f"✓ All confidence scores valid")
        print("✅ PASS - Confidence Scoring\n")
        return True


def test_patch_result_serialization():
    """Test PatchResult serialization and deserialization"""
    print("\n🧪 Test 8: Patch Result Serialization")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
            solver = LLMSolver()
            
            # Create original result
            original = PatchResult(
                issue_id="issue-123",
                solver_id="solver-abc123",
                original_code="def func(): pass",
                patched_code="def func(): return None",
                diff=create_mock_patch_diff(),
                files_affected=["file.py"],
                changes_summary="Fixed bug",
                patch_size_bytes=256,
                confidence_score=0.85,
                generated_at=datetime.now(),
                model_used="gemini-2.5-pro",
                prompt_tokens=2048,
                completion_tokens=512
            )
            
            # Save to file
            output_path = os.path.join(tmpdir, "result.json")
            solver.save_result(original, output_path)
            print(f"✓ Saved PatchResult to {output_path}")
            
            # Load from file
            loaded = solver.load_result(output_path)
            print(f"✓ Loaded PatchResult from file")
            
            assert loaded.issue_id == original.issue_id
            assert loaded.confidence_score == original.confidence_score
            assert len(loaded.diff) == len(original.diff)
            
            print(f"✓ Serialization/deserialization matches")
            print("✅ PASS - Patch Result Serialization\n")
            return True


def test_code_context_handling():
    """Test CodeContext handling in solver"""
    print("\n🧪 Test 9: CodeContext Handling")
    
    with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
        solver = LLMSolver()
        code_context = create_mock_code_context()
        
        # Verify CodeContext structure
        assert code_context.issue_id == "issue-123"
        assert len(code_context.stack_traces) == 1
        assert len(code_context.code_snippets) == 1
        
        print(f"✓ CodeContext created successfully")
        print(f"  Stack traces: {len(code_context.stack_traces)}")
        print(f"  Code snippets: {len(code_context.code_snippets)}")
        print(f"  Related files: {len(code_context.related_files)}")
        
        # Test in prompt generation
        prompt = solver._build_user_prompt(
            "issue-123",
            "Fix bug",
            "Description",
            code_context
        )
        
        assert len(prompt) > 100
        print(f"✓ CodeContext integrated in prompt generation")
        print("✅ PASS - CodeContext Handling\n")
        return True


def test_solver_initialization():
    """Test LLMSolver initialization with config"""
    print("\n🧪 Test 10: LLMSolver Initialization")
    
    with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
        # Test with default config
        solver1 = LLMSolver()
        print(f"✓ Solver initialized with defaults")
        print(f"  Solver ID: {solver1.solver_id}")
        
        # Test with custom config
        config = SolverConfig(
            model="gemini-2.0",
            temperature=0.5,
            max_tokens=2048,
            timeout_seconds=30
        )
        solver2 = LLMSolver(config=config)
        print(f"✓ Solver initialized with custom config")
        print(f"  Model: {solver2.config.model}")
        print(f"  Temperature: {solver2.config.temperature}")
        
        print("✅ PASS - Solver Initialization\n")
        return True


# ============================================================================
# Main Test Runner
# ============================================================================

def run_all_tests():
    """Run all solver tests"""
    print("\n" + "="*60)
    print("🤖 PHASE 4: LLM SOLVER - UNIT TESTS")
    print("="*60)
    
    tests = [
        test_patch_result_model,
        test_solver_config,
        test_diff_parsing,
        test_system_prompt_generation,
        test_user_prompt_generation,
        test_extract_diff_from_response,
        test_confidence_scoring,
        test_patch_result_serialization,
        test_code_context_handling,
        test_solver_initialization,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
                print(f"✗ {test.__name__} failed")
        except Exception as e:
            failed += 1
            print(f"✗ {test.__name__} failed with exception: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("="*60)
    print(f"✨ Test Results: {passed} passed, {failed} failed")
    print("="*60)
    
    if failed == 0:
        print("🎉 All tests passed!")
        return True
    else:
        print(f"⚠️  {failed} test(s) failed")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
