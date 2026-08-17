import os
from pathlib import Path
from dotenv import load_dotenv

# We assume this is loaded inside the Sales team - Copy workspace
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(WORKSPACE_DIR / ".env")

# Configure from environment or use default
TRASH_ROOT_PATH = os.getenv("TRASH_ROOT_PATH", str(WORKSPACE_DIR / "universal_trash_bin"))
TRASH_RETENTION_DAYS = int(os.getenv("TRASH_RETENTION_DAYS", "7"))
CLEANUP_INTERVAL_HOURS = int(os.getenv("CLEANUP_INTERVAL_HOURS", "24"))

# Ensure the root trash path exists
Path(TRASH_ROOT_PATH).mkdir(parents=True, exist_ok=True)
