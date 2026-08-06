import pytest
from pathlib import Path
from core.tenant.provider import SingleTenantProvider, MODULE_INVOICE, MODULE_SBC, MODULE_LOSS_RUN, MODULE_RENEWAL


def test_module_access_permissions():
    workspace_dir = Path(__file__).resolve().parent.parent
    SingleTenantProvider.reset_instance()
    provider = SingleTenantProvider.get_instance(workspace_dir)
    access_service = provider.access_service

    # Allowed modules
    assert access_service.can_access(MODULE_INVOICE) is True
    assert access_service.can_access(MODULE_SBC) is True
    assert access_service.can_access("invoice") is True
    assert access_service.can_access("sbc") is True

    # Denied modules
    assert access_service.can_access(MODULE_LOSS_RUN) is False
    assert access_service.can_access(MODULE_RENEWAL) is False
    assert access_service.can_access("loss_run") is False
    assert access_service.can_access("renewal") is False


def test_enabled_modules_list():
    workspace_dir = Path(__file__).resolve().parent.parent
    SingleTenantProvider.reset_instance()
    provider = SingleTenantProvider.get_instance(workspace_dir)

    enabled = provider.access_service.get_enabled_modules()
    assert set(enabled) == {"INVOICE", "SBC"}
