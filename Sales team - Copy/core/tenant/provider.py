from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, List, Optional
from core.tenant.models import TenantSettings, ModuleConfig
from core.tenant.loaders import TenantConfigLoader, PromptLoader, SchemaLoader, default_tenant_folder
from core.env_loader import get_env

logger = logging.getLogger(__name__)

# Standard Module Constants
MODULE_INVOICE = "INVOICE"
MODULE_SBC = "SBC"
MODULE_LOSS_RUN = "LOSS_RUN"
MODULE_RENEWAL = "RENEWAL"

ALL_MODULES = [MODULE_INVOICE, MODULE_SBC, MODULE_LOSS_RUN, MODULE_RENEWAL]


class ModuleAccessService:
    """Checks module access rights against tenant settings."""

    def __init__(self, tenant_settings: TenantSettings):
        self.tenant_settings = tenant_settings

    def can_access(self, module_code: str) -> bool:
        if not self.tenant_settings.active:
            logger.warning(f"Tenant {self.tenant_settings.tenant_code} is INACTIVE.")
            return False
        
        normalized_code = module_code.upper().strip()
        enabled_list = [m.upper().strip() for m in self.tenant_settings.enabled_modules]
        return normalized_code in enabled_list

    def get_enabled_modules(self) -> List[str]:
        if not self.tenant_settings.active:
            return []
        return [m.upper().strip() for m in self.tenant_settings.enabled_modules]


class SingleTenantProvider:
    """
    Centralized provider for Tenant Configuration.
    Supports single or multi-tenant lookups with per-tenant caching.
    """
    _instances: Dict[str, SingleTenantProvider] = {}
    _instance: Optional[SingleTenantProvider] = None

    def __init__(self, workspace_dir: Optional[Path] = None, tenant_folder: Optional[str] = None):
        if workspace_dir is None:
            workspace_dir = Path(__file__).resolve().parent.parent.parent
        self.workspace_dir = Path(workspace_dir).resolve()
        
        self.config_loader = TenantConfigLoader(self.workspace_dir)
        self.prompt_loader = PromptLoader(self.workspace_dir)
        self.schema_loader = SchemaLoader(self.workspace_dir)

        self.tenant_folder = tenant_folder or get_env("DEFAULT_TENANT") or default_tenant_folder(self.workspace_dir)

        self._tenant_settings: Optional[TenantSettings] = None
        self._module_configs: Dict[str, ModuleConfig] = {}
        self._access_service: Optional[ModuleAccessService] = None

        self.reload()

    @classmethod
    def get_instance(cls, workspace_dir: Optional[Path] = None, tenant_folder: Optional[str] = None) -> SingleTenantProvider:
        t_key = (tenant_folder or "").strip().lower()
        if not t_key:
            t_key = (get_env("DEFAULT_TENANT") or default_tenant_folder(workspace_dir or Path(__file__).resolve().parent.parent.parent)).strip().lower()
        if t_key not in cls._instances:
            cls._instances[t_key] = cls(workspace_dir=workspace_dir, tenant_folder=t_key)
        cls._instance = cls._instances[t_key]
        return cls._instances[t_key]

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
        cls._instances.clear()

    def reload(self) -> None:
        """Loads or reloads tenant settings and configs from disk."""
        target_folder = self.tenant_folder or default_tenant_folder(self.workspace_dir)
        self._tenant_settings = self.config_loader.load_tenant(tenant_folder=target_folder)
        self._access_service = ModuleAccessService(self._tenant_settings)
        
        self._module_configs.clear()
        for module_code in self._tenant_settings.enabled_modules:
            try:
                mod_cfg = self.config_loader.load_module_config(module_code, tenant_folder=target_folder)
                self._module_configs[module_code.upper()] = mod_cfg
            except Exception:
                logger.warning(f"Could not load config for enabled module {module_code}")

    @property
    def tenant(self) -> TenantSettings:
        if self._tenant_settings is None:
            raise RuntimeError("TenantSettings not loaded.")
        return self._tenant_settings

    @property
    def access_service(self) -> ModuleAccessService:
        if self._access_service is None:
            raise RuntimeError("ModuleAccessService not initialized.")
        return self._access_service

    def get_module_config(self, module_code: str) -> Optional[ModuleConfig]:
        normalized = module_code.upper().strip()
        if normalized not in self._module_configs:
            try:
                cfg = self.config_loader.load_module_config(normalized, tenant_folder=self.tenant_folder)
                self._module_configs[normalized] = cfg
            except FileNotFoundError:
                return None
        return self._module_configs.get(normalized)

    def load_prompt_for_module(self, module_code: str) -> str:
        cfg = self.get_module_config(module_code)
        if not cfg or not cfg.prompt_file:
            return ""
        return self.prompt_loader.load_prompt(cfg.prompt_file, tenant_folder=self.tenant_folder)

    def load_schema_for_module(self, module_code: str) -> dict:
        cfg = self.get_module_config(module_code)
        if not cfg or not cfg.schema_file:
            return {}
        return self.schema_loader.load_schema(cfg.schema_file, tenant_folder=self.tenant_folder)
