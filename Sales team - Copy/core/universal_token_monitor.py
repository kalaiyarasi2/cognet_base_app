"""
core/universal_token_monitor.py
================================
Universal Token Monitor — One module to track ALL OpenAI API usage across every POC.

Usage (add 2 lines after every client.chat.completions.create(...) call):
    from core.universal_token_monitor import track_usage
    track_usage(response.usage, model="gpt-4o", poc_name="my-poc", file_name="doc.pdf", step_name="extraction")

This module NEVER raises exceptions to the caller — all errors are logged silently.
"""

import os
import sys
import json
import time
import sqlite3
import threading
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Paths — always relative to the workspace root (Sales team - Copy/)
# ──────────────────────────────────────────────────────────────────────────────
_THIS_FILE   = Path(__file__).resolve()
_WORKSPACE   = _THIS_FILE.parent.parent                # Sales team - Copy/
_MONITOR_DIR = _WORKSPACE / "monitor"
_DB_PATH     = _MONITOR_DIR / "universal_token_usage.db"
_JSON_PATH   = _MONITOR_DIR / "universal_token_summary.json"

# ──────────────────────────────────────────────────────────────────────────────
# Model Pricing (USD per token — OpenAI & Anthropic Claude)
# ──────────────────────────────────────────────────────────────────────────────
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # OpenAI Models
    "gpt-4o":          {"prompt": 2.50  / 1_000_000, "completion": 10.00 / 1_000_000},
    "gpt-4o-mini":     {"prompt": 0.15  / 1_000_000, "completion": 0.60  / 1_000_000},
    "gpt-4-turbo":     {"prompt": 10.00 / 1_000_000, "completion": 30.00 / 1_000_000},
    "gpt-4":           {"prompt": 30.00 / 1_000_000, "completion": 60.00 / 1_000_000},
    "gpt-3.5-turbo":   {"prompt": 0.50  / 1_000_000, "completion": 1.50  / 1_000_000},
    "o1":              {"prompt": 15.00 / 1_000_000, "completion": 60.00 / 1_000_000},
    "o1-mini":         {"prompt": 3.00  / 1_000_000, "completion": 12.00 / 1_000_000},
    "o3":              {"prompt": 10.00 / 1_000_000, "completion": 40.00 / 1_000_000},
    "gpt-5.6":         {"prompt": 2.50  / 1_000_000, "completion": 10.00 / 1_000_000},

    # Anthropic Claude Models
    "claude-3-5-sonnet": {"prompt": 3.00  / 1_000_000, "completion": 15.00 / 1_000_000},
    "claude-3-7-sonnet": {"prompt": 3.00  / 1_000_000, "completion": 15.00 / 1_000_000},
    "claude-3-5-haiku":  {"prompt": 0.80  / 1_000_000, "completion": 4.00  / 1_000_000},
    "claude-3-haiku":    {"prompt": 0.25  / 1_000_000, "completion": 1.25  / 1_000_000},
    "claude-3-opus":     {"prompt": 15.00 / 1_000_000, "completion": 75.00 / 1_000_000},
    "claude-opus-5-5":   {"prompt": 15.00 / 1_000_000, "completion": 75.00 / 1_000_000},
    "claude-opus":       {"prompt": 15.00 / 1_000_000, "completion": 75.00 / 1_000_000},
    "claude-sonnet":     {"prompt": 3.00  / 1_000_000, "completion": 15.00 / 1_000_000},
    "claude-haiku":      {"prompt": 0.80  / 1_000_000, "completion": 4.00  / 1_000_000},

    "default":           {"prompt": 2.50  / 1_000_000, "completion": 10.00 / 1_000_000},
}

# Placeholder file names that should always inherit the active document's real filename
_PLACEHOLDER_FILE_NAMES = {
    "unknown",
    "gpu_doc",
    "insurance_doc",
    "policy_boundary_scan",
    "document",
    "n/a",
    "none",
    "",
    "rotated_temp.pdf",
}

# Friendly sub-process step name mapping from internal function names
_FUNCTION_TO_STEP_NAME = {
    "classify_document":              "router_document_classification",
    "_identify_provider":             "router_provider_identification",
    "get_semantic_mapping":           "column_semantic_mapping",
    "extract_global_metadata":        "invoice_metadata_extraction",
    "ai_find_header":                 "table_header_detection",
    "run_identification_extractor":   "id_document_extraction",
    "_detect_claim_numbers_ai":       "claim_number_detection",
    "detect_claim_id_patterns":       "claim_number_detection",
    "_analyze_document_format":       "document_format_analysis",
    "analyze_document_format":        "document_format_analysis",
    "_smart_verify_format":           "format_layout_verification",
    "_extract_all_claims":            "chunk_claims_extraction",
    "_extract_missing_claims_by_number": "claims_recovery_correction",
    "_extract_single_claim":          "single_claim_extraction",
    "_extract_text_via_vision":       "vision_ocr_extraction",
    "_chunk_text_dynamically":        "dynamic_chunking_analysis",
    "scan_window":                    "policy_boundary_scan",
    "detect_policy_boundaries":       "policy_boundary_scan",
}

# ──────────────────────────────────────────────────────────────────────────────
# Logger (writes to monitor/token_monitor.log — silent, never crashes)
# ──────────────────────────────────────────────────────────────────────────────
_log = logging.getLogger("universal_token_monitor")
if not _log.handlers:
    _log.setLevel(logging.INFO)
    try:
        _MONITOR_DIR.mkdir(parents=True, exist_ok=True)
        _fh = logging.FileHandler(str(_MONITOR_DIR / "token_monitor.log"), encoding="utf-8")
        _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        _log.addHandler(_fh)
    except Exception:
        pass  # If log file fails, still proceed silently

