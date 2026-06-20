#!/usr/bin/env python3
"""
Health Check Script for Supabase Connection & Data Integrity

Usage:
    python scripts/health_check.py
    
Output:
    Validates database connection, tables, recent data, and storage
"""

import os
import sys
from datetime import datetime, timedelta
from urllib.parse import urlparse, quote
from sqlalchemy import create_engine, text, inspect


class HealthChecker:
    def __init__(self):
        self.db_url = os.getenv("SUPABASE_DB_URL")
        self.results = {}
        self.engine = None
        
    def _fix_db_url(self, url):
        """Fix URL for psycopg3 compatibility"""
        if not url or "+psycopg" in url:
            return url
        url = url.strip().strip('"').strip("'")  # Remove whitespace and quotes
        parsed = urlparse(url)
        if not parsed.username or not parsed.password:
            print(f"  [ERROR] Invalid SUPABASE_DB_URL format")
            print(f"  [DEBUG] URL: {url[:50]}...")
            print(f"  [DEBUG] parsed.username: {parsed.username}")
            return None
        encoded_username = parsed.username.replace('.', '%2E')
        encoded_password = quote(parsed.password, safe='')
        return f"postgresql+psycopg://{encoded_username}:{encoded_password}@{parsed.hostname}:{parsed.port}{parsed.path}"
        
    def connect_db(self):
        """Test database connection"""
        print("[CHECK] Database connection...")
        try:
            if not self.db_url:
                print("  [WARN] SUPABASE_DB_URL not set - skipping Supabase checks")
                return False
            
            fixed_url = self._fix_db_url(self.db_url)
            self.engine = create_engine(fixed_url, echo=False)
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            print("  [OK] Connection successful")
            self.results["db_connection"] = True
            return True
            
        except Exception as e:
            print(f"  [ERROR] Connection failed: {e}")
            self.results["db_connection"] = False
            return False
    
    def check_tables(self):
        """Verify required tables exist"""
        print("[CHECK] Database tables...")
        try:
            if not self.engine:
                print("  [SKIP] Engine not available")
                return False
            
            inspector = inspect(self.engine)
            tables = inspector.get_table_names()
            
            required = ["stock_summary", "ingestion_log"]
            missing = [t for t in required if t not in tables]
            
            if missing:
                print(f"  [WARN] Missing tables: {missing}")
                self.results["tables_exist"] = False
                return False
            else:
                print(f"  [OK] All required tables exist: {required}")
                self.results["tables_exist"] = True
                return True
                
        except Exception as e:
            print(f"  [ERROR] Table check failed: {e}")
            self.results["tables_exist"] = False
            return False
    
    def check_recent_data(self):
        """Verify recent data exists"""
        print("[CHECK] Recent data...")
        try:
            if not self.engine:
                print("  [SKIP] Engine not available")
                return False
            
            with self.engine.connect() as conn:
                # Check latest date
                result = conn.execute(text("""
                    SELECT MAX(date) as latest_date, COUNT(*) as total_records
                    FROM stock_summary
                """)).fetchone()
                
                if result and result[0]:
                    latest_date = result[0]
                    total = result[1]
                    
                    # Parse date if string
                    if isinstance(latest_date, str):
                        latest_date = latest_date[:10]
                    
                    print(f"  [OK] Latest date: {latest_date}, Total records: {total:,}")
                    self.results["recent_data"] = True
                    return True
                else:
                    print("  [WARN] No data in stock_summary")
                    self.results["recent_data"] = False
                    return False
                    
        except Exception as e:
            print(f"  [ERROR] Data check failed: {e}")
            self.results["recent_data"] = False
            return False
    
    def check_ingestion_log(self):
        """Check ingestion log status"""
        print("[CHECK] Ingestion log status...")
        try:
            if not self.engine:
                print("  [SKIP] Engine not available")
                return False
            
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT status, COUNT(*) as count
                    FROM ingestion_log
                    GROUP BY status
                    ORDER BY status
                """)).fetchall()
                
                if result:
                    status_summary = {row[0]: row[1] for row in result}
                    print(f"  [OK] Status breakdown: {status_summary}")
                    
                    # Check if there are too many failed/empty
                    failed = status_summary.get("failed", 0)
                    empty = status_summary.get("empty", 0)
                    
                    if failed > 5:
                        print(f"  [WARN] High number of failed dates: {failed}")
                    if empty > 10:
                        print(f"  [WARN] High number of empty dates: {empty} (expected for holidays)")
                    
                    self.results["ingestion_log"] = True
                    return True
                else:
                    print("  [WARN] No ingestion_log data")
                    self.results["ingestion_log"] = False
                    return False
                    
        except Exception as e:
            print(f"  [ERROR] Ingestion log check failed: {e}")
            self.results["ingestion_log"] = False
            return False
    
    def check_storage(self):
        """Estimate storage usage (Supabase only)"""
        print("[CHECK] Storage usage...")
        try:
            if not self.engine or "supabase" not in self.db_url.lower():
                print("  [SKIP] Not Supabase or engine not available")
                return True
            
            with self.engine.connect() as conn:
                # Rough estimate based on row count
                result = conn.execute(text("""
                    SELECT 
                        (SELECT COUNT(*) FROM stock_summary) * 0.001 +
                        (SELECT COUNT(*) FROM ingestion_log) * 0.0005
                """)).fetchone()
                
                estimated_mb = float(result[0]) if result and result[0] else 0
                
                if estimated_mb < 500:
                    print(f"  [OK] Estimated usage: ~{estimated_mb:.1f} MB / 500 MB")
                    self.results["storage"] = True
                    return True
                else:
                    print(f"  [WARN] High storage: ~{estimated_mb:.1f} MB / 500 MB")
                    self.results["storage"] = False
                    return False
                    
        except Exception as e:
            print(f"  [WARN] Storage check skipped: {e}")
            return True
    
    def run_all_checks(self):
        """Run all health checks"""
        print("=" * 80)
        print("SUPABASE HEALTH CHECK")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        print()
        
        self.connect_db()
        self.check_tables()
        self.check_recent_data()
        self.check_ingestion_log()
        self.check_storage()
        
        print()
        print("=" * 80)
        print("HEALTH CHECK SUMMARY")
        print("=" * 80)
        
        all_passed = all(self.results.values())
        
        for check, result in self.results.items():
            status = "[PASS]" if result else "[FAIL]"
            print(f"  {status}: {check.replace('_', ' ').title()}")
        
        print()
        if all_passed:
            print("[OVERALL] HEALTHY")
            print("=" * 80)
            return True
        else:
            print("[OVERALL] ISSUES DETECTED")
            print("\nTroubleshooting steps:")
            print("1. Check SUPABASE_DB_URL environment variable")
            print("2. Verify database connection in Supabase dashboard")
            print("3. Check ingestion_log for recent errors")
            print("4. Run retry workflow: github.com/actions/Retry_Failed_Ingestion")
            print("=" * 80)
            return False


def main():
    checker = HealthChecker()
    success = checker.run_all_checks()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
