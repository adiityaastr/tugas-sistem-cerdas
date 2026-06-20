#!/usr/bin/env python3
"""
Manual Backfill Tool for IDX Ingestion Pipeline

Enables manual retry of failed/empty ingestions with GitHub Actions integration.

Usage:
    # Single date
    python scripts/backfill.py --date 2026-06-16
    
    # Date range
    python scripts/backfill.py --start 2026-06-10 --end 2026-06-20
    
    # All failed dates
    python scripts/backfill.py --all-failed
    
    # Dry-run (preview only)
    python scripts/backfill.py --date 2026-06-16 --dry-run
    
    # GitHub Actions dispatcher mode
    python scripts/backfill.py --gh-dispatch
"""

import os
import sys
import argparse
import subprocess
from datetime import datetime, timedelta
from typing import List
from sqlalchemy import create_engine, text


class BackfillTool:
    def __init__(self, args):
        self.db_url = os.getenv("SUPABASE_DB_URL")
        self.args = args
        self.dates_to_retry = []
        self.dry_run = args.dry_run
        self.gh_dispatch = args.gh_dispatch
        self.logger = self._setup_logger()
        self.engine = None
        
    def _setup_logger(self):
        """Setup simple logger"""
        class Logger:
            def info(self, msg):
                print(f"[INFO] {msg}")
            def warn(self, msg):
                print(f"[WARN] {msg}")
            def error(self, msg):
                print(f"[ERROR] {msg}")
            def success(self, msg):
                print(f"[SUCCESS] {msg}")
            def debug(self, msg):
                if "-vv" in sys.argv:
                    print(f"[DEBUG] {msg}")
        return Logger()
    
    def _connect_db(self):
        """Connect to Supabase"""
        if not self.db_url:
            self.logger.error("SUPABASE_DB_URL not set")
            sys.exit(1)
        
        try:
            self.engine = create_engine(self.db_url, echo=False)
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            self.logger.debug("Database connection successful")
            return True
        except Exception as e:
            self.logger.error(f"Database connection failed: {e}")
            sys.exit(1)
    
    def _parse_dates(self) -> List[str]:
        """Parse dates from arguments"""
        dates = []
        
        if self.args.date:
            dates = [self.args.date]
        
        elif self.args.start and self.args.end:
            start = datetime.strptime(self.args.start, "%Y-%m-%d")
            end = datetime.strptime(self.args.end, "%Y-%m-%d")
            current = start
            while current <= end:
                dates.append(current.strftime("%Y-%m-%d"))
                current += timedelta(days=1)
        
        elif self.args.all_failed:
            self._connect_db()
            dates = self._get_failed_dates()
        
        elif self.gh_dispatch:
            # GitHub Actions dispatch mode - get from env or stdin
            gh_date = os.getenv("GH_DATE", "").strip()
            if gh_date:
                dates = [gh_date]
            else:
                # Fallback to all failed
                self._connect_db()
                dates = self._get_failed_dates()
        
        return sorted(list(set(dates)))
    
    def _get_failed_dates(self) -> List[str]:
        """Query failed dates from ingestion_log"""
        if not self.engine:
            self._connect_db()
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT date, status, record_count, retry_count
                    FROM ingestion_log
                    WHERE status IN ('failed', 'empty')
                    ORDER BY date DESC
                """)).fetchall()
                
                dates = [str(row[0]) for row in result]
                
                if result:
                    self.logger.info(f"Found {len(result)} failed/empty date(s)")
                    for row in result:
                        print(f"  {row[0]} - status: {row[1]} ({row[2]} records, {row[3]} retries)")
                else:
                    self.logger.info("No failed dates found")
                
                return dates
        except Exception as e:
            self.logger.error(f"Failed to query database: {e}")
            return []
    
    def preview(self):
        """Show preview of what will be retried"""
        print()
        print("=" * 80)
        print("BACKFILL PREVIEW")
        print("=" * 80)
        
        if not self.dates_to_retry:
            print("\n[INFO] No dates to retry")
            return False
        
        self._connect_db()
        
        print(f"\nWill retry {len(self.dates_to_retry)} date(s):\n")
        
        with self.engine.connect() as conn:
            for date in self.dates_to_retry:
                result = conn.execute(text("""
                    SELECT status, record_count, error_message, retry_count
                    FROM ingestion_log
                    WHERE date = :date
                    ORDER BY started_at DESC
                    LIMIT 1
                """), {"date": date}).fetchone()
                
                if result:
                    status, count, error, retries = result
                    error_msg = (error[:40] + "...") if error else "N/A"
                    print(f"  {date} | status: {status:6s} | records: {count:4d} | retries: {retries} | {error_msg}")
                else:
                    print(f"  {date} | (new entry)")
        
        print()
        return True
    
    def interactive_confirm(self):
        """Ask user for confirmation before executing"""
        if self.gh_dispatch:
            # GitHub Actions mode - auto-confirm
            return True
        
        response = input("Proceed with backfill? (y/n): ").strip().lower()
        return response in ["y", "yes"]
    
    def execute_backfill(self):
        """Execute backfill for each date"""
        print()
        print("=" * 80)
        print("EXECUTING BACKFILL")
        print("=" * 80)
        print()
        
        if not self.dates_to_retry:
            self.logger.info("No dates to retry")
            return True
        
        success_count = 0
        error_count = 0
        
        for i, date in enumerate(self.dates_to_retry, 1):
            print(f"\n[{i}/{len(self.dates_to_retry)}] Retrying {date}...")
            
            try:
                env = os.environ.copy()
                env["INGEST_DATE"] = date
                env["MAX_RETRIES"] = "1"
                
                # Call ingestion pipeline for specific date
                result = subprocess.run(
                    [sys.executable, "ingestion/ingestion_pipeline.py"],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                
                if result.returncode == 0:
                    self.logger.success(f"{date} completed")
                    success_count += 1
                else:
                    self.logger.error(f"{date} failed (exit code {result.returncode})")
                    if result.stderr:
                        print(f"  Error: {result.stderr[:200]}")
                    error_count += 1
                    
            except subprocess.TimeoutExpired:
                self.logger.error(f"{date} timed out")
                error_count += 1
            except Exception as e:
                self.logger.error(f"{date} exception: {e}")
                error_count += 1
        
        print()
        print("=" * 80)
        print("BACKFILL SUMMARY")
        print("=" * 80)
        print(f"Total:     {len(self.dates_to_retry)} date(s)")
        print(f"Success:   {success_count} ✓")
        print(f"Failed:    {error_count} ✗")
        print("=" * 80)
        
        return error_count == 0
    
    def run(self):
        """Main execution"""
        print("=" * 80)
        print("IDX INGESTION BACKFILL TOOL")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        print()
        
        # Parse dates
        self.dates_to_retry = self._parse_dates()
        
        if not self.dates_to_retry:
            self.logger.info("No dates specified")
            return True
        
        # Preview
        if not self.preview():
            return True
        
        # Dry run?
        if self.dry_run:
            self.logger.success("Dry-run complete. No changes made.")
            return True
        
        # Confirm
        if not self.interactive_confirm():
            self.logger.info("Cancelled")
            return True
        
        # Execute
        success = self.execute_backfill()
        
        if success:
            self.logger.success("Backfill completed successfully")
        else:
            self.logger.warn("Backfill completed with errors")
        
        return success


def main():
    parser = argparse.ArgumentParser(
        description="Manual backfill tool for IDX ingestion pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single date
  python scripts/backfill.py --date 2026-06-16
  
  # Date range
  python scripts/backfill.py --start 2026-06-10 --end 2026-06-20
  
  # All failed dates
  python scripts/backfill.py --all-failed
  
  # Dry-run
  python scripts/backfill.py --date 2026-06-16 --dry-run
  
  # GitHub Actions (auto-confirm)
  python scripts/backfill.py --gh-dispatch
        """
    )
    
    parser.add_argument(
        "--date",
        type=str,
        help="Single date (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--end",
        type=str,
        help="End date (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--all-failed",
        action="store_true",
        help="Retry all failed/empty dates"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without executing"
    )
    
    parser.add_argument(
        "--gh-dispatch",
        action="store_true",
        help="GitHub Actions dispatcher mode (auto-confirm)"
    )
    
    parser.add_argument(
        "-vv",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # Validate args
    if not any([args.date, args.start, args.all_failed, args.gh_dispatch]):
        parser.print_help()
        sys.exit(1)
    
    if (args.date or args.all_failed) and (args.start or args.end):
        parser.error("Cannot combine --date/--all-failed with --start/--end")
    
    if bool(args.start) != bool(args.end):
        parser.error("Both --start and --end required for date range")
    
    tool = BackfillTool(args)
    success = tool.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
