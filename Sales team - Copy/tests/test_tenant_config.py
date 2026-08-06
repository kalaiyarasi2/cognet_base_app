import pytest
from pathlib import Path
from core.tenant.provider import SingleTenantProvider
from core.tenant.models import TenantSettings, ModuleConfig


def test_tenant_config_loading():
    workspace_dir = Path(__file__).resolve().parent.parent
    SingleTenantProvider.reset_instance()
    provider = SingleTenantProvider.get_instance(workspace_dir)

    tenant = provider.tenant
    assert tenant.tenant_id == 1
    assert tenant.tenant_code == "CLIENT_A"
    assert tenant.tenant_name == "ABC Company"
    assert tenant.active is True
    assert "INVOICE" in tenant.enabled_modules
    assert "SBC" in tenant.enabled_modules
    assert "LOSS_RUN" not in tenant.enabled_modules
    assert "RENEWAL" not in tenant.enabled_modules


def test_prompt_and_schema_loading():
    workspace_dir = Path(__file__).resolve().parent.parent
    SingleTenantProvider.reset_instance()
    provider = SingleTenantProvider.get_instance(workspace_dir)

    invoice_prompt = provider.load_prompt_for_module("INVOICE")
    assert len(invoice_prompt) > 0
    assert "invoice_number" in invoice_prompt

    sbc_schema = provider.load_schema_for_module("SBC")
    assert isinstance(sbc_schema, dict)
    assert sbc_schema.get("title") == "SBCSchema"
    assert "plan_name" in sbc_schema.get("required", [])


def test_inactive_tenant():
    workspace_dir = Path(__file__).resolve().parent.parent
    SingleTenantProvider.reset_instance()
    provider = SingleTenantProvider.get_instance(workspace_dir)

    provider.tenant.active = False
    assert provider.access_service.can_access("INVOICE") is False
    assert provider.access_service.get_enabled_modules() == []

    # Reset back to active
    provider.tenant.active = True
