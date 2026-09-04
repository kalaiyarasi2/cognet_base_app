from .trash_manager import move_to_trash
from .cleanup_service import start_cleanup_service, perform_cleanup
start_scheduled_cleanup = start_cleanup_service

__all__ = [
    "move_to_trash",
    "start_cleanup_service",
    "start_scheduled_cleanup",
    "perform_cleanup"
]
