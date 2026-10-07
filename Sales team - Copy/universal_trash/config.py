import os
from pathlib import Path
from dotenv import load_dotenv

# We assume this is loaded inside the Sales team - Copy workspace
WORKSPACE_DIR = Path(__file__).resolve().parent.parent

# Look for .env in WORKSPACE_DIR, then its parent
env_path = WORKSPACE_DIR / ".env"
if not env_path.exists():
    env_path = WORKSPACE_DIR.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Configure from environment or use default
TRASH_ROOT_PATH = os.getenv("TRASH_ROOT_PATH", str(WORKSPACE_DIR / "universal_trash_bin"))

# Support legacy TRASH_RETENTION_DAYS as a fallback for hours
_legacy_hours = int(os.getenv("TRASH_RETENTION_DAYS", "7")) * 24
TRASH_RETENTION_HOURS = int(os.getenv("TRASH_RETENTION_HOURS", str(_legacy_hours)))

CLEANUP_INTERVAL_HOURS = int(os.getenv("CLEANUP_INTERVAL_HOURS", "1"))
CLEANUP_DRY_RUN = os.getenv("CLEANUP_DRY_RUN", "true").lower() == "true"

_watch_dirs_str = os.getenv("CLEANUP_WATCH_DIRS", "")
CLEANUP_WATCH_DIRS = [WORKSPACE_DIR / p.strip() for p in _watch_dirs_str.split(";") if p.strip()]

_protected_ext_str = os.getenv("CLEANUP_PROTECTED_EXT", ".py;.db;.db-wal;.db-shm;.env;.gitkeep")
CLEANUP_PROTECTED_EXT = {ext.strip().lower() for ext in _protected_ext_str.split(";") if ext.strip()}

# Ensure the root trash path exists
Path(TRASH_ROOT_PATH).mkdir(parents=True, exist_ok=True)