# ──────────────────────────────────────────────────────────────────────────────
# Thread-safe DB lock & Cross-Thread / Cross-Process Dynamic Context
# ──────────────────────────────────────────────────────────────────────────────
_db_lock = threading.Lock()
_context_local = threading.local()
_GLOBAL_ACTIVE_CONTEXT: Dict[str, Optional[str]] = {
    "file_name": None,
    "session_id": None,
    "poc_name": None,
}
_AUTO_FILE_SESSIONS: Dict[str, Dict[str, Any]] = {}
_SESSION_COUNTER = 0


def _is_placeholder_filename(name: Optional[str]) -> bool:
    if not name:
        return True
    cleaned = os.path.basename(str(name).strip()).lower()
    if cleaned in _PLACEHOLDER_FILE_NAMES or cleaned.startswith("rotated_temp"):
        return True
    return False


def _generate_unique_session_id(base_ts: Optional[str] = None) -> str:
    """Generate a unique date-time session ID for a file processing run."""
    global _SESSION_COUNTER
    _SESSION_COUNTER += 1
    ts = base_ts or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    # Ensure uniqueness even if the same file is triggered twice within the same second
    ms = int((time.time() % 1) * 1000)
    return f"{ts} [{ms:03d}-{_SESSION_COUNTER}]"


def start_file_session(
    file_name: str,
    poc_name: Optional[str] = None,
    session_id: Optional[str] = None
) -> str:
    """
    Start a new isolated processing session for a file run using the current UTC date-time.
    Ensures that re-processing the same file creates a separate log entry and groups
    all sub-process LLM calls (across threads and subprocesses) under this file run.
    """
    clean_file = os.path.basename(str(file_name).strip()) if file_name else "unknown"
    sid = session_id or _generate_unique_session_id()
    set_context(file_name=clean_file, session_id=sid, poc_name=poc_name)
    _AUTO_FILE_SESSIONS[clean_file] = {
        "session_id": sid,
        "last_ts": time.time(),
        "poc_name": poc_name,
    }
    return sid


def set_context(file_name: Optional[str] = None, session_id: Optional[str] = None, poc_name: Optional[str] = None):
    """Dynamically set active file and session context across thread, process, and child subprocesses."""
    if file_name is not None:
        clean_fn = os.path.basename(str(file_name).strip())
        if not _is_placeholder_filename(clean_fn):
            _context_local.file_name = clean_fn
            _GLOBAL_ACTIVE_CONTEXT["file_name"] = clean_fn
            os.environ["COGNET_ACTIVE_FILE_NAME"] = clean_fn
    if session_id is not None:
        _context_local.session_id = session_id
        _GLOBAL_ACTIVE_CONTEXT["session_id"] = session_id
        os.environ["COGNET_ACTIVE_SESSION_ID"] = session_id
    if poc_name is not None:
        _context_local.poc_name = poc_name
        _GLOBAL_ACTIVE_CONTEXT["poc_name"] = poc_name
        os.environ["COGNET_ACTIVE_POC_NAME"] = poc_name


def get_context() -> Dict[str, Optional[str]]:
    """Get active context (checks thread-local, process-global for worker threads, and env for subprocesses)."""
    fn = (
        getattr(_context_local, "file_name", None)
        or _GLOBAL_ACTIVE_CONTEXT.get("file_name")
        or os.environ.get("COGNET_ACTIVE_FILE_NAME")
    )
    sid = (
        getattr(_context_local, "session_id", None)
        or _GLOBAL_ACTIVE_CONTEXT.get("session_id")
        or os.environ.get("COGNET_ACTIVE_SESSION_ID")
    )
    poc = (
        getattr(_context_local, "poc_name", None)
        or _GLOBAL_ACTIVE_CONTEXT.get("poc_name")
        or os.environ.get("COGNET_ACTIVE_POC_NAME")
    )
    return {
        "file_name": fn,
        "session_id": sid,
        "poc_name": poc,
    }


def clear_context():
    """Clear active thread and process context."""
    _context_local.file_name = None
    _context_local.session_id = None
    _context_local.poc_name = None
    _GLOBAL_ACTIVE_CONTEXT["file_name"] = None
    _GLOBAL_ACTIVE_CONTEXT["session_id"] = None
    _GLOBAL_ACTIVE_CONTEXT["poc_name"] = None
    os.environ.pop("COGNET_ACTIVE_FILE_NAME", None)
    os.environ.pop("COGNET_ACTIVE_SESSION_ID", None)
    os.environ.pop("COGNET_ACTIVE_POC_NAME", None)


def _inspect_stack_for_context() -> Dict[str, Optional[str]]:
    """Walk the Python call stack to recover real file_name and sub-process step_name."""
    found_file: Optional[str] = None
    found_step: Optional[str] = None
    ignored_funcs = {
        "track_usage", "_tm", "_track_universal", "_inspect_stack_for_context",
        "cached_chat_completion", "_cached_sync_create", "_cached_async_create",
        "call_llm_deterministically", "create",
    }
    try:
        frame = sys._getframe(1)
        while frame:
            func_name = frame.f_code.co_name
            co_file = frame.f_code.co_filename or ""
            if "universal_token_monitor" not in co_file and "prompt_cache_manager" not in co_file and "openai" not in co_file.lower():
                if not found_step and func_name and func_name not in ignored_funcs and not func_name.startswith("<"):
                    found_step = _FUNCTION_TO_STEP_NAME.get(func_name, func_name.lstrip("_"))

                f_locals = frame.f_locals or {}
                if not found_file:
                    # Check `self.current_filename` first
                    self_obj = f_locals.get("self")
                    if self_obj is not None:
                        cf = getattr(self_obj, "current_filename", None)
                        if cf and not _is_placeholder_filename(cf):
                            found_file = os.path.basename(str(cf))
                    if not found_file:
                        for key in ("original_pdf_path", "safe_filename", "file_name", "filename", "pdf_path", "file_path", "working_path"):
                            val = f_locals.get(key)
                            if val and isinstance(val, (str, Path)):
                                candidate = os.path.basename(str(val))
                                if not _is_placeholder_filename(candidate):
                                    found_file = candidate
                                    break
            if found_file and found_step:
                break
            frame = frame.f_back
    except Exception:
        pass
    return {"file_name": found_file, "step_name": found_step}


