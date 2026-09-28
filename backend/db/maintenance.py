"""Database maintenance utilities for CUA-Sentinel.

Usage:
    python -m backend.db.maintenance --cleanup-backups
    python -m backend.db.maintenance --vacuum
    python -m backend.db.maintenance --stats
    python -m backend.db.maintenance --prune-telemetry --days 30
"""

import argparse
import logging
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).parent.parent.parent / "data"
BACKUP_DIR = DB_DIR / ".sentinel_backup" / "db_pre_migrate"

DATABASES = {
    "operational": DB_DIR / "operational.sqlite",
    "audit": DB_DIR / "audit.sqlite", 
    "knowledge": DB_DIR / "knowledge.sqlite",
    "state": DB_DIR / "state.sqlite",
}


def cleanup_backups(keep_per_db: int = 3, dry_run: bool = False) -> dict:
    """Remove old backup files, keeping only the most recent per database.
    
    Returns dict with counts of files removed per database.
    """
    if not BACKUP_DIR.exists():
        logger.info("No backup directory found")
        return {}
    
    results = {}
    for db_name in DATABASES.keys():
        pattern = f"{db_name}_*.sqlite"
        backups = sorted(BACKUP_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        
        to_remove = backups[keep_per_db:]
        results[db_name] = {"kept": len(backups[:keep_per_db]), "removed": 0, "freed_mb": 0}
        
        for old_backup in to_remove:
            size_mb = old_backup.stat().st_size / (1024 * 1024)
            if dry_run:
                logger.info(f"[DRY RUN] Would remove: {old_backup.name} ({size_mb:.2f} MB)")
            else:
                old_backup.unlink()
                logger.info(f"Removed: {old_backup.name} ({size_mb:.2f} MB)")
            results[db_name]["removed"] += 1
            results[db_name]["freed_mb"] += size_mb
    
    total_freed = sum(r["freed_mb"] for r in results.values())
    total_removed = sum(r["removed"] for r in results.values())
    logger.info(f"Total: removed {total_removed} files, freed {total_freed:.2f} MB")
    return results


def vacuum_databases() -> dict:
    """Run VACUUM on all databases to reclaim space and defragment."""
    results = {}
    for db_name, db_path in DATABASES.items():
        if not db_path.exists():
            continue
        
        size_before = db_path.stat().st_size / (1024 * 1024)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("VACUUM")
            conn.close()
            size_after = db_path.stat().st_size / (1024 * 1024)
            saved = size_before - size_after
            results[db_name] = {
                "before_mb": size_before,
                "after_mb": size_after,
                "saved_mb": saved,
            }
            logger.info(f"{db_name}: {size_before:.2f} MB -> {size_after:.2f} MB (saved {saved:.2f} MB)")
        except Exception as e:
            logger.error(f"Failed to vacuum {db_name}: {e}")
            results[db_name] = {"error": str(e)}
        finally:
            conn.close()
    
    return results


def get_stats() -> dict:
    """Get row counts and sizes for all tables across all databases."""
    stats = {}
    for db_name, db_path in DATABASES.items():
        if not db_path.exists():
            continue
        
        size_mb = db_path.stat().st_size / (1024 * 1024)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = {}
        for row in cur.fetchall():
            table_name = row["name"]
            try:
                cnt = conn.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()[0]
                tables[table_name] = cnt
            except Exception:
                tables[table_name] = "ERROR"
        
        conn.close()
        stats[db_name] = {"size_mb": size_mb, "tables": tables}
    
    # Backup stats
    if BACKUP_DIR.exists():
        backup_files = list(BACKUP_DIR.glob("*.sqlite"))
        backup_size = sum(f.stat().st_size for f in backup_files) / (1024 * 1024)
        stats["_backups"] = {"count": len(backup_files), "size_mb": backup_size}
    
    return stats


def prune_telemetry(days: int = 30) -> dict:
    """Remove telemetry events older than specified days."""
    audit_db = DATABASES["audit"]
    if not audit_db.exists():
        return {"error": "audit.sqlite not found"}
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    conn = sqlite3.connect(str(audit_db))
    try:
        # Check current count
        before = conn.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0]
        
        # Note: telemetry_events has append-only trigger, need to disable temporarily
        conn.execute("DROP TRIGGER IF EXISTS prevent_telemetry_events_delete")
        conn.execute("DELETE FROM telemetry_events WHERE timestamp < ?", (cutoff,))
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS prevent_telemetry_events_delete
            BEFORE DELETE ON telemetry_events
            BEGIN SELECT RAISE(ABORT, 'telemetry_events is append-only'); END
        """)
        conn.commit()
        
        after = conn.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0]
        removed = before - after
        
        logger.info(f"Pruned {removed} telemetry events older than {days} days")
        return {"before": before, "after": after, "removed": removed}
    except Exception as e:
        logger.error(f"Failed to prune telemetry: {e}")
        return {"error": str(e)}
    finally:
        conn.close()


def prune_audit_logs(days: int = 90) -> dict:
    """Remove audit logs older than specified days (careful - governance data!)."""
    audit_db = DATABASES["audit"]
    if not audit_db.exists():
        return {"error": "audit.sqlite not found"}
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    conn = sqlite3.connect(str(audit_db))
    try:
        before = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        
        # Disable append-only trigger temporarily
        conn.execute("DROP TRIGGER IF EXISTS prevent_audit_logs_delete")
        conn.execute("DELETE FROM audit_logs WHERE created_at < ?", (cutoff,))
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS prevent_audit_logs_delete
            BEFORE DELETE ON audit_logs
            BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END
        """)
        conn.commit()
        
        after = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        removed = before - after
        
        logger.info(f"Pruned {removed} audit logs older than {days} days")
        return {"before": before, "after": after, "removed": removed}
    except Exception as e:
        logger.error(f"Failed to prune audit logs: {e}")
        return {"error": str(e)}
    finally:
        conn.close()


