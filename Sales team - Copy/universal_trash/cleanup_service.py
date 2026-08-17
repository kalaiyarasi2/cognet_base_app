import os
import time
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from .config import TRASH_ROOT_PATH, TRASH_RETENTION_DAYS, CLEANUP_INTERVAL_HOURS
from .trash_manager import logger


def perform_cleanup():
    """
    Synchronous function that scans the universal trash directory, deletes files older than
    TRASH_RETENTION_DAYS, and removes empty directories.
    """
    logger.info("Universal Trash Cleanup Started")
    
    trash_root = Path(TRASH_ROOT_PATH)
    if not trash_root.exists():
        logger.info(f"Trash root {trash_root} does not exist. Skipping cleanup.")
        return

    now = datetime.now()
    cutoff_time = now - timedelta(days=TRASH_RETENTION_DAYS)
    
    files_scanned = 0
    files_deleted = 0
    files_skipped = 0
    errors = 0

    # First pass: iterate files (bottom-up is not strictly necessary for file deletion,
    # but we'll use os.walk to get everything easily)
    for root, dirs, files in os.walk(trash_root, topdown=False):
        current_dir = Path(root)
        
        for file in files:
            files_scanned += 1
            file_path = current_dir / file
            
            try:
                # Check modification time
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                
                if mtime < cutoff_time:
                    file_path.unlink()
                    files_deleted += 1
                    logger.debug(f"Deleted old trash file: {file_path}")
                else:
                    files_skipped += 1
            except Exception as e:
                logger.error(f"Failed to delete trash file {file_path}: {e}")
                errors += 1
        
        # Now check if the directory is empty and is not the root TRASH_ROOT_PATH itself
        if current_dir != trash_root:
            try:
                if not any(current_dir.iterdir()):
                    current_dir.rmdir()
                    logger.debug(f"Removed empty trash directory: {current_dir}")
            except Exception as e:
                # Directory not empty or locked
                pass

    logger.info(f"Files Scanned: {files_scanned}")
    logger.info(f"Files Deleted: {files_deleted}")
    logger.info(f"Files Skipped: {files_skipped}")
    if errors > 0:
        logger.warning(f"Errors encountered during cleanup: {errors}")
    logger.info("Cleanup Completed")


async def cleanup_loop():
    """
    Background asyncio task that periodically runs the cleanup logic.
    """
    logger.info(f"Universal Trash background cleanup service started. Interval: {CLEANUP_INTERVAL_HOURS}h, Retention: {TRASH_RETENTION_DAYS}d")
    
    while True:
        try:
            # We run the synchronous cleanup in a thread to avoid blocking the asyncio event loop
            await asyncio.to_thread(perform_cleanup)
        except asyncio.CancelledError:
            logger.info("Universal Trash cleanup task cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in Universal Trash cleanup loop: {e}")
        
        # Sleep for the configured interval
        await asyncio.sleep(CLEANUP_INTERVAL_HOURS * 3600)

def start_cleanup_service():
    """
    Spawns the background asyncio task for periodic cleanup.
    Returns the asyncio.Task.
    """
    return asyncio.create_task(cleanup_loop())
