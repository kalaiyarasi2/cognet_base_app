"""
core/tenant/exception_evaluator.py
────────────────────────────────────────────────────────────────────────────────
Generic Exception Rule Evaluator

Reads exception_rules from a tenant's extraction.json and evaluates each rule
against the extracted payloads.  Works for ANY tenant — no tenant-specific logic.

Supported eval_target values (matching extraction.json schema):
  - "document_presence"  → checks which document types were extracted
  - "acord_data"         → checks fields in the WORK_COMP / WORK_COMPENSATION payload
  - "loss_run_data"      → checks fields in the INSURANCE_CLAIMS / INSURANCE payload

Supported condition micro-DSL:
  !field.path              → field is falsy / missing
  has_document('TYPE')     → document type is present in payloads
  !has_document('TYPE')    → document type is NOT present
  field.path == value      → field equals value
  days_since(field.path) > N → date field is more than N days old
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_nested(data: Dict[str, Any], dotted_key: str) -> Any:
    """Resolve a dot-separated key path in a nested dict, e.g. 'demographics.fein'."""
    if not isinstance(data, dict):
        return None
    keys = dotted_key.split(".")
    current = data
    for k in keys:
        if not isinstance(current, dict):
            current = None
            break
        current = current.get(k)
    if current is not None:
        return current

    # If data is wrapped in a top-level "data" key, check inside data["data"]
    if "data" in data and isinstance(data["data"], dict) and not dotted_key.startswith("data."):
        current = data["data"]
        for k in keys:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(k)
        if current is not None:
            return current

    # Fallback for employee_count: calculate from ratingByState if present
    if "employee_count" in dotted_key:
        rating_entries = (
            data.get("ratingByState")
            or (data.get("data", {}).get("ratingByState") if isinstance(data.get("data"), dict) else None)
            or []
        )
        if isinstance(rating_entries, list) and rating_entries:
            total_emp = sum(
                int(r.get("fullTimeEmployees") or 0) + int(r.get("partTimeEmployees") or 0)
                for r in rating_entries
                if isinstance(r, dict)
            )
            return total_emp

    return None


def _days_since(value: Any) -> Optional[int]:
    """
    Return number of days since the given date value.
    Accepts strings like 'MM/DD/YYYY', 'YYYY-MM-DD', or date objects.
    Returns None if unparseable.
    """
    if not value:
        return None

    formats = ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y"]
    for fmt in formats:
        try:
            d = datetime.strptime(str(value).strip(), fmt).date()
            return (date.today() - d).days
        except ValueError:
            continue
    logger.debug("[ExceptionEvaluator] Could not parse date '%s'", value)
    return None


def _has_document(doc_type: str, doc_map: Dict[str, Any]) -> bool:
    """Check if a document type exists in the extracted payloads map."""
    upper = doc_type.upper()
    # Normalize: INSURANCE_CLAIMS ↔ INSURANCE, WORK_COMPENSATION ↔ WORK_COMP
    aliases = {
        "INSURANCE": ["INSURANCE", "INSURANCE_CLAIMS", "LOSS_RUN", "LOSSRUNS"],
        "INSURANCE_CLAIMS": ["INSURANCE_CLAIMS", "INSURANCE", "LOSS_RUN", "LOSSRUNS"],
        "WORK_COMP": ["WORK_COMP", "WORK_COMPENSATION", "ACORD"],
        "WORK_COMPENSATION": ["WORK_COMPENSATION", "WORK_COMP", "ACORD"],
        "EXPERIENCE_MODIFIER": ["EXPERIENCE_MODIFIER", "MODIFIER", "EXPERIENCE MODIFIER", "MODIFIERDATA"],
    }
    candidates = aliases.get(upper, [upper])
    for key in doc_map:
        if key.upper() in candidates:
            return bool(doc_map[key])
    return False


# ---------------------------------------------------------------------------
# Condition evaluator
# ---------------------------------------------------------------------------

def _evaluate_condition(
    condition: str,
    eval_target: str,
    acord_data: Dict[str, Any],
    loss_run_data: Dict[str, Any],
    doc_map: Dict[str, Any],
) -> bool:
    """
    Evaluate a single condition string.
    Returns True if the exception FIRES (condition is met).
    """
    condition = condition.strip()

    # ── has_document / !has_document ─────────────────────────────────────────
    has_doc_match = re.match(r"(!?)has_document\(['\"]([^'\"]+)['\"]\)", condition)
    if has_doc_match:
        negate = has_doc_match.group(1) == "!"
        doc_type = has_doc_match.group(2)
        result = _has_document(doc_type, doc_map)
        return (not result) if negate else result

    # ── days_since(field) > N ─────────────────────────────────────────────────
    days_match = re.match(r"days_since\(([^)]+)\)\s*([><=!]+)\s*(\d+)", condition)
    if days_match:
        field_path = days_match.group(1).strip()
        operator = days_match.group(2).strip()
        threshold = int(days_match.group(3))

        # Pick the data source
        data = loss_run_data if eval_target == "loss_run_data" else acord_data
        value = _get_nested(data, field_path)
        days = _days_since(value)

        if days is None:
            # Can't determine date → treat as exception (safe default)
            logger.debug("[ExceptionEvaluator] days_since('%s') → unparseable → firing exception", field_path)
            return True

        if operator == ">":
            return days > threshold
        if operator == ">=":
            return days >= threshold
        if operator == "<":
            return days < threshold
        if operator == "<=":
            return days <= threshold
        return False

    # ── field == value ────────────────────────────────────────────────────────
    eq_match = re.match(r"^(.+?)\s*==\s*(.+)$", condition)
    if eq_match:
        field_path = eq_match.group(1).strip()
        raw_val = eq_match.group(2).strip().strip("'\"")

        data = loss_run_data if eval_target == "loss_run_data" else acord_data
        actual = _get_nested(data, field_path)
        if actual is None and "employee_count" in field_path:
            # Fallback: if employee_count requested from loss_run_data, check acord_data
            actual = _get_nested(acord_data, field_path)

        if actual is None:
            # Field is missing entirely; do not treat None as 0 unless raw_val is explicitly None
            return raw_val.lower() in ("none", "null", "")

        # Attempt numeric comparison
        try:
            return float(actual) == float(raw_val)
        except (ValueError, TypeError):
            return str(actual) == raw_val

    # ── !field.path (falsy / missing check) ──────────────────────────────────
    if condition.startswith("!"):
        field_path = condition[1:].strip()
        data = loss_run_data if eval_target == "loss_run_data" else acord_data
        value = _get_nested(data, field_path)
        return not bool(value)

    logger.warning("[ExceptionEvaluator] Unrecognised condition: '%s'", condition)
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ExceptionEvaluator:
    """
    Generic exception rule evaluator.

    Usage:
        evaluator = ExceptionEvaluator(workspace_dir, tenant_folder="wcuw")
        triggered = evaluator.evaluate(
            extracted_payloads={"WORK_COMP": [...], "INSURANCE_CLAIMS": [...]},
        )
        # triggered → [{"id": "missing_fein", "message": "No FEIN Found"}, ...]
    """

    def __init__(self, workspace_dir: Path, tenant_folder: str):
        self.workspace_dir = Path(workspace_dir)
        self.tenant_folder = tenant_folder
        self._rules: List[Dict[str, Any]] = self._load_rules()

    def _load_rules(self) -> List[Dict[str, Any]]:
        extraction_path = (
            self.workspace_dir
            / "config" / "tenants" / self.tenant_folder / "extraction.json"
        )
        if not extraction_path.exists():
            logger.warning(
                "[ExceptionEvaluator] extraction.json not found at %s — no rules loaded.",
                extraction_path,
            )
            return []
        try:
            with open(extraction_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            rules = data.get("exception_rules", [])
            logger.info(
                "[ExceptionEvaluator] Loaded %d exception rule(s) for tenant '%s'.",
                len(rules), self.tenant_folder,
            )
            return rules
        except Exception as e:
            logger.error("[ExceptionEvaluator] Failed to load rules: %s", e)
            return []

    def evaluate(
        self,
        extracted_payloads: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        merged_payload: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """
        Evaluate all rules against the extracted payloads and/or merged payload.

        Args:
            extracted_payloads: dict mapping category key → list of extracted dicts
                e.g. {"WORK_COMP": [{...}], "INSURANCE_CLAIMS": [{...}]}
            merged_payload: optional unified final submission JSON dict

        Returns:
            List of triggered exception dicts: [{"id": str, "message": str}, ...]
        """
        if not self._rules:
            return []

        extracted_payloads = extracted_payloads or {}

        # Build normalised data maps
        def _merge(payloads_list: List[Dict]) -> Dict:
            merged: Dict[str, Any] = {}
            for p in payloads_list:
                if isinstance(p, dict):
                    for k, v in p.items():
                        if k not in merged:
                            merged[k] = v
            return merged

        # Resolve ACORD (WORK_COMP) data
        acord_data: Dict[str, Any] = {}
        if merged_payload and isinstance(merged_payload.get("acord"), dict):
            acord_data = dict(merged_payload["acord"])
        else:
            for key in ("WORK_COMP", "WORK_COMPENSATION"):
                if key in extracted_payloads and extracted_payloads[key]:
                    acord_data = _merge(extracted_payloads[key])
                    break

        # Resolve Loss Run (INSURANCE / INSURANCE_CLAIMS) data
        loss_run_data: Dict[str, Any] = {}
        if merged_payload and isinstance(merged_payload.get("lossRuns"), dict):
            loss_run_data = dict(merged_payload["lossRuns"])
        else:
            for key in ("INSURANCE_CLAIMS", "INSURANCE", "LOSS_RUN"):
                if key in extracted_payloads and extracted_payloads[key]:
                    loss_run_data = _merge(extracted_payloads[key])
                    break

        # Build document presence map {category_upper: bool}
        doc_map: Dict[str, bool] = {k.upper(): bool(v) for k, v in extracted_payloads.items()}
        if merged_payload and isinstance(merged_payload, dict):
            if merged_payload.get("acord"):
                doc_map["WORK_COMP"] = True
                doc_map["WORK_COMPENSATION"] = True
            if merged_payload.get("lossRuns"):
                doc_map["INSURANCE"] = True
                doc_map["INSURANCE_CLAIMS"] = True
            if merged_payload.get("modifier") or merged_payload.get("modifierData"):
                doc_map["EXPERIENCE_MODIFIER"] = True
                doc_map["MODIFIER"] = True

        triggered: List[Dict[str, str]] = []

        for rule in self._rules:
            rule_id = rule.get("id", "unknown")
            condition = rule.get("condition", "")
            eval_target = rule.get("eval_target", "acord_data")
            message = rule.get("exception_message", rule_id)

            if not condition:
                continue

            try:
                fired = _evaluate_condition(
                    condition=condition,
                    eval_target=eval_target,
                    acord_data=acord_data,
                    loss_run_data=loss_run_data,
                    doc_map=doc_map,
                )
                if fired:
                    logger.info(
                        "[ExceptionEvaluator] Rule '%s' FIRED: %s", rule_id, message
                    )
                    triggered.append({"id": rule_id, "message": message})
                else:
                    logger.debug("[ExceptionEvaluator] Rule '%s' passed (no exception).", rule_id)
            except Exception as e:
                logger.warning(
                    "[ExceptionEvaluator] Error evaluating rule '%s': %s", rule_id, e
                )

        logger.info(
            "[ExceptionEvaluator] %d/%d rule(s) triggered for tenant '%s'.",
            len(triggered), len(self._rules), self.tenant_folder,
        )
        return triggered
