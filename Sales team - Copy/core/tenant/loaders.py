import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from core.tenant.models import TenantSettings, ModuleConfig, TenantSubmissionConfig

logger = logging.getLogger(__name__)


def default_tenant_folder(base_dir: Path) -> str:
    """Default tenant folder when the caller doesn't name one.

    Order: PLATFORM_TENANT env -> first (alphabetical) folder under config/tenants with a tenant.json
    -> 'default'. (The old hardcoded 'client_a'/'c1754' folders don't exist on disk.)
    """
    env_val = (os.getenv("PLATFORM_TENANT") or "").strip()
    if env_val:
        return env_val
    tenants_dir = Path(base_dir) / "config" / "tenants"
    if tenants_dir.exists():
        for sub in sorted(tenants_dir.iterdir()):
            if sub.is_dir() and (sub / "tenant.json").exists():
                return sub.name
    return "default"


class TenantConfigLoader:
    """Loads tenant configuration and module configurations from disk."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).resolve()

    def load_submission_config(self, tenant_folder: Optional[str] = None) -> TenantSubmissionConfig:
        tenant_folder = tenant_folder or default_tenant_folder(self.base_dir)
        config_path = self.base_dir / "config" / "tenants" / tenant_folder / "submission.json"
        if not config_path.exists():
            return TenantSubmissionConfig(enabled=False)

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not data.get("tenant_code"):
            t_json = self.base_dir / "config" / "tenants" / tenant_folder / "tenant.json"
            if t_json.exists():
                try:
                    with open(t_json, "r", encoding="utf-8") as tf:
                        td = json.load(tf)
                        data["tenant_code"] = td.get("tenant_code", tenant_folder.upper())
                except Exception:
                    data["tenant_code"] = tenant_folder.upper()
            else:
                data["tenant_code"] = tenant_folder.upper()

        return TenantSubmissionConfig(**data)


    def _bootstrap_tenant(self, tenant_folder: str):
        tenant_dir = self.base_dir / "config" / "tenants" / tenant_folder
        tenant_dir.mkdir(parents=True, exist_ok=True)
        (tenant_dir / "prompts").mkdir(exist_ok=True)
        (tenant_dir / "schemas").mkdir(exist_ok=True)

        clean_code = tenant_folder.upper()
        t_name = "ABC Company" if clean_code == "CLIENT_A" else clean_code

        tenant_file = tenant_dir / "tenant.json"
        if not tenant_file.exists():
            tenant_data = {
                "tenant_id": 1 if clean_code == "CLIENT_A" else 99,
                "tenant_code": clean_code,
                "tenant_name": t_name,
                "email": f"admin@{clean_code.lower()}.com",
                "active": True,
                "enabled_modules": ["INVOICE", "SBC"],
                "output_root": f"output/{clean_code}",
                "default_confidence_threshold": 0.85,
                "timezone": "UTC"
            }
            with open(tenant_file, "w", encoding="utf-8") as f:
                json.dump(tenant_data, f, indent=2)

        # invoice.json
        inv_file = tenant_dir / "invoice.json"
        if not inv_file.exists():
            inv_cfg = {
                "module_code": "INVOICE",
                "enabled": True,
                "prompt_file": "prompts/invoice.txt",
                "schema_file": "schemas/invoice.schema.json",
                "confidence_threshold": 0.85,
                "required_fields": ["invoice_number", "total_amount", "vendor_name"],
                "output_formats": ["json", "xlsx"]
            }
            with open(inv_file, "w", encoding="utf-8") as f:
                json.dump(inv_cfg, f, indent=2)

        # sbc.json
        sbc_file = tenant_dir / "sbc.json"
        if not sbc_file.exists():
            sbc_cfg = {
                "module_code": "SBC",
                "enabled": True,
                "prompt_file": "prompts/sbc.txt",
                "schema_file": "schemas/sbc.schema.json",
                "confidence_threshold": 0.80,
                "required_fields": ["plan_name", "deductible_individual", "copay_primary_care"],
                "output_formats": ["json", "csv"]
            }
            with open(sbc_file, "w", encoding="utf-8") as f:
                json.dump(sbc_cfg, f, indent=2)

        # Prompts
        inv_prompt = tenant_dir / "prompts" / "invoice.txt"
        if not inv_prompt.exists():
            with open(inv_prompt, "w", encoding="utf-8") as f:
                f.write(f"Extract invoice details including invoice_number, total_amount, vendor_name for tenant {t_name}.")

        sbc_prompt = tenant_dir / "prompts" / "sbc.txt"
        if not sbc_prompt.exists():
            with open(sbc_prompt, "w", encoding="utf-8") as f:
                f.write(f"Extract SBC details including plan_name, deductible_individual, copay_primary_care for tenant {t_name}.")

        # Schemas
        inv_schema = tenant_dir / "schemas" / "invoice.schema.json"
        if not inv_schema.exists():
            with open(inv_schema, "w", encoding="utf-8") as f:
                json.dump({"title": "InvoiceSchema", "type": "object", "required": ["invoice_number"]}, f, indent=2)

        sbc_schema = tenant_dir / "schemas" / "sbc.schema.json"
        if not sbc_schema.exists():
            with open(sbc_schema, "w", encoding="utf-8") as f:
                json.dump({"title": "SBCSchema", "type": "object", "required": ["plan_name"]}, f, indent=2)

    def load_tenant(self, tenant_folder: Optional[str] = None) -> TenantSettings:
        tenant_folder = tenant_folder or default_tenant_folder(self.base_dir)
        tenants_dir = self.base_dir / "config" / "tenants"
        tenant_path = tenants_dir / tenant_folder / "tenant.json"
        
        if not tenant_path.exists():
            # Find any existing tenant folder
            if tenants_dir.exists():
                for sub in tenants_dir.iterdir():
                    if sub.is_dir() and (sub / "tenant.json").exists():
                        tenant_path = sub / "tenant.json"
                        break

        if not tenant_path.exists():
            return TenantSettings(
                tenant_id=1,
                tenant_code=tenant_folder.upper(),
                tenant_name=tenant_folder.upper(),
                email=f"admin@{tenant_folder.lower()}.com",
                active=True,
                enabled_modules=["INVOICE", "SBC"]
            )

        with open(tenant_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return TenantSettings(**data)

    def load_module_config(self, module_code: str, tenant_folder: Optional[str] = None) -> ModuleConfig:
        tenant_folder = tenant_folder or default_tenant_folder(self.base_dir)
        module_file = f"{module_code.lower()}.json"
        config_path = self.base_dir / "config" / "tenants" / tenant_folder / module_file
        if not config_path.exists():
            return ModuleConfig(
                module_code=module_code.upper(),
                enabled=True,
                confidence_threshold=0.85
            )

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ModuleConfig(**data)


class PromptLoader:
    """Loads tenant prompt files."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).resolve()

    def load_prompt(self, relative_prompt_path: str, tenant_folder: Optional[str] = None) -> str:
        tenant_folder = tenant_folder or default_tenant_folder(self.base_dir)
        prompt_path = self.base_dir / "config" / "tenants" / tenant_folder / relative_prompt_path
        if not prompt_path.exists():
            TenantConfigLoader(self.base_dir)._bootstrap_tenant(tenant_folder)
        if not prompt_path.exists():
            logger.warning(f"Prompt file not found at {prompt_path}, using default empty prompt.")
            return ""
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()


class SchemaLoader:
    """Loads tenant JSON schema files."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).resolve()

    def load_schema(self, relative_schema_path: str, tenant_folder: Optional[str] = None) -> Dict[str, Any]:
        tenant_folder = tenant_folder or default_tenant_folder(self.base_dir)
        schema_path = self.base_dir / "config" / "tenants" / tenant_folder / relative_schema_path
        if not schema_path.exists():
            TenantConfigLoader(self.base_dir)._bootstrap_tenant(tenant_folder)
        if not schema_path.exists():
            logger.warning(f"Schema file not found at {schema_path}, returning empty schema.")
            return {}
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
