import os
import shutil
import logging
import traceback
from datetime import datetime
from pathlib import Path

from .config import TRASH_ROOT_PATH

# Configure a module logger
logger = logging.getLogger("universal_trash")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] Universal Trash [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def move_to_trash(file_path: str | Path, module_name: str = "general", file_type: str = "temp") -> bool:
    """
    Safely moves a file to the centralized Universal Trash Folder instead of deleting it outright.
    This replaces os.remove() or Path.unlink().

    Args:
        file_path (str | Path): The path of the file to remove/move to trash.
        module_name (str): The name of the module originating this request (e.g., "workflow", "gpu", "extractor").
        file_type (str): The logical type of file (e.g., "input", "output", "extracted", "temp").

    Returns:
        bool: True if the file was successfully moved to trash, False otherwise.
    """
    try:
        source_path = Path(file_path)
        
        # If file doesn't exist, we consider the deletion successfully "handled" (no-op)
        if not source_path.exists():
            return True

        if source_path.is_dir():
            logger.warning(f"move_to_trash called on directory '{source_path}', but only files are supported. Skipping.")
            return False

        # Build target destination: TRASH_ROOT_PATH / module_name / YYYY-MM-DD / file_type
        today_str = datetime.now().strftime("%Y-%m-%d")
        dest_dir = Path(TRASH_ROOT_PATH) / module_name / today_str / file_type
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Handle filename collisions in trash by appending a timestamp if needed
        dest_path = dest_dir / source_path.name
        if dest_path.exists():
            timestamp_str = datetime.now().strftime("%H%M%S")
            dest_path = dest_dir / f"{source_path.stem}_{timestamp_str}{source_path.suffix}"

        # Attempt to move the file
        shutil.move(str(source_path), str(dest_path))
        logger.debug(f"File moved to trash: {source_path} -> {dest_path}")
        return True

    except PermissionError:
        logger.error(f"Permission denied moving '{file_path}' to trash. File might be locked or in use.")
        return False
    except Exception as e:
        logger.error(f"Failed to move '{file_path}' to trash: {e}")
        logger.error(traceback.format_exc())
        return False
