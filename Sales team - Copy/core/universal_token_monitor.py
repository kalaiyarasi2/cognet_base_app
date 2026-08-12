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
import json
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
# OpenAI Pricing (USD per token — updated as of 2025)
# ──────────────────────────────────────────────────────────────────────────────
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4o":          {"prompt": 2.50  / 1_000_000, "completion": 10.00 / 1_000_000},
    "gpt-4o-mini":     {"prompt": 0.15  / 1_000_000, "completion": 0.60  / 1_000_000},
    "gpt-4-turbo":     {"prompt": 10.00 / 1_000_000, "completion": 30.00 / 1_000_000},
    "gpt-4":           {"prompt": 30.00 / 1_000_000, "completion": 60.00 / 1_000_000},
    "gpt-3.5-turbo":   {"prompt": 0.50  / 1_000_000, "completion": 1.50  / 1_000_000},
    "o1":              {"prompt": 15.00 / 1_000_000, "completion": 60.00 / 1_000_000},
    "o1-mini":         {"prompt": 3.00  / 1_000_000, "completion": 12.00 / 1_000_000},
    "o3":              {"prompt": 10.00 / 1_000_000, "completion": 40.00 / 1_000_000},
    "gpt-5.6":         {"prompt": 2.50  / 1_000_000, "completion": 10.00 / 1_000_000},
    "default":         {"prompt": 2.50  / 1_000_000, "completion": 10.00 / 1_000_000},
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
# Thread-safe DB lock
# ──────────────────────────────────────────────────────────────────────────────
_db_lock = threading.Lock()


# ──────────────────────────────────────────────────────────────────────────────
# DB Initialization
# ──────────────────────────────────────────────────────────────────────────────
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
                completion_tokens INTEGER DEFAULT 0,
                total_tokens      INTEGER DEFAULT 0,
                cost_usd          REAL    DEFAULT 0.0,
                session_id        TEXT
            )
        """)
        # Aggregated view per POC + file (for fast dashboard queries)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS token_file_summary (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                poc_name          TEXT NOT NULL,
                file_name         TEXT NOT NULL,
                session_id        TEXT,
                total_llm_calls   INTEGER DEFAULT 0,
                total_prompt_tokens     INTEGER DEFAULT 0,
                total_completion_tokens INTEGER DEFAULT 0,
                total_tokens      INTEGER DEFAULT 0,
                total_cost_usd    REAL    DEFAULT 0.0,
                first_seen        TEXT,
                last_updated      TEXT,
                UNIQUE(poc_name, file_name, session_id)
            )
        """)
        conn.commit()
        conn.close()


# Initialize DB when module is first imported
try:
    _init_db()
except Exception as _init_err:
    _log.warning("DB init failed: %s", _init_err)


# ──────────────────────────────────────────────────────────────────────────────
# Cost Calculator
# ──────────────────────────────────────────────────────────────────────────────
def _calculate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """Calculate USD cost based on model pricing."""
    # Normalize model name: strip version suffix like -2025-01-01
    model_lower = model.lower().split("-20")[0]  # e.g. "gpt-4o-mini-2025-07-18" → "gpt-4o-mini"
    rates = MODEL_PRICING.get(model_lower, MODEL_PRICING["default"])
    cost = (prompt_tokens * rates["prompt"]) + (completion_tokens * rates["completion"])
    return round(cost, 8)


