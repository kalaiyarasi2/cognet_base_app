import copy
import datetime
import logging
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
        
        # Backward compatibility for unified_acord_lossrun
        cleaned_acord = {}
        cleaned_loss_run = {}
        
        if transform_rules.unified_acord_lossrun:
            # Extract ACORD-like data
            for cat, payloads in extracted_payloads.items():
                if "ACORD" in cat or "COMPENSATION" in cat:
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

            payload["defaultModifier"] = resolved_modifier
            payload["email"] = resolved_email
            payload["acord"] = cleaned_acord
            payload["lossRuns"] = cleaned_loss_run
            
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
            payload["metadata"] = {
                "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                **(extra_metadata or {})
            }

        # 5. Apply any custom field mappings
        if transform_rules.custom_field_mappings:
            for source_key, target_key in transform_rules.custom_field_mappings.items():
                if source_key in payload:
                    payload[target_key] = payload.pop(source_key)

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