def print_stats(stats: dict) -> None:
    """Pretty print database statistics."""
    for db_name, info in stats.items():
        if db_name == "_backups":
            print(f"\n=== BACKUPS ===")
            print(f"  Files: {info['count']}")
            print(f"  Size: {info['size_mb']:.2f} MB")
            continue
        
        print(f"\n=== {db_name.upper()} ({info['size_mb']:.2f} MB) ===")
        for table, count in sorted(info["tables"].items()):
            print(f"  {table}: {count} rows")


def main():
    parser = argparse.ArgumentParser(description="CUA-Sentinel database maintenance")
    parser.add_argument("--cleanup-backups", action="store_true", help="Remove old backup files")
    parser.add_argument("--keep", type=int, default=3, help="Number of backups to keep per DB (default: 3)")
    parser.add_argument("--vacuum", action="store_true", help="Run VACUUM on all databases")
    parser.add_argument("--stats", action="store_true", help="Show database statistics")
    parser.add_argument("--prune-telemetry", action="store_true", help="Remove old telemetry events")
    parser.add_argument("--prune-audit", action="store_true", help="Remove old audit logs (careful!)")
    parser.add_argument("--days", type=int, default=30, help="Days to retain for pruning (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    
    args = parser.parse_args()
    
    if args.stats:
        stats = get_stats()
        print_stats(stats)
    
    if args.cleanup_backups:
        cleanup_backups(keep_per_db=args.keep, dry_run=args.dry_run)
    
    if args.vacuum and not args.dry_run:
        vacuum_databases()
    
    if args.prune_telemetry and not args.dry_run:
        prune_telemetry(days=args.days)
    
    if args.prune_audit and not args.dry_run:
        prune_audit(days=args.days)
    
    if not any([args.stats, args.cleanup_backups, args.vacuum, args.prune_telemetry, args.prune_audit]):
        parser.print_help()


if __name__ == "__main__":
    main()
