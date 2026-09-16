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
        acord_data: Optional[Dict[str, Any]] = None,
        loss_run_data: Optional[Dict[str, Any]] = None,
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

        # Deep copy inputs to prevent mutating original extraction cache
        cleaned_acord = copy.deepcopy(acord_data) if acord_data else {}
        cleaned_loss_run = copy.deepcopy(loss_run_data) if loss_run_data else {}

        # Normalize class-code fields so numeric strings become nullable ints,
        # matching the partner API's System.Nullable<Int32> schema.
        self._normalize_class_codes(cleaned_loss_run)

        # 1. Strip configured keys from SummaryLevel (e.g., policy_number, carrier_name)
        strip_keys = transform_rules.strip_summary_level_keys
        if strip_keys:
            self._clean_summary_level(cleaned_loss_run, strip_keys)

        # 2. Determine default modifier & submitter email
        resolved_modifier = (
            modifier
            if modifier is not None
            else active_config.default_modifier
        )

        resolved_email = email_address
        if active_config.default_submitter_email:
            if active_config.override_sender_email or not resolved_email:
                resolved_email = active_config.default_submitter_email

        # 3. Build target unified JSON
        payload: Dict[str, Any] = {}

        if transform_rules.unified_acord_lossrun:
            payload["defaultModifier"] = resolved_modifier
            payload["email"] = resolved_email
            payload["acord"] = cleaned_acord
            payload["lossRuns"] = cleaned_loss_run
        else:
            # Standard passthrough if tenant doesn't require unified wrapper
            if cleaned_acord:
                payload["acord"] = cleaned_acord
            if cleaned_loss_run:
                payload["lossRuns"] = cleaned_loss_run
            payload["email"] = resolved_email
            payload["modifier"] = resolved_modifier

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
