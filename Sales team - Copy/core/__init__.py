# Core package initialization
from .prompt_cache_manager import (
    cached_chat_completion,
    ensure_cache_threshold,
    build_cached_messages,
    optimize_messages_for_caching,
    enable_global_prompt_caching,
    get_cache_stats
)
