#!/usr/bin/env python3
"""
Autonomous Code Bounties Bot - Main Entry Point
Phase 2: Issue Monitor Implementation
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
        logger.info("🤖 Autonomous Code Bounties Bot initialized")

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

    def run_daemon(self, interval: int = 300):
        """
        Run the bot in daemon mode (continuous polling)
        
        Args:
            interval: Polling interval in seconds (default: 300 = 5 minutes)
        """
        logger.info(f"🚀 Starting daemon mode with {interval}s interval")
        cycle_count = 0
        
        try:
            while True:
                cycle_count += 1
                logger.info(f"--- Cycle #{cycle_count} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
                
                new_count = self.run_single_cycle()
                
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
  # Run single poll cycle
  python bounty_bot/main.py

  # Run in daemon mode (poll every 5 minutes)
  python bounty_bot/main.py --daemon --interval 300

  # Run in daemon mode with verbose logging
  python bounty_bot/main.py --daemon --log-level DEBUG

  # Use custom config file
  python bounty_bot/main.py --config custom_config.yaml
        """
    )

    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run in daemon mode (continuous polling)'
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
        bot.run_daemon(interval=args.interval)
    else:
        # Single cycle mode
        logger.info("Running single poll cycle...")
        new_count = bot.run_single_cycle()
        logger.info(f"✅ Completed: Found {new_count} new issues")


if __name__ == '__main__':
    main()
