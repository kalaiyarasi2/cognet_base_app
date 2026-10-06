import copy
import datetime
import logging
import re
from typing import Any, Dict, List, Optional
from core.tenant.models import TenantSubmissionConfig

logger = logging.getLogger(__name__)


class PayloadTransformer:
    """
    Transforms extracted ACORD and Loss Runs data into the partner/tenant's
    target JSON format using rules specified in TenantSubmissionConfig.
    """

    def __init__(self, config: Optional[TenantSubmissionConfig] = None):
        self.config = config or TenantSubmissionConfig()

    def transform(
        self,
        extracted_payloads: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        email_address: str = "",
        modifier: Optional[float] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
        config_override: Optional[TenantSubmissionConfig] = None,
    ) -> Dict[str, Any]:
        """
        Builds a unified submission payload according to tenant transform rules.
        """
        active_config = config_override or self.config
        transform_rules = active_config.transform_rules

        # Determine default modifier & submitter email
        resolved_modifier = (
            modifier
            if modifier is not None
            else active_config.default_modifier
        )

        resolved_email = email_address
        if active_config.default_submitter_email:
            if active_config.override_sender_email or not resolved_email:
                resolved_email = active_config.default_submitter_email

        # 3. Process each category from the extracted_payloads
        payload: Dict[str, Any] = {}
        
        extracted_payloads = extracted_payloads or {}
        
        # Check for extracted modifier data across categories
        modifier_data = None
        for cat, payloads in extracted_payloads.items():
            if any(k in cat.upper() for k in ("MODIFIER", "EXPERIENCE_MODIFIER", "XMOD", "EXMOD")) and payloads:
                modifier_data = copy.deepcopy(payloads[0]) if isinstance(payloads[0], dict) else {}
                break

        if modifier_data and modifier_data.get("experience_mod") is not None:
            try:
                resolved_modifier = float(modifier_data["experience_mod"])
            except (ValueError, TypeError):
                pass

        if transform_rules.unified_acord_lossrun:
            # Initialize default empty dicts to prevent UnboundLocalError
            cleaned_acord = {}
            cleaned_loss_run = {}
            
            # Extract ACORD-like data
            for cat, payloads in extracted_payloads.items():
                if any(k in cat.upper() for k in ("ACORD", "COMPENSATION", "WORK_COMP")):
                    cleaned_acord = copy.deepcopy(payloads[0]) if payloads else {}
            # Extract LOSS-like data
            loss_payloads = []
            for cat, payloads in extracted_payloads.items():
                if "LOSS" in cat or "CLAIM" in cat or "INSURANCE" in cat:
                    loss_payloads.extend(payloads)
            
            if len(loss_payloads) == 1:
                cleaned_loss_run = copy.deepcopy(loss_payloads[0])
            elif len(loss_payloads) > 1:
                cleaned_loss_run = copy.deepcopy(self._merge_documents(loss_payloads))
                
            # Normalizations specific to Loss Runs
            self._normalize_class_codes(cleaned_loss_run)
            if transform_rules.strip_summary_level_keys:
                self._clean_summary_level(cleaned_loss_run, transform_rules.strip_summary_level_keys)

            if transform_rules.include_tenant_code:
                tenant_code_val = getattr(active_config, "tenant_code", "") or ""
                if tenant_code_val:
                    payload["tenant"] = tenant_code_val

            payload["defaultModifier"] = resolved_modifier
            if transform_rules.include_modifier_data:
                payload["modifier"] = resolved_modifier
            payload["email"] = resolved_email

            # Generic opportunity block construction if configured for tenant
            if transform_rules.opportunity_template:
                opp = copy.deepcopy(transform_rules.opportunity_template)
                applicant_name = (
                    cleaned_acord.get("demographics", {}).get("applicantName")
                    or cleaned_acord.get("data", {}).get("demographics", {}).get("applicantName")
                    or ""
                )
                if applicant_name and not opp.get("opportunityName"):
                    opp["opportunityName"] = applicant_name
                opp["modifier"] = str(resolved_modifier)
                
                # Apply dynamic email body extractions
                email_body = extra_metadata.get("email_body") if extra_metadata else None
                if email_body and transform_rules.email_extraction_rules:
                    import re
                    for field, pattern in transform_rules.email_extraction_rules.items():
                        try:
                            match = re.search(pattern, email_body, re.IGNORECASE)
                            if match and match.group(1):
                                opp[field] = match.group(1).strip()
                        except Exception as e:
                            logger.warning(f"Failed to apply email extraction rule for {field}: {e}")

                payload["opportunity"] = opp

            payload["acord"] = cleaned_acord
            payload["lossRuns"] = cleaned_loss_run

            if transform_rules.include_modifier_data and modifier_data:
                payload["modifierData"] = modifier_data
            
        else:
            # Fully dynamic payload mapping for any POC
            payload["email"] = resolved_email
            
            for category, payloads in extracted_payloads.items():
                if not payloads:
                    continue
                    
                # Apply merge strategy if there are multiple documents of the same category
                if len(payloads) == 1:
                    merged_data = copy.deepcopy(payloads[0])
                else:
                    if transform_rules.merge_multiple_documents:
                        merged_data = copy.deepcopy(self._merge_documents(payloads))
                    else:
                        merged_data = copy.deepcopy(payloads)
                
                # Check for tenant-specified mapping key
                target_key = transform_rules.payload_mapping.get(category)
                
                if target_key:
                    payload[target_key] = merged_data
                else:
                    # If no explicit mapping, inject directly into root if it's a dict
                    if isinstance(merged_data, dict):
                        payload.update(merged_data)
                    else:
                        # Fallback for arrays without a specific key
                        payload[category.lower()] = merged_data

        # 4. Inject metadata if enabled
        if transform_rules.inject_metadata:
            if transform_rules.clean_metadata_summary:
                claims_list = cleaned_loss_run.get("claims", [])
                ratings_list = (
                    cleaned_acord.get("ratingByState")
                    or cleaned_acord.get("data", {}).get("ratingByState")
                    or []
                )
                locations_list = (
                    cleaned_acord.get("locations")
                    or cleaned_acord.get("data", {}).get("locations")
                    or []
                )
                meta = {
                    "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "lossRunFile": (extra_metadata or {}).get("lossRunFile"),
                    "acordFile": (extra_metadata or {}).get("acordFile"),
                    "modifierFile": (extra_metadata or {}).get("modifierFile"),
                    "defaultModifier": resolved_modifier,
                    "experienceMod": resolved_modifier,
                    "totalClaims": len(claims_list) if isinstance(claims_list, list) else 0,
                    "totalRatingEntries": len(ratings_list) if isinstance(ratings_list, list) else 0,
                    "totalLocations": len(locations_list) if isinstance(locations_list, list) else 0,
                }
                if not meta["modifierFile"] and modifier_data and modifier_data.get("filename"):
                    meta["modifierFile"] = modifier_data["filename"]
                payload["metadata"] = meta
            else:
                payload["metadata"] = {
                    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    **(extra_metadata or {})
                }

        # 4b. Shared finalize step (same step is used by the UI save endpoint)
        if transform_rules.unified_acord_lossrun:
            payload = self.finalize_unified_payload(payload, active_config)

        # 5. Apply any custom field mappings
        if transform_rules.custom_field_mappings:
            for source_key, target_key in transform_rules.custom_field_mappings.items():
                if source_key in payload:
                    payload[target_key] = payload.pop(source_key)

        return payload

    # ------------------------------------------------------------------
    # Shared finalize step (mail flow + UI save endpoint)
    # ------------------------------------------------------------------
    _DATE_TOKEN = re.compile(r"^\$\{TODAY(?:([+-])(\d+))?\}$", re.IGNORECASE)

    @classmethod
    def _resolve_date_token(cls, value: Any) -> Any:
        """Resolve ${TODAY} / ${TODAY+N} / ${TODAY-N} into MM/DD/YYYY."""
        if not isinstance(value, str):
            return value
        m = cls._DATE_TOKEN.match(value.strip())
        if not m:
            return value
        days = int(m.group(2) or 0)
        if m.group(1) == "-":
            days = -days
        d = datetime.date.today() + datetime.timedelta(days=days)
        return d.strftime("%m/%d/%Y")

    @staticmethod
    def _acord_data_node(acord: Dict[str, Any]) -> Dict[str, Any]:
        """Return the dict that holds ACORD fields (acord['data'] or acord itself)."""
        if isinstance(acord.get("data"), dict):
            return acord["data"]
        return acord

    def finalize_unified_payload(
        self,
        payload: Dict[str, Any],
        config: Optional[TenantSubmissionConfig] = None,
    ) -> Dict[str, Any]:
        """
        Normalises a unified ACORD + Loss Run payload so the UI and mail-to-mail
        flows produce the same shape. Only fills gaps / normalises formats —
        never overwrites values that are already present (e.g. UI edits).
        """
        if not isinstance(payload, dict):
            return payload
        active_config = config or self.config
        rules = active_config.transform_rules
        tenant_tag = getattr(active_config, "tenant_code", "") or payload.get("tenant") or ""

        acord = payload.get("acord") if isinstance(payload.get("acord"), dict) else {}
        loss_runs = payload.get("lossRuns") if isinstance(payload.get("lossRuns"), dict) else {}
        acord_node = self._acord_data_node(acord) if acord else {}

        # Helper to extract value by dotted path (e.g. 'acord.demographics.applicantName')
        def _get_path_val(root_dict: Dict[str, Any], path_str: str) -> Any:
            parts = path_str.split(".")
            curr: Any = root_dict
            for idx, p in enumerate(parts):
                if not isinstance(curr, dict):
                    return None
                # Handle possible 'data' wrapper for acord/lossRuns
                if p not in curr and "data" in curr and isinstance(curr["data"], dict) and p in curr["data"]:
                    curr = curr["data"][p]
                else:
                    curr = curr.get(p)
            return curr

        # (a)(b)(c) Opportunity block
        if rules.opportunity_template or isinstance(payload.get("opportunity"), dict):
            opp = payload.get("opportunity") if isinstance(payload.get("opportunity"), dict) else {}
            for key, tmpl_val in (rules.opportunity_template or {}).items():
                if opp.get(key) in (None, ""):
                    opp[key] = tmpl_val
            for key in list(opp.keys()):
                opp[key] = self._resolve_date_token(opp[key])
            
            # Dynamic opportunity field sources (e.g. opportunityName from acord)
            for target_field, source_path in (rules.opportunity_field_sources or {}).items():
                if not opp.get(target_field):
                    val = _get_path_val(payload, source_path)
                    if val is not None and val != "":
                        opp[target_field] = val
                    elif target_field not in opp:
                        opp[target_field] = ""
            
            # Modifier in opportunity if available
            if payload.get("modifier") is not None and opp.get("modifier") in (None, ""):
                opp["modifier"] = str(payload["modifier"])
            payload["opportunity"] = opp

        # (d) Class codes -> nullable ints (partner API format)
        if loss_runs:
            self._normalize_class_codes(loss_runs)

        # (e) Tenant tag inside sections
        if rules.include_tenant_code and tenant_tag:
            payload.setdefault("tenant", tenant_tag)
            if acord:
                acord.setdefault("tenant", tenant_tag)
            if loss_runs:
                loss_runs.setdefault("tenant", tenant_tag)

        # (f) Dynamic schema extension placeholders from tenant's extraction.json (if present)
        # Avoid hardcoding any specific fields like locations or contact_information!
        if tenant_tag:
            try:
                import json
                from pathlib import Path
                # Check if tenant has extraction.json defining schema_extensions
                config_dir = Path(__file__).resolve().parent.parent.parent / "config" / "tenants" / tenant_tag.lower()
                ext_cfg_path = config_dir / "extraction.json"
                if ext_cfg_path.exists():
                    with open(ext_cfg_path, "r", encoding="utf-8") as f:
                        ext_cfg = json.load(f)
                    for ext in ext_cfg.get("schema_extensions", []):
                        if not ext.get("enabled", False):
                            continue
                        name = ext.get("name")
                        if not name:
                            continue
                        src = str(ext.get("source_doc_type", "")).upper()
                        empty_val = [] if str(ext.get("output_type", "")).lower() == "array" else {}
                        if "WORK_COMP" in src or "ACORD" in src:
                            if acord and name not in acord_node:
                                acord_node[name] = copy.deepcopy(empty_val)
                        elif "INSURANCE" in src or "LOSS" in src:
                            if loss_runs and name not in loss_runs:
                                loss_runs[name] = copy.deepcopy(empty_val)
            except Exception as e:
                logger.warning(f"[finalize_unified_payload] Failed loading schema_extensions for {tenant_tag}: {e}")

        # (g) Recompute metadata counts dynamically based on config
        meta = payload.get("metadata")
        if isinstance(meta, dict) and rules.inject_metadata:
            for count_key, source_path in (rules.metadata_count_sources or {}).items():
                items = _get_path_val(payload, source_path)
                meta[count_key] = len(items) if isinstance(items, list) else 0

        return payload

    def _clean_summary_level(self, loss_data: Any, strip_keys: List[str]):
        """
        Recursively finds any list under 'SummaryLevel' or 'summary_level'
        and removes specified keys from each dictionary item.
        """
        if isinstance(loss_data, dict):
            for key, val in loss_data.items():
                if key in ("SummaryLevel", "summary_level", "summaryLevel") and isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            for k in strip_keys:
                                item.pop(k, None)
                else:
                    self._clean_summary_level(val, strip_keys)
        elif isinstance(loss_data, list):
            for item in loss_data:
                self._clean_summary_level(item, strip_keys)

    def _normalize_class_codes(self, payload: Any):
        """
        Recursively converts class-code fields (claim_class / *_class) to nullable
        integers so the partner API can deserialize them as System.Nullable<Int32>.
        Non-numeric values are emitted as None instead of a failing string.
        """
        if isinstance(payload, dict):
            for key, val in payload.items():
                if key == "claim_class" or (isinstance(key, str) and key.endswith("_class")):
                    payload[key] = self._to_nullable_int(val)
                else:
                    self._normalize_class_codes(val)
        elif isinstance(payload, list):
            for item in payload:
                self._normalize_class_codes(item)

    @staticmethod
    def _to_nullable_int(value: Any):
        if value is None or value == "" or value == []:
            return None
        if isinstance(value, bool):
            return int(value)
        try:
            numeric = int(float(value))
            return numeric
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _merge_documents(docs: List[dict]) -> dict:
        """
        Dynamically merges multiple extracted documents of the same category.
        Concatenates lists (like claims), sums integers (like claimsCount),
        and takes the first non-empty value for other keys.
        """
        if not docs:
            return {}
        if len(docs) == 1:
            return docs[0]

        merged: Dict[str, Any] = {}
        list_keys = set()
        
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            for k, v in doc.items():
                if isinstance(v, list):
                    list_keys.add(k)
                    if k not in merged:
                        merged[k] = []
                    merged[k].extend(v)
                elif isinstance(v, dict) and k == "claimsCount":
                    # Special sum logic for nested int counts
                    if k not in merged:
                        merged[k] = {"lastFiveYears": 0, "olderThanFiveYears": 0, "total": 0}
                    merged[k]["lastFiveYears"] += int(v.get("lastFiveYears") or 0)
                    merged[k]["olderThanFiveYears"] += int(v.get("olderThanFiveYears") or 0)
                    merged[k]["total"] += int(v.get("total") or 0)
                else:
                    if k not in merged or not merged[k]:
                        merged[k] = v
                        
        return merged