# ──────────────────────────────────────────────────────────────────────────────
# Write to DB
# ──────────────────────────────────────────────────────────────────────────────
def _write_to_db(
    poc_name: str, file_name: str, step_name: str, model: str,
    prompt_tokens: int, completion_tokens: int, total_tokens: int,
    cost_usd: float, session_id: Optional[str], timestamp: str
):
    """Write one LLM call entry to the DB and update the file-level summary."""
    try:
        with _db_lock:
            conn = sqlite3.connect(str(_DB_PATH))
            cursor = conn.cursor()

            # 1. Insert individual call record
            cursor.execute("""
                INSERT INTO token_calls
                  (timestamp, poc_name, file_name, step_name, model,
                   prompt_tokens, completion_tokens, total_tokens, cost_usd, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, poc_name, file_name, step_name, model,
                  prompt_tokens, completion_tokens, total_tokens, cost_usd, session_id))

            # 2. Upsert file-level summary
            sid = session_id or ""
            cursor.execute("""
                INSERT INTO token_file_summary
                  (poc_name, file_name, session_id, total_llm_calls,
                   total_prompt_tokens, total_completion_tokens, total_tokens,
                   total_cost_usd, first_seen, last_updated)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(poc_name, file_name, session_id) DO UPDATE SET
                   total_llm_calls          = total_llm_calls + 1,
                   total_prompt_tokens      = total_prompt_tokens + excluded.total_prompt_tokens,
                   total_completion_tokens  = total_completion_tokens + excluded.total_completion_tokens,
                   total_tokens             = total_tokens + excluded.total_tokens,
                   total_cost_usd           = total_cost_usd + excluded.total_cost_usd,
                   last_updated             = excluded.last_updated
            """, (poc_name, file_name, sid,
                  prompt_tokens, completion_tokens, total_tokens, cost_usd,
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
    cost_usd: float, timestamp: str
):
    """Append entry to the JSON summary file for easy human inspection."""
    try:
        summary = {
            "last_updated": "",
            "grand_total_cost_usd": 0.0,
            "grand_total_tokens": 0,
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
        summary["grand_total_cost_usd"]  = round(summary.get("grand_total_cost_usd", 0.0) + cost_usd, 8)
        summary["grand_total_tokens"]    = summary.get("grand_total_tokens", 0) + total_tokens
        summary["grand_total_calls"]     = summary.get("grand_total_calls", 0) + 1
        summary["last_updated"]          = timestamp

        # Update per-POC section
        pocs = summary.setdefault("pocs", {})
        poc = pocs.setdefault(poc_name, {
            "total_files_processed": 0,
            "total_llm_calls": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "files": {}
        })
        poc["total_llm_calls"]      = poc.get("total_llm_calls", 0) + 1
        poc["total_tokens"]         = poc.get("total_tokens", 0) + total_tokens
        poc["total_cost_usd"]       = round(poc.get("total_cost_usd", 0.0) + cost_usd, 8)

        # Per-file section inside POC
        files = poc.setdefault("files", {})
        if file_name not in files:
            poc["total_files_processed"] = poc.get("total_files_processed", 0) + 1
            files[file_name] = {
                "total_llm_calls": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "calls_breakdown": []
            }
        file_entry = files[file_name]
        file_entry["total_llm_calls"]  = file_entry.get("total_llm_calls", 0) + 1
        file_entry["total_tokens"]     = file_entry.get("total_tokens", 0) + total_tokens
        file_entry["total_cost_usd"]   = round(file_entry.get("total_cost_usd", 0.0) + cost_usd, 8)
        file_entry.setdefault("calls_breakdown", []).append({
            "step": step_name,
            "model": model,
            "prompt_tokens": prompt_tokens,
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
    Track one OpenAI LLM call. Call this right after every
    client.chat.completions.create(...).

    Args:
        response_usage : response.usage object or dict from OpenAI API
        model          : model name used (e.g. "gpt-4o")
        poc_name       : name of the POC (e.g. "file-classification", "rpve")
        file_name      : name of the file/document being processed
        step_name      : name of the processing step (e.g. "classification", "extraction")
        session_id     : optional string to group multiple files in one user session

    Returns:
        dict with token counts and cost info. Never raises exceptions.
    """
    try:
        # ── Extract token counts ──────────────────────────────────────────────
        if response_usage is None:
            prompt_tokens = completion_tokens = total_tokens = 0
        elif hasattr(response_usage, "prompt_tokens"):
            prompt_tokens     = getattr(response_usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(response_usage, "completion_tokens", 0) or 0
            total_tokens      = getattr(response_usage, "total_tokens", 0) or 0
        elif isinstance(response_usage, dict):
            prompt_tokens     = response_usage.get("prompt_tokens", 0) or 0
            completion_tokens = response_usage.get("completion_tokens", 0) or 0
            total_tokens      = response_usage.get("total_tokens", 0) or 0
        else:
            prompt_tokens = completion_tokens = total_tokens = 0

        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens

        # ── Calculate cost ───────────────────────────────────────────────────
        cost_usd  = _calculate_cost(prompt_tokens, completion_tokens, model)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # ── Build result dict ────────────────────────────────────────────────
        result = {
            "poc_name":          poc_name,
            "file_name":         file_name,
            "step_name":         step_name,
            "model":             model,
            "prompt_tokens":     prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens":      total_tokens,
            "cost_usd":          cost_usd,
            "formatted_cost":    f"${cost_usd:.6f}",
            "timestamp":         timestamp,
        }

        # ── Persist data (non-blocking — errors logged, never raised) ────────
        _write_to_db(
            poc_name, file_name, step_name, model,
            prompt_tokens, completion_tokens, total_tokens, cost_usd,
            session_id, timestamp
        )
        _update_json_summary(
            poc_name, file_name, step_name, model,
            prompt_tokens, completion_tokens, total_tokens, cost_usd, timestamp
        )

        _log.info(
            "[%s] file=%s | step=%s | model=%s | tokens=%d | cost=%s",
            poc_name, file_name, step_name, model, total_tokens, f"${cost_usd:.6f}"
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
                    ORDER BY timestamp DESC LIMIT 200
                """, (file_name,))
                calls = [dict(r) for r in cursor.fetchall()]

                cursor.execute("""
                    SELECT * FROM token_file_summary WHERE file_name = ?
                """, (file_name,))
                summary_row = cursor.fetchone()
                conn.close()
                return {
                    "file_name": file_name,
                    "summary": dict(summary_row) if summary_row else {},
                    "calls": calls
                }

            elif poc_name:
                # POC-level: all files for this POC
                cursor.execute("""
                    SELECT * FROM token_file_summary WHERE poc_name = ?
                    ORDER BY last_updated DESC LIMIT 500
                """, (poc_name,))
                files = [dict(r) for r in cursor.fetchall()]

                cursor.execute("""
                    SELECT
                        COUNT(*) as total_calls,
                        SUM(total_tokens) as total_tokens,
                        SUM(total_cost_usd) as total_cost_usd,
                        COUNT(DISTINCT file_name) as total_files
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
                        SUM(total_cost_usd) as total_cost_usd
                    FROM token_file_summary
                    GROUP BY poc_name
                    ORDER BY total_cost_usd DESC
                """)
                poc_rows = [dict(r) for r in cursor.fetchall()]

                cursor.execute("""
                    SELECT
                        SUM(total_tokens) as grand_tokens,
                        SUM(total_cost_usd) as grand_cost,
                        SUM(total_llm_calls) as grand_calls,
                        COUNT(DISTINCT poc_name) as total_pocs,
                        COUNT(DISTINCT file_name) as total_files
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
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
    except Exception as e:
        _log.warning("get_recent_calls failed: %s", e)
        return []


def get_file_summaries(limit: int = 100, poc_name: Optional[str] = None) -> list:
    """
    Returns aggregated file-level rows (1 row per file process) including:
    - total_llm_calls count (e.g. 3)
    - total_prompt_tokens & total_completion_tokens
    - total_tokens & total_cost_usd
    - distinct models list (e.g. ["gpt-4o", "gpt-4o-mini"])
    - list of nested step call records for expanding details
    """
    try:
        with _db_lock:
            conn = sqlite3.connect(str(_DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if poc_name:
                cursor.execute("""
                    SELECT * FROM token_file_summary WHERE poc_name = ?
                    ORDER BY last_updated DESC LIMIT ?
                """, (poc_name, limit))
            else:
                cursor.execute("""
                    SELECT * FROM token_file_summary
                    ORDER BY last_updated DESC LIMIT ?
                """, (limit,))

            file_rows = [dict(r) for r in cursor.fetchall()]

            # Enrich each file summary with distinct models used & individual call steps
            for frow in file_rows:
                fname = frow["file_name"]
                fpoc  = frow["poc_name"]

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
                frow["calls"] = [dict(c) for c in cursor.fetchall()]

            conn.close()
            return file_rows
    except Exception as e:
        _log.warning("get_file_summaries failed: %s", e)
        return []

