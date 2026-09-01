#!/usr/bin/env python3
"""
Autonomous Code Bounties Bot - Main Entry Point
Phase 3: Code Ingestor Integration
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from bounty_bot.src.monitor import IssueMonitor
from bounty_bot.src.ingestor import CodeIngestor

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BountyBot:
    """Main bounty bot orchestrator"""

    def __init__(self, config_path: str = "bounty_bot/config/settings.yaml"):
        """Initialize the bounty bot"""
        self.config_path = config_path
        self.monitor = IssueMonitor(config_path)
        self.ingestor = CodeIngestor()
        logger.info("🤖 Autonomous Code Bounties Bot initialized (Phase 2 + 3)")

    def run_single_cycle(self) -> int:
        """
        Run a single poll cycle and return number of new issues found
        
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
        Ingest code context for identified issues (Phase 3)
        
        Args:
            issues: List of BountyIssue objects from monitor
        
        Returns:
            Number of successfully ingested issues
        """
        logger.info(f"Starting code ingestion for {len(issues)} issues...")
        ingested_count = 0
        
        for issue in issues:
            try:
                logger.info(f"Ingesting issue: {issue.title}")
                
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
                    # Save context for Phase 4 (Solver)
                    cache_path = f"/tmp/bounty_cache/contexts/{issue.id}_context.json"
                    self.ingestor.save_context(context, cache_path)
                    ingested_count += 1
                    logger.info(f"✓ Ingested {issue.title}")
                else:
                    logger.warning(f"✗ Failed to ingest {issue.title}")
            
            except Exception as e:
                logger.error(f"Error ingesting {issue.id}: {e}", exc_info=True)
        
        logger.info(f"Code ingestion completed: {ingested_count}/{len(issues)} successful")
        return ingested_count

    def run_full_cycle(self) -> dict:
        """
        Run full cycle: Monitor (Phase 2) + Ingest (Phase 3)
        
        Returns:
            Dict with statistics
        """
        logger.info("="*60)
        logger.info("🔄 FULL CYCLE: Monitor + Ingest (Phase 2-3)")
        logger.info("="*60)
        
        # Phase 2: Monitor
        logger.info("\n📡 Phase 2: Monitoring for new bounty issues...")
        new_issues = self.monitor.run_poll_cycle()
        
        # Phase 3: Ingest
        logger.info(f"\n🔍 Phase 3: Ingesting code context for {len(new_issues)} issues...")
        ingested_count = self.ingest_issues(new_issues)
        
        stats = {
            'found_issues': len(new_issues),
            'ingested_issues': ingested_count,
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info("\n" + "="*60)
        logger.info(f"✨ Cycle Complete: {len(new_issues)} found, {ingested_count} ingested")
        logger.info("="*60)
        
        return stats

    def run_daemon(self, interval: int = 300, enable_ingest: bool = True):
        """
        Run the bot in daemon mode (continuous polling)
        
        Args:
            interval: Polling interval in seconds (default: 300 = 5 minutes)
            enable_ingest: Enable Phase 3 code ingestion (default: True)
        """
        logger.info(f"🚀 Starting daemon mode with {interval}s interval")
        logger.info(f"Code ingestion (Phase 3): {'✓ ENABLED' if enable_ingest else '✗ DISABLED'}")
        cycle_count = 0
        
        try:
            while True:
                cycle_count += 1
                logger.info(f"--- Cycle #{cycle_count} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
                
                if enable_ingest:
                    self.run_full_cycle()  # Phase 2 + 3
                else:
                    self.run_single_cycle()  # Phase 2 only
                
                logger.info(f"💤 Sleeping for {interval}s until next cycle...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            logger.info("\n⏹️  Daemon interrupted by user")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Fatal error in daemon mode: {e}", exc_info=True)
            sys.exit(1)


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="🤖 Autonomous Code Bounties Bot - Automated Bounty Hunter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run single poll cycle (Phase 2 only)
  python bounty_bot/main.py

  # Run single full cycle (Phase 2 + 3)
  python bounty_bot/main.py --full-cycle

  # Run in daemon mode (poll every 5 minutes, Phase 2 only)
  python bounty_bot/main.py --daemon --interval 300

  # Run in daemon mode with code ingestion (Phase 2 + 3)
  python bounty_bot/main.py --daemon --enable-ingest --interval 300

  # Run in daemon mode with verbose logging
  python bounty_bot/main.py --daemon --enable-ingest --log-level DEBUG

  # Use custom config file
  python bounty_bot/main.py --config custom_config.yaml --enable-ingest
        """
    )

    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run in daemon mode (continuous polling)'
    )

    parser.add_argument(
        '--enable-ingest',
        action='store_true',
        help='Enable Phase 3 code ingestion (default: False)'
    )

    parser.add_argument(
        '--full-cycle',
        action='store_true',
        help='Run single full cycle (Phase 2 + 3) and exit'
    )

    parser.add_argument(
        '--interval',
        type=int,
        default=300,
        help='Polling interval in seconds (default: 300 = 5 minutes)'
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
        help='Logging level (default: INFO)'
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

    # Initialize and run bot
    bot = BountyBot(config_path=args.config)

    if args.daemon:
        bot.run_daemon(interval=args.interval, enable_ingest=args.enable_ingest)
    elif args.full_cycle:
        # Full cycle mode (Phase 2 + 3)
        logger.info("Running full cycle (Phase 2 + 3)...")
        stats = bot.run_full_cycle()
        logger.info(f"✅ Completed: Found {stats['found_issues']}, Ingested {stats['ingested_issues']}")
    else:
        # Single poll cycle mode (Phase 2 only)
        if args.enable_ingest:
            logger.info("Running full cycle (Phase 2 + 3)...")
            stats = bot.run_full_cycle()
            logger.info(f"✅ Completed: Found {stats['found_issues']}, Ingested {stats['ingested_issues']}")
        else:
            logger.info("Running single poll cycle (Phase 2)...")
            new_count = bot.run_single_cycle()
            logger.info(f"✅ Completed: Found {new_count} new issues")


if __name__ == '__main__':
    main()