# ──────────────────────────────────────────────────────────────────────────────
# DB Initialization & Historical Run Date-Time Migration
# ──────────────────────────────────────────────────────────────────────────────
def _parse_utc_timestamp(ts_str: str) -> Optional[float]:
    if not ts_str:
        return None
    clean = str(ts_str).replace(" UTC", "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(clean[:19], fmt).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            pass
    return None


def _migrate_historical_runs_by_datetime(conn: sqlite3.Connection):
    """
    One-time migration that splits cumulative historical rows into per-run date-time
    sessions and attaches sub-process calls (insurance_doc, gpu_doc, policy_boundary_scan)
    to the parent file run that initiated them.
    """
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_monitor_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("SELECT value FROM token_monitor_meta WHERE key = 'migrated_datetime_runs_v2'")
    if cursor.fetchone():
        return

    cursor.execute("""
        SELECT id, timestamp, poc_name, file_name, step_name, model,
               prompt_tokens, COALESCE(cached_tokens, 0) as cached_tokens,
               completion_tokens, total_tokens, cost_usd, session_id
        FROM token_calls
        ORDER BY id ASC
    """)
    all_calls = cursor.fetchall()
    if not all_calls:
        cursor.execute("INSERT OR REPLACE INTO token_monitor_meta (key, value) VALUES ('migrated_datetime_runs_v2', '1')")
        conn.commit()
        return

    # Track active file run while scanning chronological call history
    active_run: Dict[str, Any] = {
        "file_name": None,
        "session_id": None,
        "poc_name": None,
        "last_epoch": None,
    }
    file_runs: Dict[str, Dict[str, Any]] = {}
    used_sids = set()

    def make_unique_sid(ts_val: str) -> str:
        base = ts_val or "unknown_time"
        candidate = base
        idx = 2
        while candidate in used_sids:
            candidate = f"{base} (#{idx})"
            idx += 1
        used_sids.add(candidate)
        return candidate

    call_updates = []
    session_poc_upgrade: Dict[tuple, str] = {}

    for row in all_calls:
        cid, ts, poc, fname, sname, model, p_tok, c_tok, comp_tok, tot_tok, cost, sid = row
        epoch = _parse_utc_timestamp(ts)
        is_placeholder = _is_placeholder_filename(fname)
        model_l = (model or "").lower()

        # Infer descriptive step name for historical generic 'extraction' rows
        new_step = sname or "extraction"
        if new_step in ("extraction", "llm_call"):
            if poc == "Gpu_server" and "mini" in model_l and (comp_tok or 0) <= 30:
                new_step = "router_document_classification"
            elif poc == "Insurance_pdf_extractor" and is_placeholder:
                if 3700 <= (p_tok or 0) <= 4600:
                    new_step = "claim_number_detection"
                elif 2500 <= (p_tok or 0) < 3700:
                    new_step = "document_format_analysis"
                else:
                    new_step = "insurance_analysis_step"
            elif poc == "Gpu_server" and is_placeholder:
                if (p_tok or 0) < 4200:
                    new_step = "document_format_analysis"
                else:
                    new_step = "schema_data_extraction"

        is_router_start = (
            not is_placeholder
            and poc == "Gpu_server"
            and "mini" in model_l
            and (comp_tok or 0) <= 30
        )

        if is_placeholder:
            # Sub-process call: attach to the currently active file run if within 10 minutes
            if (
                active_run["file_name"]
                and active_run["session_id"]
                and (epoch is None or active_run["last_epoch"] is None or (epoch - active_run["last_epoch"]) <= 600)
            ):
                resolved_file = active_run["file_name"]
                resolved_sid = active_run["session_id"]
                resolved_poc = poc if poc != "Gpu_server" else (active_run["poc_name"] or poc)
                if poc != "Gpu_server":
                    active_run["poc_name"] = poc
                    session_poc_upgrade[(resolved_file, resolved_sid)] = poc
                if epoch is not None:
                    active_run["last_epoch"] = epoch
                if resolved_file in file_runs:
                    file_runs[resolved_file]["last_epoch"] = epoch
                    file_runs[resolved_file]["poc_name"] = active_run["poc_name"]
            else:
                # Standalone placeholder call with no recent parent file
                resolved_file = fname or "unknown"
                if (
                    active_run["file_name"] == resolved_file
                    and active_run["session_id"]
                    and epoch is not None
                    and active_run["last_epoch"] is not None
                    and (epoch - active_run["last_epoch"]) <= 90
                ):
                    resolved_sid = active_run["session_id"]
                    active_run["last_epoch"] = epoch
                else:
                    resolved_sid = make_unique_sid(ts)
                    active_run = {
                        "file_name": resolved_file,
                        "session_id": resolved_sid,
                        "poc_name": poc,
                        "last_epoch": epoch,
                    }
                resolved_poc = poc
        else:
            # Real filename
            resolved_file = fname
            prev = file_runs.get(resolved_file)
            # Determine if this call continues an ongoing run of the same file or starts a new run
            if (
                prev
                and not is_router_start
                and epoch is not None
                and prev.get("last_epoch") is not None
                and (epoch - prev["last_epoch"]) <= 120
            ):
                resolved_sid = prev["session_id"]
                prev["last_epoch"] = epoch
                if poc != "Gpu_server":
                    prev["poc_name"] = poc
                    session_poc_upgrade[(resolved_file, resolved_sid)] = poc
                resolved_poc = prev.get("poc_name") or poc
            else:
                resolved_sid = make_unique_sid(ts)
                file_runs[resolved_file] = {
                    "session_id": resolved_sid,
                    "last_epoch": epoch,
                    "poc_name": poc,
                }
                resolved_poc = poc

            active_run = {
                "file_name": resolved_file,
                "session_id": resolved_sid,
                "poc_name": resolved_poc,
                "last_epoch": epoch,
            }

        call_updates.append((resolved_poc, resolved_file, new_step, resolved_sid, cid))

    # Apply upgraded POC names so router + extractor calls in the same run share one POC
    final_updates = []
    for resolved_poc, resolved_file, new_step, resolved_sid, cid in call_updates:
        upgraded_poc = session_poc_upgrade.get((resolved_file, resolved_sid), resolved_poc)
        final_updates.append((upgraded_poc, resolved_file, new_step, resolved_sid, cid))

    cursor.executemany("""
        UPDATE token_calls
        SET poc_name = ?, file_name = ?, step_name = ?, session_id = ?
        WHERE id = ?
    """, final_updates)

    # Rebuild token_file_summary cleanly from updated token_calls
    cursor.execute("DELETE FROM token_file_summary")
    cursor.execute("""
        INSERT INTO token_file_summary (
            poc_name, file_name, session_id, total_llm_calls,
            total_prompt_tokens, total_cached_tokens, total_completion_tokens,
            total_tokens, total_cost_usd, first_seen, last_updated
        )
        SELECT
            poc_name,
            file_name,
            COALESCE(session_id, ''),
            COUNT(*) as total_llm_calls,
            SUM(COALESCE(prompt_tokens, 0)),
            SUM(COALESCE(cached_tokens, 0)),
            SUM(COALESCE(completion_tokens, 0)),
            SUM(COALESCE(total_tokens, 0)),
            SUM(COALESCE(cost_usd, 0.0)),
            MIN(timestamp),
            MAX(timestamp)
        FROM token_calls
        GROUP BY poc_name, file_name, COALESCE(session_id, '')
        ORDER BY MIN(id) ASC
    """)

    cursor.execute("INSERT OR REPLACE INTO token_monitor_meta (key, value) VALUES ('migrated_datetime_runs_v2', '1')")
    conn.commit()


def _init_db():
    """Create the universal_token_usage.db and its tables if they don't exist."""
    _MONITOR_DIR.mkdir(parents=True, exist_ok=True)
    with _db_lock:
        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS token_calls (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp         TEXT NOT NULL,
                poc_name          TEXT NOT NULL,
                file_name         TEXT,
                step_name         TEXT,
                model             TEXT,
                prompt_tokens     INTEGER DEFAULT 0,
                cached_tokens     INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens      INTEGER DEFAULT 0,
                cost_usd          REAL    DEFAULT 0.0,
                session_id        TEXT
            )
        """)
        # Aggregated view per POC + file + session_id (1 row per file processing run)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS token_file_summary (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                poc_name          TEXT NOT NULL,
                file_name         TEXT NOT NULL,
                session_id        TEXT,
                total_llm_calls   INTEGER DEFAULT 0,
                total_prompt_tokens     INTEGER DEFAULT 0,
                total_cached_tokens     INTEGER DEFAULT 0,
                total_completion_tokens INTEGER DEFAULT 0,
                total_tokens      INTEGER DEFAULT 0,
                total_cost_usd    REAL    DEFAULT 0.0,
                first_seen        TEXT,
                last_updated      TEXT,
                UNIQUE(poc_name, file_name, session_id)
            )
        """)
        # Safe migrations for existing databases
        for alter_sql in (
            "ALTER TABLE token_calls ADD COLUMN cached_tokens INTEGER DEFAULT 0",
            "ALTER TABLE token_file_summary ADD COLUMN total_cached_tokens INTEGER DEFAULT 0",
        ):
            try:
                cursor.execute(alter_sql)
            except Exception:
                pass
        conn.commit()
        try:
            _migrate_historical_runs_by_datetime(conn)
        except Exception as mig_err:
            _log.warning("Historical migration skipped: %s", mig_err)
        conn.close()


