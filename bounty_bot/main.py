#!/usr/bin/env python3
"""
Autonomous Code Bounties Bot - Main Entry Point & Orchestrator
Phase 7: Complete End-to-End Automation

Workflow:
Phase 2: Monitor → Find bounty issues
Phase 3: Ingest → Extract code context
Phase 4: Solve → Generate patches with LLM
Phase 5: Test → Validate in Docker sandbox
Phase 6: Submit → Auto-create PR
Phase 7: Orchestrate → Coordinate full pipeline

Author: Autonomous Code Bounties Bot
"""

import argparse
import logging
import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from bounty_bot.src.monitor import IssueMonitor, BountyIssue
from bounty_bot.src.ingestor import CodeIngestor
from bounty_bot.src.solver import LLMSolver, SolverConfig
from bounty_bot.src.tester import DockerTester, TesterConfig
from bounty_bot.src.submitter import AutoSubmitter, SubmitterConfig

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BountyBot:
    """
    Complete bounty bot orchestrator - Phase 2-7
    
    Phases:
    - Phase 2: Monitor - Find bounty issues
    - Phase 3: Ingest - Extract code context
    - Phase 4: Solve - Generate patches
    - Phase 5: Test - Validate patches
    - Phase 6: Submit - Create PRs
    - Phase 7: Orchestrate - Coordinate workflow
    """

    def __init__(
        self,
        config_path: str = "bounty_bot/config/settings.yaml",
        phases: str = "2-3",  # e.g., "2-3", "2-7", "4-6"
        dry_run: bool = False
    ):
        """
        Initialize the bounty bot with specified phases
        
        Args:
            config_path: Path to settings.yaml
            phases: Phase range to enable (e.g., "2-3", "2-7")
            dry_run: Run all enabled phases except PR submission
        """
        self.config_path = config_path
        self.phases = phases
        self.dry_run = dry_run
        
        # Initialize modules
        self.monitor = IssueMonitor(config_path)
        self.ingestor = CodeIngestor()
        self.solver = None
        self.tester = None
        self.submitter = None
        
        # Initialize Phase 4-6 if enabled
        phase_start, phase_end = map(int, phases.split('-'))
        
        if phase_end >= 4:
            try:
                self.solver = LLMSolver(SolverConfig())
                logger.info("✓ Phase 4 (Solver) initialized")
            except Exception as e:
                logger.warning(f"Phase 4 (Solver) initialization failed: {e}")
        
        if phase_end >= 5:
            try:
                self.tester = DockerTester(TesterConfig())
                logger.info("✓ Phase 5 (Tester) initialized")
            except Exception as e:
                logger.warning(f"Phase 5 (Tester) initialization failed: {e}")
        
        if phase_end >= 6 and not self.dry_run:
            try:
                self.submitter = AutoSubmitter(SubmitterConfig())
                logger.info("✓ Phase 6 (Submitter) initialized")
            except Exception as e:
                logger.warning(f"Phase 6 (Submitter) initialization failed: {e}")
        elif phase_end >= 6:
            logger.info("Phase 6 (Submitter) skipped in dry-run mode")
        
        logger.info(
            f"🤖 Autonomous Code Bounties Bot initialized "
            f"(Phases {phases}, dry_run={self.dry_run})"
        )

    def run_single_poll(self) -> int:
        """
        Run single poll cycle (Phase 2 only)
        
        Returns:
            Number of new issues found
        """
        try:
            new_issues = self.monitor.run_poll_cycle()
            return len(new_issues)
        except Exception as e:
            logger.error(f"Error during poll cycle: {e}", exc_info=True)
            return 0

    def ingest_issues(self, issues: list) -> int:
        """
        Ingest code context for issues (Phase 3)
        
        Args:
            issues: List of BountyIssue objects
        
        Returns:
            Number of successfully ingested issues
        """
        logger.info(f"Starting code ingestion for {len(issues)} issues...")
        ingested_count = 0
        
        for issue in issues:
            try:
                logger.info(f"📥 Ingesting: {issue.title}")
                
                context = self.ingestor.ingest_issue(
                    issue_id=issue.id,
                    repository_url=issue.repository_url,
                    repository=issue.repository,
                    language=issue.language,
                    issue_title=issue.title,
                    issue_description=issue.description,
                    branch="main"
                )
                
                if context:
                    # Save context for Phase 4
                    cache_path = f"/tmp/bounty_cache/contexts/{issue.id}_context.json"
                    self.ingestor.save_context(context, cache_path)
                    ingested_count += 1
                    logger.info(f"✓ Ingested")
                else:
                    logger.warning(f"✗ Failed to ingest")
            
            except Exception as e:
                logger.error(f"Error ingesting {issue.id}: {e}", exc_info=True)
        
        logger.info(f"Code ingestion completed: {ingested_count}/{len(issues)} successful")
        return ingested_count

    def solve_patches(self, issues: list) -> dict:
        """
        Generate patches using LLM (Phase 4)
        
        Args:
            issues: List of BountyIssue objects
        
        Returns:
            Dict mapping issue_id -> PatchResult
        """
        if not self.solver:
            logger.warning("Phase 4 (Solver) not initialized")
            return {}
        
        logger.info(f"Starting patch generation for {len(issues)} issues...")
        patches = {}
        
        for issue in issues:
            try:
                logger.info(f"🧠 Solving: {issue.title}")
                
                # Load ingested context
                context_path = f"/tmp/bounty_cache/contexts/{issue.id}_context.json"
                if not Path(context_path).exists():
                    logger.warning(f"Context not found for {issue.id}, skipping")
                    continue
                
                context = self.ingestor.load_context(context_path)
                
                # Generate patch
                patch_result = self.solver.solve_issue(issue, context)
                
                if patch_result:
                    patches[issue.id] = patch_result
                    # Save patch
                    patch_path = f"/tmp/bounty_cache/patches/{issue.id}_patch.json"
                    Path(patch_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(patch_path, "w") as f:
                        json.dump(patch_result.dict(default=str), f, indent=2)
                    logger.info(f"✓ Patch generated (confidence: {patch_result.confidence_score:.2f})")
                else:
                    logger.warning(f"✗ Failed to generate patch")
            
            except Exception as e:
                logger.error(f"Error solving {issue.id}: {e}", exc_info=True)
        
        logger.info(f"Patch generation completed: {len(patches)}/{len(issues)} successful")
        return patches

    def test_patches(self, issues: list, repo_paths: dict) -> dict:
        """
        Test patches in Docker sandbox (Phase 5)
        
        Args:
            issues: List of BountyIssue objects
            repo_paths: Dict mapping issue_id -> repo_path
        
        Returns:
            Dict mapping issue_id -> TestResult
        """
        if not self.tester:
            logger.warning("Phase 5 (Tester) not initialized")
            return {}
        
        logger.info(f"Starting patch validation for {len(issues)} issues...")
        test_results = {}
        
        for issue in issues:
            try:
                repo_path = repo_paths.get(issue.id)
                if not repo_path:
                    logger.warning(f"Repo path not found for {issue.id}, skipping")
                    continue
                
                logger.info(f"🧪 Testing: {issue.title}")
                
                result = self.tester.run_tests(repo_path, build=True)
                test_results[issue.id] = result
                
                if result.status == "READY_FOR_PR":
                    logger.info(f"✓ Tests passed ({result.tests_passed} passed)")
                else:
                    logger.info(f"✗ Tests failed ({result.tests_failed} failed)")
            
            except Exception as e:
                logger.error(f"Error testing {issue.id}: {e}", exc_info=True)
        
        logger.info(f"Patch testing completed: {len(test_results)}/{len(issues)} tested")
        return test_results

    def submit_patches(self, issues: list, test_results: dict) -> dict:
        """
        Submit validated patches as PRs (Phase 6)
        
        Args:
            issues: List of BountyIssue objects
            test_results: Dict mapping issue_id -> TestResult
        
        Returns:
            Dict mapping issue_id -> SubmissionResult
        """
        if not self.submitter:
            logger.warning("Phase 6 (Submitter) not initialized")
            return {}
        
        logger.info(f"Starting PR submission for {len(issues)} issues...")
        submissions = {}
        
        for issue in issues:
            try:
                test_result = test_results.get(issue.id)
                if not test_result or test_result.status != "READY_FOR_PR":
                    logger.warning(f"Issue {issue.id} not ready for PR, skipping")
                    continue
                
                logger.info(f"📤 Submitting: {issue.title}")
                
                # Load patch
                patch_path = f"/tmp/bounty_cache/patches/{issue.id}_patch.json"
                if not Path(patch_path).exists():
                    logger.warning(f"Patch not found for {issue.id}, skipping")
                    continue
                
                with open(patch_path, "r") as f:
                    patch_data = json.load(f)
                
                # Submit
                result = self.submitter.submit_patch(
                    issue_id=issue.id,
                    issue_title=issue.title,
                    repository_url=issue.repository_url,
                    repository=issue.repository,
                    patch_content=patch_data["diff"],
                    issue_url=issue.issue_url
                )
                
                submissions[issue.id] = result
                
                if result.status == "PR_CREATED":
                    logger.info(f"✓ PR created: {result.pr_url}")
                else:
                    logger.warning(f"✗ Submission failed: {result.error_message}")
            
            except Exception as e:
                logger.error(f"Error submitting {issue.id}: {e}", exc_info=True)
        
        logger.info(f"PR submission completed: {len(submissions)}/{len(issues)} submitted")
        return submissions

    def run_full_pipeline(self) -> dict:
        """
        Run complete end-to-end pipeline (Phase 2-7)
        
        Returns:
            Dict with statistics and results
        """
        logger.info("="*70)
        logger.info("🚀 STARTING FULL PIPELINE (Phase 2-7)")
        logger.info("="*70)
        
        start_time = datetime.now()
        stats = {
            'timestamp': start_time.isoformat(),
            'phases': self.phases,
            'phase_2': {'found': 0},
            'phase_3': {'ingested': 0},
            'phase_4': {'patched': 0},
            'phase_5': {'tested': 0, 'ready': 0},
            'phase_6': {'submitted': 0, 'success': 0, 'skipped': self.dry_run},
            'total_time_seconds': 0
        }
        
        try:
            # Phase 2: Monitor
            logger.info("\n📡 Phase 2: Monitoring for bounty issues...")
            new_issues = self.monitor.run_poll_cycle()
            stats['phase_2']['found'] = len(new_issues)
            logger.info(f"Found {len(new_issues)} new issues\n")
            
            if not new_issues:
                logger.info("No new issues found, skipping remaining phases")
                stats['total_time_seconds'] = (datetime.now() - start_time).total_seconds()
                return stats
            
            # Phase 3: Ingest
            logger.info("🔍 Phase 3: Extracting code context...")
            ingested_count = self.ingest_issues(new_issues)
            stats['phase_3']['ingested'] = ingested_count
            logger.info(f"Ingested {ingested_count}/{len(new_issues)} issues\n")
            
            if ingested_count == 0:
                logger.warning("No issues ingested, skipping remaining phases")
                stats['total_time_seconds'] = (datetime.now() - start_time).total_seconds()
                return stats
            
            # Phase 4: Solve
            if self.solver:
                logger.info("🧠 Phase 4: Generating patches...")
                patches = self.solve_patches(new_issues)
                stats['phase_4']['patched'] = len(patches)
                logger.info(f"Generated {len(patches)}/{len(new_issues)} patches\n")
                
                if not patches:
                    logger.warning("No patches generated, skipping remaining phases")
                    stats['total_time_seconds'] = (datetime.now() - start_time).total_seconds()
                    return stats
            else:
                logger.warning("Phase 4 not enabled, skipping")
            
            # Phase 5: Test
            if self.tester:
                logger.info("🧪 Phase 5: Testing patches...")
                # Prepare repo paths (using cache)
                repo_paths = {
                    issue.id: f"/tmp/bounty_cache/repos/{issue.id}"
                    for issue in new_issues
                }
                test_results = self.test_patches(new_issues, repo_paths)
                
                ready_count = sum(
                    1 for r in test_results.values()
                    if r.status == "READY_FOR_PR"
                )
                stats['phase_5']['tested'] = len(test_results)
                stats['phase_5']['ready'] = ready_count
                logger.info(f"Tested {len(test_results)}/{len(new_issues)} patches, {ready_count} ready for PR\n")
                
                if ready_count == 0:
                    logger.warning("No patches ready for PR, skipping submission")
                    stats['total_time_seconds'] = (datetime.now() - start_time).total_seconds()
                    return stats
            else:
                logger.warning("Phase 5 not enabled, skipping")
            
            # Phase 6: Submit
            if self.dry_run:
                logger.info("Phase 6 skipped: dry-run mode prevents PR submission")
            elif self.submitter:
                logger.info("📤 Phase 6: Submitting pull requests...")
                submissions = self.submit_patches(new_issues, test_results)
                
                success_count = sum(
                    1 for r in submissions.values()
                    if r.status == "PR_CREATED"
                )
                stats['phase_6']['submitted'] = len(submissions)
                stats['phase_6']['success'] = success_count
                logger.info(f"Submitted {len(submissions)}/{len(new_issues)} PRs, {success_count} successful\n")
            else:
                logger.warning("Phase 6 not enabled, skipping")
            
            stats['total_time_seconds'] = (datetime.now() - start_time).total_seconds()
            
            # Summary
            logger.info("="*70)
            logger.info("✨ PIPELINE COMPLETE")
            logger.info("="*70)
            logger.info(f"Phase 2 (Monitor): {stats['phase_2']['found']} issues found")
            logger.info(f"Phase 3 (Ingest):  {stats['phase_3']['ingested']} issues ingested")
            logger.info(f"Phase 4 (Solve):   {stats['phase_4'].get('patched', 0)} patches generated")
            logger.info(f"Phase 5 (Test):    {stats['phase_5'].get('tested', 0)} patches tested, {stats['phase_5'].get('ready', 0)} ready")
            logger.info(f"Phase 6 (Submit):  {stats['phase_6'].get('submitted', 0)} PRs submitted, {stats['phase_6'].get('success', 0)} successful")
            logger.info(f"Total Time: {stats['total_time_seconds']:.1f} seconds")
            logger.info("="*70 + "\n")
            
            return stats
        
        except Exception as e:
            logger.error(f"Fatal error in pipeline: {e}", exc_info=True)
            stats['total_time_seconds'] = (datetime.now() - start_time).total_seconds()
            stats['error'] = str(e)
            return stats

    def run_daemon(
        self,
        interval: int = 300,
        max_phases: int = 3
    ):
        """
        Run in daemon mode with continuous cycling
        
        Args:
            interval: Polling interval in seconds (default: 300 = 5 minutes)
            max_phases: Maximum phases to run (2, 3, 4, 5, 6, or 7)
        """
        logger.info(f"🚀 Starting daemon mode")
        logger.info(f"  Polling interval: {interval}s")
        logger.info(f"  Maximum phases: {max_phases}")
        cycle_count = 0
        
        try:
            while True:
                cycle_count += 1
                logger.info(f"\n{'='*70}")
                logger.info(f"Cycle #{cycle_count} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"{'='*70}")
                
                self.run_full_pipeline()
                
                logger.info(f"💤 Sleeping for {interval}s until next cycle...")
                time.sleep(interval)
        
        except KeyboardInterrupt:
            logger.info(f"\n⏹️  Daemon interrupted by user after {cycle_count} cycles")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Fatal error in daemon mode: {e}", exc_info=True)
            sys.exit(1)


# Configure logging


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="🤖 Autonomous Code Bounties Bot - Automated Bounty Hunter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run Phase 2 only (monitor)
  python bounty_bot/main.py

  # Run Phase 2-3 (monitor + ingest)
  python bounty_bot/main.py --phases 2-3

  # Run full pipeline Phase 2-7
  python bounty_bot/main.py --phases 2-7

    # Run Phase 2-5 without creating forks, pushes, or pull requests
    python bounty_bot/main.py --phases 2-7 --dry-run

  # Run Phase 2-7 in daemon mode (every 5 minutes)
  python bounty_bot/main.py --phases 2-7 --daemon --interval 300

  # Custom configuration
  python bounty_bot/main.py --phases 2-7 --config custom_config.yaml --log-level DEBUG
        """
    )

    parser.add_argument(
        '--phases',
        type=str,
        default='2-3',
        help='Phase range to run (e.g., "2-3", "2-7", "4-6") [default: 2-3]'
    )

    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run in daemon mode (continuous polling)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run enabled phases without creating forks, pushes, or pull requests'
    )

    parser.add_argument(
        '--interval',
        type=int,
        default=300,
        help='Polling interval in seconds [default: 300]'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='bounty_bot/config/settings.yaml',
        help='Path to settings.yaml configuration file'
    )

    parser.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level [default: INFO]'
    )

    args = parser.parse_args()

    # Set log level
    logging.getLogger().setLevel(args.log_level)

    # Load environment variables
    load_dotenv('.env')

    # Verify config file exists
    if not os.path.exists(args.config):
        logger.error(f"Configuration file not found: {args.config}")
        logger.info("Please create a .env file and configure settings.yaml")
        sys.exit(1)

    # Verify required environment variables
    required_env_vars = ['GEMINI_API_KEY', 'GITHUB_TOKEN']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.warning(f"Missing environment variables: {', '.join(missing_vars)}")
        logger.info("Some features may not work correctly.")

    # Initialize bot
    try:
        bot = BountyBot(
            config_path=args.config,
            phases=args.phases,
            dry_run=args.dry_run
        )
    except ValueError as e:
        logger.error(f"Invalid phase configuration: {e}")
        sys.exit(1)

    # Run
    if args.daemon:
        # Parse phase end
        _, phase_end = map(int, args.phases.split('-'))
        bot.run_daemon(interval=args.interval, max_phases=phase_end)
    else:
        # Single run
        stats = bot.run_full_pipeline()
        
        # Exit with error if phases failed
        if 'error' in stats:
            sys.exit(1)


if __name__ == '__main__':
    main()
