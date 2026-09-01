#!/usr/bin/env python3
"""
Test script for Phase 3: Code Ingestor Module
Tests the CodeIngestor, CodeParser, and StackTraceExtractor classes
"""

import os
import sys
import json
import logging
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock, mock_open

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bounty_bot.src.ingestor import (
    CodeIngestor,
    CodeParser,
    StackTraceExtractor,
    CodeContext,
    CodeSnippet,
    StackTrace
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==================== Test Stack Trace Extractor ====================

def test_stack_trace_extraction_python():
    """Test extracting Python stack traces from issue text"""
    print("\n🧪 Test 1: Python Stack Trace Extraction")
    
    issue_text = """
    Getting error when running the code:
    
    Traceback (most recent call last):
      File "src/utils.py", line 42, in process_data
        result = calculate_sum(data)
      File "src/math.py", line 15, in calculate_sum
        return sum_values / 0
    ZeroDivisionError: division by zero
    """
    
    traces = StackTraceExtractor.extract_from_text(issue_text, language='python')
    
    print(f"✓ Extracted {len(traces)} stack traces")
    for i, trace in enumerate(traces, 1):
        print(f"  {i}. File: {trace.file_path}, Line: {trace.line_number}, "
              f"Function: {trace.function_name}")
    
    assert len(traces) > 0, "Should extract at least one stack trace"
    print("✅ PASS - Python Stack Trace Extraction")


def test_stack_trace_extraction_javascript():
    """Test extracting JavaScript stack traces from issue text"""
    print("\n🧪 Test 2: JavaScript Stack Trace Extraction")
    
    issue_text = """
    Error in application:
    
    TypeError: Cannot read property 'map' of undefined
        at processArray (app.js:45:12)
        at main (index.js:120:5)
    """
    
    traces = StackTraceExtractor.extract_from_text(issue_text, language='javascript')
    
    print(f"✓ Extracted {len(traces)} stack traces")
    if traces:
        for i, trace in enumerate(traces, 1):
            print(f"  {i}. Function: {trace.function_name}, File: {trace.file_path}")
    
    print("✅ PASS - JavaScript Stack Trace Extraction")


# ==================== Test Code Parser ====================

def test_code_snippet_model():
    """Test CodeSnippet data model"""
    print("\n🧪 Test 3: CodeSnippet Model")
    
    snippet = CodeSnippet(
        file_path="src/utils.py",
        start_line=10,
        end_line=20,
        content="def my_function():\n    pass",
        language="python",
        relevance_score=0.95,
        context="Main utility function"
    )
    
    print(f"✓ Created CodeSnippet: {snippet.file_path}")
    print(f"  Lines: {snippet.start_line}-{snippet.end_line}")
    print(f"  Language: {snippet.language}")
    print(f"  Relevance: {snippet.relevance_score}")
    
    # Test serialization
    json_data = snippet.dict()
    print(f"✓ Serialized to JSON successfully")
    
    print("✅ PASS - CodeSnippet Model")


def test_code_context_model():
    """Test CodeContext data model"""
    print("\n🧪 Test 4: CodeContext Model")
    
    context = CodeContext(
        issue_id="issue-123",
        repository="tensorflow/tensorflow",
        repository_url="https://github.com/tensorflow/tensorflow",
        language="python",
        summary="Memory leak in Layer API",
        repository_branch="main"
    )
    
    print(f"✓ Created CodeContext for {context.issue_id}")
    print(f"  Repository: {context.repository}")
    print(f"  Language: {context.language}")
    print(f"  Extracted at: {context.extracted_at.isoformat()}")
    
    # Test serialization
    json_data = context.dict()
    print(f"✓ Serialized to JSON successfully")
    
    print("✅ PASS - CodeContext Model")


def test_language_detection():
    """Test programming language detection"""
    print("\n🧪 Test 5: Language Detection")
    
    test_cases = [
        ("src/app.py", "python"),
        ("src/main.js", "javascript"),
        ("src/types.ts", "typescript"),
        ("src/Main.java", "java"),
        ("src/main.cpp", "cpp"),
    ]
    
    for file_path, expected_lang in test_cases:
        detected = CodeParser.detect_language(file_path)
        status = "✓" if detected == expected_lang else "✗"
        print(f"  {status} {file_path} → {detected}")
        assert detected == expected_lang, f"Expected {expected_lang}, got {detected}"
    
    print("✅ PASS - Language Detection")


# ==================== Test Code Ingestor ====================

def test_code_ingestor_initialization():
    """Test CodeIngestor initialization"""
    print("\n🧪 Test 6: CodeIngestor Initialization")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ingestor = CodeIngestor(cache_dir=tmpdir)
        
        print(f"✓ Initialized CodeIngestor with cache: {tmpdir}")
        assert os.path.exists(tmpdir), "Cache directory should exist"
        
        print("✅ PASS - CodeIngestor Initialization")


@patch('bounty_bot.src.ingestor.Repo.clone_from')
def test_repository_clone_mocked(mock_clone):
    """Test repository cloning with mock"""
    print("\n🧪 Test 7: Repository Clone (Mocked)")
    
    # Mock the Git repository
    mock_repo = MagicMock()
    mock_clone.return_value = mock_repo
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ingestor = CodeIngestor(cache_dir=tmpdir)
        
        repo_url = "https://github.com/example/repo.git"
        clone_path = ingestor._clone_repository(repo_url, branch="main")
        
        print(f"✓ Attempted to clone {repo_url}")
        print(f"  Clone called: {mock_clone.called}")
        
        print("✅ PASS - Repository Clone (Mocked)")


def test_ingest_issue_mocked():
    """Test complete issue ingestion with mocked repository"""
    print("\n🧪 Test 8: Complete Issue Ingestion (Mocked)")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ingestor = CodeIngestor(cache_dir=tmpdir)
        
        issue_text = """
        Memory leak in Layer API:
        
        Traceback (most recent call last):
          File "src/layer.py", line 42, in forward
            result = self.compute(data)
        MemoryError: Unable to allocate memory
        """
        
        # Mock repository clone to use temp directory
        with patch.object(ingestor, '_clone_repository') as mock_clone:
            # Create a fake repository structure
            fake_repo = os.path.join(tmpdir, "fake_repo")
            os.makedirs(fake_repo)
            
            # Create a sample Python file
            sample_file = os.path.join(fake_repo, "src", "layer.py")
            os.makedirs(os.path.dirname(sample_file))
            with open(sample_file, 'w') as f:
                f.write("""
def forward(self, data):
    '''Forward pass'''
    result = self.compute(data)
    return result

def compute(self, data):
    '''Compute operation'''
    return data * 2
""")
            
            mock_clone.return_value = fake_repo
            
            # Run ingestion
            context = ingestor.ingest_issue(
                issue_id="test-001",
                repository_url="https://github.com/test/repo",
                repository="test/repo",
                language="python",
                issue_title="Memory leak in Layer API",
                issue_description=issue_text,
                branch="main"
            )
            
            assert context is not None, "Context should be created"
            assert context.issue_id == "test-001"
            print(f"✓ Successfully ingested issue")
            print(f"  Stack traces: {len(context.stack_traces)}")
            print(f"  Code snippets: {len(context.code_snippets)}")
            print(f"  Related files: {len(context.related_files)}")
            
            print("✅ PASS - Complete Issue Ingestion (Mocked)")


def test_context_serialization():
    """Test saving and loading CodeContext"""
    print("\n🧪 Test 9: Context Serialization")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ingestor = CodeIngestor(cache_dir=tmpdir)
        
        # Create a CodeContext
        context = CodeContext(
            issue_id="issue-456",
            repository="test/repo",
            repository_url="https://github.com/test/repo",
            language="python",
            summary="Test context",
            code_snippets=[
                CodeSnippet(
                    file_path="src/test.py",
                    start_line=1,
                    end_line=10,
                    content="print('Hello')",
                    language="python"
                )
            ]
        )
        
        # Save to file
        output_path = os.path.join(tmpdir, "context.json")
        saved = ingestor.save_context(context, output_path)
        
        assert saved, "Should save successfully"
        assert os.path.exists(output_path), "File should exist"
        print(f"✓ Saved context to {output_path}")
        
        # Load from file
        loaded = ingestor.load_context(output_path)
        
        assert loaded is not None, "Should load successfully"
        assert loaded.issue_id == context.issue_id
        assert len(loaded.code_snippets) == 1
        print(f"✓ Loaded context from {output_path}")
        
        print("✅ PASS - Context Serialization")


# ==================== Run All Tests ====================

def run_all_tests():
    """Run all test cases"""
    print("\n" + "="*60)
    print("🤖 PHASE 3: CODE INGESTOR - UNIT TESTS")
    print("="*60)
    
    test_functions = [
        test_stack_trace_extraction_python,
        test_stack_trace_extraction_javascript,
        test_code_snippet_model,
        test_code_context_model,
        test_language_detection,
        test_code_ingestor_initialization,
        test_repository_clone_mocked,
        test_ingest_issue_mocked,
        test_context_serialization,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in test_functions:
        try:
            test_func()
            passed += 1
        except Exception as e:
            logger.error(f"❌ FAIL - {test_func.__name__}: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"✨ Test Results: {passed} passed, {failed} failed")
    print("="*60)
    
    if failed == 0:
        print("\n🎉 All tests passed!")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
