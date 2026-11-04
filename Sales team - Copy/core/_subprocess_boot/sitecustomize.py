"""
Auto-loaded by Python at startup (via PYTHONPATH) in every child subprocess
spawned by the unified server (Payroll, Renewal, RPVE phase 1/2, Invoice-to-Excel...).
Turns on OpenAI prompt caching without editing those scripts. Never raises.
"""
try:
    import os as _os
    import sys as _sys

    _ws = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    if _ws not in _sys.path:
        _sys.path.append(_ws)

    from core.prompt_cache_manager import enable_global_prompt_caching as _pcb_enable
    _pcb_enable()
except Exception:
    pass