# Initialize DB and connect prompt_cache_manager when module is first imported
try:
    _init_db()
except Exception as _init_err:
    _log.warning("DB init failed: %s", _init_err)

try:
    if str(_THIS_FILE.parent) not in sys.path:
        sys.path.insert(0, str(_THIS_FILE.parent))
    from prompt_cache_manager import enable_global_prompt_caching as _enable_cache
    _enable_cache()
except Exception:
    pass


# ──────────────────────────────────────────────────────────────────────────────
# Cost Calculator
# ──────────────────────────────────────────────────────────────────────────────
def _calculate_cost(prompt_tokens: int, completion_tokens: int, model: str, cached_tokens: int = 0) -> float:
    """Calculate USD cost based on model pricing (OpenAI + Anthropic Claude), applying 50% discount on cached tokens."""
    model_clean = (model or "").lower().strip()
    model_base = model_clean.split("-20")[0]
    rates = MODEL_PRICING.get(model_base)
    if not rates:
        for key, price in MODEL_PRICING.items():
            if key != "default" and key in model_clean:
                rates = price
                break
    if not rates:
        rates = MODEL_PRICING["default"]
    
    uncached_prompt = max(0, prompt_tokens - cached_tokens)
    prompt_cost = (uncached_prompt * rates["prompt"]) + (cached_tokens * rates["prompt"] * 0.5)
    completion_cost = completion_tokens * rates["completion"]
    cost = prompt_cost + completion_cost
    return round(cost, 8)


