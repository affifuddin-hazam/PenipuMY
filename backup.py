"""
PenipuMY V2 — Daily Auto Backup Script
Creates a timestamped zip of the database, web scripts, uploads, templates, and static files.
Deletes backups older than RETENTION_DAYS.

Usage:
    python backup.py          # Run backup manually
    python backup.py --dry    # Show what would be backed up without creating zip
"""

import os
import sys
import zipfile
import datetime
import glob
import logging

# === Configuration ===
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(PROJECT_DIR, 'backups')
RETENTION_DAYS = 30
DB_NAME = 'scam_reports.db'

# Root-level file patterns to include
INCLUDE_PATTERNS = ['*.py', '*.bat', '*.md', '*.csv', '*.txt', '*.json', '*.cfg', '*.ini', '*.yml', '*.yaml']

# Directories to include recursively
INCLUDE_DIRS = ['templates', 'static', 'uploads']

# Directories to exclude (won't be traversed)
EXCLUDE_DIRS = {
    'backups', '__pycache__', '.claude', '.agent',
    '_bmad', '_bmad-output', 'db backup', 'node_modules',
    '.git', 'docs', 'venv', 'env'
}

# File extensions to skip inside included dirs
SKIP_EXTENSIONS = {'.pyc', '.pyo', '.log'}

# === Logging ===
log_path = os.path.join(BACKUP_DIR, 'backup.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_path, encoding='utf-8')
    ]
)
logger = logging.getLogger('backup')


def collect_files():
    """Collect all files to be backed up. Returns list of (abs_path, arcname) tuples."""
    files = []

    # 1. Database
    db_path = os.path.join(PROJECT_DIR, DB_NAME)
    if os.path.isfile(db_path):
        files.append((db_path, DB_NAME))
    else:
        logger.warning(f"Database not found: {db_path}")

    # 2. Root-level files matching patterns
    added_root = set()
    for pattern in INCLUDE_PATTERNS:
        for fpath in glob.glob(os.path.join(PROJECT_DIR, pattern)):
            if os.path.isfile(fpath):
                fname = os.path.basename(fpath)
                if fname not in added_root:
                    added_root.add(fname)
                    files.append((fpath, fname))

    # 3. Included directories (recursive)
    for dirname in INCLUDE_DIRS:
        dir_path = os.path.join(PROJECT_DIR, dirname)
        if not os.path.isdir(dir_path):
            logger.info(f"Directory not found (skipping): {dir_path}")
            continue
        for root, dirs, filenames in os.walk(dir_path):
            # Skip excluded subdirectories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in SKIP_EXTENSIONS:
                    continue
                abs_path = os.path.join(root, fname)
                arc_name = os.path.relpath(abs_path, PROJECT_DIR)
                files.append((abs_path, arc_name))

    return files


def run_backup(dry_run=False):
    """Create a backup zip. Returns the zip file path on success, None on failure."""
    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_filename = f'backup_{timestamp}.zip'
    zip_path = os.path.join(BACKUP_DIR, zip_filename)

    files = collect_files()

    if dry_run:
        logger.info(f"=== DRY RUN — {len(files)} files would be backed up ===")
        total_size = 0
        for abs_path, arc_name in files:
            size = os.path.getsize(abs_path)
            total_size += size
            logger.info(f"  {arc_name} ({_fmt_size(size)})")
        logger.info(f"Total uncompressed: {_fmt_size(total_size)}")
        return None

    logger.info(f"Starting backup: {zip_filename}")
    logger.info(f"Files to back up: {len(files)}")

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for abs_path, arc_name in files:
                zf.write(abs_path, arc_name)

        zip_size = os.path.getsize(zip_path)
        logger.info(f"Backup created: {zip_filename} ({_fmt_size(zip_size)})")

        # Cleanup old backups
        removed = cleanup_old_backups()
        if removed:
            logger.info(f"Cleaned up {removed} old backup(s)")

        return zip_path

    except Exception as e:
        logger.error(f"Backup failed: {e}", exc_info=True)
        # Remove partial zip if it exists
        if os.path.isfile(zip_path):
            os.remove(zip_path)
        return None


def cleanup_old_backups():
    """Delete backup_*.zip files older than RETENTION_DAYS. Returns count removed."""
    cutoff = datetime.datetime.now() - datetime.timedelta(days=RETENTION_DAYS)
    removed = 0

    for fpath in glob.glob(os.path.join(BACKUP_DIR, 'backup_*.zip')):
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime < cutoff:
                os.remove(fpath)
                logger.info(f"Removed old backup: {os.path.basename(fpath)}")
                removed += 1
        except Exception as e:
            logger.warning(f"Could not remove {fpath}: {e}")

    return removed


def list_backups():
    """Return list of existing backups sorted newest first. Each item is a dict."""
    backups = []
    for fpath in glob.glob(os.path.join(BACKUP_DIR, 'backup_*.zip')):
        try:
            stat = os.stat(fpath)
            backups.append({
                'filename': os.path.basename(fpath),
                'size': stat.st_size,
                'size_fmt': _fmt_size(stat.st_size),
                'created': datetime.datetime.fromtimestamp(stat.st_mtime),
            })
        except Exception:
            pass
    backups.sort(key=lambda b: b['created'], reverse=True)
    return backups


def _fmt_size(nbytes):
    """Format byte count as human-readable string."""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


if __name__ == '__main__':
    dry = '--dry' in sys.argv
    result = run_backup(dry_run=dry)
    if result:
        print(f"\nBackup saved to: {result}")
    elif not dry:
        print("\nBackup failed! Check backup.log for details.")
        sys.exit(1)