# ──────────────────────────────────────────────────────────────────────────────
# Write to DB
# ──────────────────────────────────────────────────────────────────────────────
def _write_to_db(
    poc_name: str, file_name: str, step_name: str, model: str,
    prompt_tokens: int, completion_tokens: int, total_tokens: int,
    cost_usd: float, session_id: Optional[str], timestamp: str,
    cached_tokens: int = 0
):
    """Write one LLM call entry to the DB and update the per-run file summary."""
    try:
        with _db_lock:
            conn = sqlite3.connect(str(_DB_PATH))
            cursor = conn.cursor()

            sid = session_id or timestamp

            # Unify POC name within the same (file_name, session_id) run so router classification
            # or environmental leaks do not split a single file-run into multiple rows.
            cursor.execute("""
                SELECT id, poc_name FROM token_file_summary
                WHERE file_name = ? AND session_id = ?
                LIMIT 1
            """, (file_name, sid))
            existing_row = cursor.fetchone()
            if existing_row:
                existing_id, existing_poc = existing_row
                generic_names = {"Gpu_server", "general_poc", "unknown", ""}
                if existing_poc in generic_names and poc_name and poc_name not in generic_names:
                    # Upgrade session's POC from generic router to specific extractor
                    cursor.execute("""
                        UPDATE token_file_summary SET poc_name = ? WHERE id = ?
                    """, (poc_name, existing_id))
                    cursor.execute("""
                        UPDATE token_calls SET poc_name = ? WHERE file_name = ? AND session_id = ?
                    """, (poc_name, file_name, sid))
                elif existing_poc and existing_poc not in generic_names:
                    # Keep the established POC for all subsequent calls in this run
                    poc_name = existing_poc

            # 1. Insert individual call record
            cursor.execute("""
                INSERT INTO token_calls
                  (timestamp, poc_name, file_name, step_name, model,
                   prompt_tokens, cached_tokens, completion_tokens, total_tokens, cost_usd, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, poc_name, file_name, step_name, model,
                  prompt_tokens, cached_tokens, completion_tokens, total_tokens, cost_usd, sid))

            # 2. Upsert file-level summary for this specific run (session_id)
            cursor.execute("""
                INSERT INTO token_file_summary
                  (poc_name, file_name, session_id, total_llm_calls,
                   total_prompt_tokens, total_cached_tokens, total_completion_tokens, total_tokens,
                   total_cost_usd, first_seen, last_updated)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(poc_name, file_name, session_id) DO UPDATE SET
                   total_llm_calls          = total_llm_calls + 1,
                   total_prompt_tokens      = total_prompt_tokens + excluded.total_prompt_tokens,
                   total_cached_tokens      = COALESCE(total_cached_tokens, 0) + excluded.total_cached_tokens,
                   total_completion_tokens  = total_completion_tokens + excluded.total_completion_tokens,
                   total_tokens             = total_tokens + excluded.total_tokens,
                   total_cost_usd           = total_cost_usd + excluded.total_cost_usd,
                   last_updated             = excluded.last_updated
            """, (poc_name, file_name, sid,
                  prompt_tokens, cached_tokens, completion_tokens, total_tokens, cost_usd,
                  timestamp, timestamp))

            conn.commit()
            conn.close()
    except Exception as e:
        _log.warning("DB write failed: %s", e)


# ──────────────────────────────────────────────────────────────────────────────
# JSON Summary Update (human-readable flat file)
# ──────────────────────────────────────────────────────────────────────────────
def _update_json_summary(
    poc_name: str, file_name: str, step_name: str, model: str,
    prompt_tokens: int, completion_tokens: int, total_tokens: int,
    cost_usd: float, timestamp: str, cached_tokens: int = 0
):
    """Append entry to the JSON summary file for easy human inspection."""
    try:
        summary = {
            "last_updated": "",
            "grand_total_cost_usd": 0.0,
            "grand_total_tokens": 0,
            "grand_total_cached_tokens": 0,
            "grand_total_calls": 0,
            "pocs": {}
        }
        if _JSON_PATH.exists():
            try:
                with open(_JSON_PATH, "r", encoding="utf-8") as f:
                    summary = json.load(f)
            except Exception:
                pass

        # Update grand totals
        summary["grand_total_cost_usd"]      = round(summary.get("grand_total_cost_usd", 0.0) + cost_usd, 8)
        summary["grand_total_tokens"]        = summary.get("grand_total_tokens", 0) + total_tokens
        summary["grand_total_cached_tokens"] = summary.get("grand_total_cached_tokens", 0) + cached_tokens
        summary["grand_total_calls"]         = summary.get("grand_total_calls", 0) + 1
        summary["last_updated"]              = timestamp

        # Update per-POC section
        pocs = summary.setdefault("pocs", {})
        poc = pocs.setdefault(poc_name, {
            "total_files_processed": 0,
            "total_llm_calls": 0,
            "total_tokens": 0,
            "total_cached_tokens": 0,
            "total_cost_usd": 0.0,
            "files": {}
        })
        poc["total_llm_calls"]      = poc.get("total_llm_calls", 0) + 1
        poc["total_tokens"]         = poc.get("total_tokens", 0) + total_tokens
        poc["total_cached_tokens"]  = poc.get("total_cached_tokens", 0) + cached_tokens
        poc["total_cost_usd"]       = round(poc.get("total_cost_usd", 0.0) + cost_usd, 8)

        # Per-file section inside POC
        files = poc.setdefault("files", {})
        if file_name not in files:
            poc["total_files_processed"] = poc.get("total_files_processed", 0) + 1
            files[file_name] = {
                "total_llm_calls": 0,
                "total_tokens": 0,
                "total_cached_tokens": 0,
                "total_cost_usd": 0.0,
                "calls_breakdown": []
            }
        file_entry = files[file_name]
        file_entry["total_llm_calls"]     = file_entry.get("total_llm_calls", 0) + 1
        file_entry["total_tokens"]        = file_entry.get("total_tokens", 0) + total_tokens
        file_entry["total_cached_tokens"] = file_entry.get("total_cached_tokens", 0) + cached_tokens
        file_entry["total_cost_usd"]      = round(file_entry.get("total_cost_usd", 0.0) + cost_usd, 8)
        file_entry.setdefault("calls_breakdown", []).append({
            "step": step_name,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
            "formatted_cost": f"${cost_usd:.6f}",
            "timestamp": timestamp
        })

        with open(_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
    except Exception as e:
        _log.warning("JSON summary update failed: %s", e)


# ──────────────────────────────────────────────────────────────────────────────
# PUBLIC API — track_usage()
# ──────────────────────────────────────────────────────────────────────────────
def track_usage(
    response_usage: Any,
    model: str = "gpt-4o",
    poc_name: str = "unknown",
    file_name: str = "unknown",
    step_name: str = "llm_call",
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Track one OpenAI/Anthropic LLM call. Call this right after every
    client.chat.completions.create(...).

    Automatically resolves placeholder filenames ('insurance_doc', 'gpu_doc',
    'policy_boundary_scan', 'unknown') to the active document filename, infers
    descriptive sub-process step names from the call stack, and groups all
    sub-process calls of a single file execution under a unique date-time session_id.
    """
    try:
        # Prevent duplicate tracking if cached_chat_completion already tracked this usage object
        if response_usage is not None and getattr(response_usage, "_tracked_result", None) is not None:
            return getattr(response_usage, "_tracked_result")

        # ── Dynamically inherit context & inspect stack for sub-processes ────
        ctx = get_context()
        stack_info = _inspect_stack_for_context()

        if _is_placeholder_filename(file_name):
            if ctx.get("file_name") and not _is_placeholder_filename(ctx.get("file_name")):
                file_name = ctx["file_name"]  # type: ignore[assignment]
            elif stack_info.get("file_name"):
                file_name = stack_info["file_name"]  # type: ignore[assignment]
        else:
            file_name = os.path.basename(str(file_name).strip())
            if poc_name == "INVOICE_EXCEL" and file_name.lower().endswith(".png") and "_p" in file_name.lower():
                import re as _re
                file_name = _re.sub(r"_p\d+\.png$", ".pdf", file_name, flags=_re.IGNORECASE)
            # Update global active filename so subsequent helper calls inherit it
            _GLOBAL_ACTIVE_CONTEXT["file_name"] = file_name
            os.environ["COGNET_ACTIVE_FILE_NAME"] = file_name

        # Resolve descriptive sub-process step_name if generic
        if (not step_name or step_name in ("extraction", "llm_call")) and stack_info.get("step_name"):
            step_name = stack_info["step_name"]  # type: ignore[assignment]

        if (not poc_name or poc_name == "unknown") and ctx.get("poc_name"):
            poc_name = ctx["poc_name"]  # type: ignore[assignment]

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        now_ts = time.time()

        # Resolve unique per-run session_id (using date-time)
        if not session_id:
            if ctx.get("session_id"):
                session_id = ctx["session_id"]
            else:
                auto_entry = _AUTO_FILE_SESSIONS.get(file_name)
                is_new_router_run = step_name in ("router_document_classification", "router_filename_classification")
                if (
                    auto_entry
                    and not is_new_router_run
                    and (now_ts - auto_entry.get("last_ts", 0)) <= 90
                ):
                    session_id = auto_entry["session_id"]
                    auto_entry["last_ts"] = now_ts
                else:
                    session_id = _generate_unique_session_id(timestamp)
                    _AUTO_FILE_SESSIONS[file_name] = {
                        "session_id": session_id,
                        "last_ts": now_ts,
                        "poc_name": poc_name,
                    }
                    _GLOBAL_ACTIVE_CONTEXT["session_id"] = session_id
                    os.environ["COGNET_ACTIVE_SESSION_ID"] = session_id

        # Refresh active session timestamp on every sub-process call
        if file_name in _AUTO_FILE_SESSIONS and _AUTO_FILE_SESSIONS[file_name].get("session_id") == session_id:
            _AUTO_FILE_SESSIONS[file_name]["last_ts"] = now_ts

        # ── Extract token counts (OpenAI & Anthropic Claude) ──────────────────
        if response_usage is None:
            prompt_tokens = completion_tokens = total_tokens = 0
        elif hasattr(response_usage, "prompt_tokens"):
            prompt_tokens     = getattr(response_usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(response_usage, "completion_tokens", 0) or 0
            total_tokens      = getattr(response_usage, "total_tokens", 0) or 0
        elif hasattr(response_usage, "input_tokens"):
            # Anthropic Claude usage object
            prompt_tokens     = getattr(response_usage, "input_tokens", 0) or 0
            completion_tokens = getattr(response_usage, "output_tokens", 0) or 0
            total_tokens      = prompt_tokens + completion_tokens
        elif isinstance(response_usage, dict):
            prompt_tokens     = response_usage.get("prompt_tokens") or response_usage.get("input_tokens") or 0
            completion_tokens = response_usage.get("completion_tokens") or response_usage.get("output_tokens") or 0
            total_tokens      = response_usage.get("total_tokens") or (prompt_tokens + completion_tokens)
        else:
            prompt_tokens = completion_tokens = total_tokens = 0

        # Extract cached tokens (OpenAI prompt caching)
        cached_tokens = 0
        if response_usage is not None:
            if hasattr(response_usage, "prompt_tokens_details") and response_usage.prompt_tokens_details:
                cached_tokens = getattr(response_usage.prompt_tokens_details, "cached_tokens", 0) or 0
            elif isinstance(response_usage, dict):
                pt_details = response_usage.get("prompt_tokens_details", {})
                if isinstance(pt_details, dict):
                    cached_tokens = pt_details.get("cached_tokens", 0) or 0

        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens

        # ── Calculate cost ───────────────────────────────────────────────────
        cost_usd = _calculate_cost(prompt_tokens, completion_tokens, model, cached_tokens=cached_tokens)

        # ── Build result dict ────────────────────────────────────────────────
        result = {
            "poc_name":          poc_name,
            "file_name":         file_name,
            "step_name":         step_name,
            "session_id":        session_id,
            "model":             model,
            "prompt_tokens":     prompt_tokens,
            "cached_tokens":     cached_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens":      total_tokens,
            "cost_usd":          cost_usd,
            "formatted_cost":    f"${cost_usd:.6f}",
            "timestamp":         timestamp,
        }

        try:
            if response_usage is not None and not isinstance(response_usage, dict):
                setattr(response_usage, "_tracked_result", result)
        except Exception:
            pass

        # ── Persist data (non-blocking — errors logged, never raised) ────────
        _write_to_db(
            poc_name, file_name, step_name, model,
            prompt_tokens, completion_tokens, total_tokens, cost_usd,
            session_id, timestamp, cached_tokens=cached_tokens
        )
        _update_json_summary(
            poc_name, file_name, step_name, model,
            prompt_tokens, completion_tokens, total_tokens, cost_usd, timestamp,
            cached_tokens=cached_tokens
        )

        _log.info(
            "[%s] file=%s | session=%s | step=%s | model=%s | tokens=%d (cached=%d) | cost=%s",
            poc_name, file_name, session_id, step_name, model, total_tokens, cached_tokens, f"${cost_usd:.6f}"
        )
        return result

    except Exception as e:
        _log.warning("track_usage failed silently: %s", e)
        return {
            "poc_name": poc_name, "file_name": file_name, "step_name": step_name,
            "model": model, "prompt_tokens": 0, "completion_tokens": 0,
            "total_tokens": 0, "cost_usd": 0.0, "formatted_cost": "$0.000000",
            "error": str(e)
        }


# ──────────────────────────────────────────────────────────────────────────────
# PUBLIC API — get_summary()
# ──────────────────────────────────────────────────────────────────────────────
def get_summary(poc_name: Optional[str] = None, file_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Read current token usage summary from DB.
    - If poc_name given: returns stats for that POC only.
    - If file_name given: returns all calls for that file.
    - If neither: returns grand totals + per-POC breakdown.
    """
    try:
        with _db_lock:
            conn = sqlite3.connect(str(_DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if file_name:
                # File-level: all step calls for this file
                cursor.execute("""
                    SELECT * FROM token_calls WHERE file_name = ?
                    ORDER BY id DESC LIMIT 200
                """, (file_name,))
                calls = [dict(r) for r in cursor.fetchall()]

                cursor.execute("""
                    SELECT * FROM token_file_summary WHERE file_name = ?
                    ORDER BY id DESC
                """, (file_name,))
                summary_rows = [dict(r) for r in cursor.fetchall()]
                conn.close()
                return {
                    "file_name": file_name,
                    "summary": summary_rows[0] if summary_rows else {},
                    "runs": summary_rows,
                    "calls": calls
                }

            elif poc_name:
                # POC-level: all file runs for this POC
                cursor.execute("""
                    SELECT * FROM token_file_summary WHERE poc_name = ?
                    ORDER BY last_updated DESC, id DESC LIMIT 500
                """, (poc_name,))
                files = [dict(r) for r in cursor.fetchall()]

                cursor.execute("""
                    SELECT
                        SUM(total_llm_calls) as total_calls,
                        SUM(total_tokens) as total_tokens,
                        SUM(COALESCE(total_cached_tokens, 0)) as total_cached_tokens,
                        SUM(total_cost_usd) as total_cost_usd,
                        COUNT(*) as total_files
                    FROM token_file_summary WHERE poc_name = ?
                """, (poc_name,))
                agg = dict(cursor.fetchone() or {})
                conn.close()
                return {"poc_name": poc_name, "aggregates": agg, "files": files}

            else:
                # Grand totals + per-POC breakdown
                cursor.execute("""
                    SELECT
                        poc_name,
                        COUNT(*) as total_files,
                        SUM(total_llm_calls) as total_calls,
                        SUM(total_tokens) as total_tokens,
                        SUM(COALESCE(total_cached_tokens, 0)) as total_cached_tokens,
                        SUM(total_cost_usd) as total_cost_usd
                    FROM token_file_summary
                    GROUP BY poc_name
                    ORDER BY total_cost_usd DESC
                """)
                poc_rows = [dict(r) for r in cursor.fetchall()]

                cursor.execute("""
                    SELECT
                        SUM(total_tokens) as grand_tokens,
                        SUM(COALESCE(total_cached_tokens, 0)) as grand_cached_tokens,
                        SUM(total_cost_usd) as grand_cost,
                        SUM(total_llm_calls) as grand_calls,
                        COUNT(DISTINCT poc_name) as total_pocs,
                        COUNT(*) as total_files
                    FROM token_file_summary
                """)
                grand = dict(cursor.fetchone() or {})
                conn.close()
                return {
                    "grand_totals": grand,
                    "per_poc": poc_rows
                }
    except Exception as e:
        _log.warning("get_summary failed: %s", e)
        return {"error": str(e)}


def _get_model_rates(model: str) -> Dict[str, float]:
    model_clean = (model or "").lower().strip()
    model_base = model_clean.split("-20")[0]
    rates = MODEL_PRICING.get(model_base)
    if not rates:
        for key, price in MODEL_PRICING.items():
            if key != "default" and key in model_clean:
                rates = price
                break
    return rates or MODEL_PRICING["default"]


def _enrich_call_cache_info(call_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures cached_tokens, uncached_prompt_tokens, and cache_savings_usd are populated (including historical rows)."""
    prompt_tokens = int(call_dict.get("prompt_tokens") or 0)
    completion_tokens = int(call_dict.get("completion_tokens") or 0)
    cached_tokens = int(call_dict.get("cached_tokens") or 0)
    cost_usd = float(call_dict.get("cost_usd") or 0.0)
    model = str(call_dict.get("model") or "gpt-4o")

    rates = _get_model_rates(model)
    uncached_full_cost = (prompt_tokens * rates["prompt"]) + (completion_tokens * rates["completion"])

    # Backfill cached_tokens for historical DB rows where cost_usd already had the 50% discount applied
    if cached_tokens == 0 and prompt_tokens >= 1024 and cost_usd > 0:
        diff = uncached_full_cost - cost_usd
        half_rate = rates["prompt"] * 0.5
        if diff > (half_rate * 64) and half_rate > 0:
            inferred = int(round(diff / half_rate))
            # OpenAI caches in 128-token increments starting at 1024
            inferred_aligned = (inferred // 64) * 64
            if 1024 <= inferred_aligned <= prompt_tokens:
                cached_tokens = inferred_aligned

    savings_usd = round(max(0.0, cached_tokens * rates["prompt"] * 0.5), 8)
    call_dict["cached_tokens"] = cached_tokens
    call_dict["uncached_prompt_tokens"] = max(0, prompt_tokens - cached_tokens)
    call_dict["cache_savings_usd"] = savings_usd
    return call_dict


# ──────────────────────────────────────────────────────────────────────────────
# PUBLIC API — get_recent_calls()
# ──────────────────────────────────────────────────────────────────────────────
def get_recent_calls(limit: int = 100, poc_name: Optional[str] = None) -> list:
    """Returns the most recent individual LLM call records for dashboard display."""
    try:
        with _db_lock:
            conn = sqlite3.connect(str(_DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if poc_name:
                cursor.execute("""
                    SELECT * FROM token_calls WHERE poc_name = ?
                    ORDER BY id DESC LIMIT ?
                """, (poc_name, limit))
            else:
                cursor.execute("""
                    SELECT * FROM token_calls ORDER BY id DESC LIMIT ?
                """, (limit,))
            rows = [_enrich_call_cache_info(dict(r)) for r in cursor.fetchall()]
            conn.close()
            return rows
    except Exception as e:
        _log.warning("get_recent_calls failed: %s", e)
        return []


def get_file_summaries(limit: int = 100, poc_name: Optional[str] = None) -> list:
    """
    Returns per-run file-level rows (1 row per file execution, uniquely identified by session_id / date-time)
    including:
    - total_llm_calls count (all sub-processes of that file run)
    - total_prompt_tokens, total_cached_tokens & total_completion_tokens
    - total_tokens & total_cost_usd
    - distinct models list (e.g. ["gpt-4o-mini", "gpt-5.5"])
    - list of nested sub-process step call records for expanding details
    """
    try:
        with _db_lock:
            conn = sqlite3.connect(str(_DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if poc_name:
                cursor.execute("""
                    SELECT * FROM token_file_summary WHERE poc_name = ?
                    ORDER BY last_updated DESC, id DESC LIMIT ?
                """, (poc_name, limit))
            else:
                cursor.execute("""
                    SELECT * FROM token_file_summary
                    ORDER BY last_updated DESC, id DESC LIMIT ?
                """, (limit,))

            file_rows = [dict(r) for r in cursor.fetchall()]

            # Enrich each file run summary with distinct models used & individual sub-process call steps
            for frow in file_rows:
                fname = frow["file_name"]
                fpoc  = frow["poc_name"]
                fsid  = frow.get("session_id")

                if fsid:
                    cursor.execute("""
                        SELECT DISTINCT model FROM token_calls
                        WHERE file_name = ? AND session_id = ?
                    """, (fname, fsid))
                    models = [r["model"] for r in cursor.fetchall() if r["model"]]
                    frow["models"] = models

                    cursor.execute("""
                        SELECT * FROM token_calls
                        WHERE file_name = ? AND session_id = ?
                        ORDER BY id ASC
                    """, (fname, fsid))
                    frow["calls"] = [_enrich_call_cache_info(dict(c)) for c in cursor.fetchall()]
                else:
                    cursor.execute("""
                        SELECT DISTINCT model FROM token_calls
                        WHERE file_name = ? AND poc_name = ?
                    """, (fname, fpoc))
                    models = [r["model"] for r in cursor.fetchall() if r["model"]]
                    frow["models"] = models

                    cursor.execute("""
                        SELECT * FROM token_calls
                        WHERE file_name = ? AND poc_name = ?
                        ORDER BY id ASC
                    """, (fname, fpoc))
                    frow["calls"] = [_enrich_call_cache_info(dict(c)) for c in cursor.fetchall()]

                frow["total_cached_tokens"] = max(
                    int(frow.get("total_cached_tokens") or 0),
                    sum(int(c.get("cached_tokens") or 0) for c in frow["calls"])
                )
                frow["total_cache_savings_usd"] = round(
                    sum(float(c.get("cache_savings_usd") or 0.0) for c in frow["calls"]),
                    8
                )

            conn.close()
            return file_rows
    except Exception as e:
        _log.warning("get_file_summaries failed: %s", e)
        return []
