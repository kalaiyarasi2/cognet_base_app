import pytest
from pathlib import Path
from core.tenant.storage import TenantStorageService, SecurityError


def test_storage_path_generation():
    workspace_dir = Path(__file__).resolve().parent.parent
    storage = TenantStorageService(workspace_dir, tenant_code="CLIENT_A")

    out_dir = storage.get_job_output_dir(module_code="INVOICE", job_id="job_test_123")
    expected_suffix = Path("output") / "CLIENT_A" / "INVOICE" / "job_test_123"
    assert str(out_dir).endswith(str(expected_suffix))
    assert out_dir.exists()


def test_path_traversal_prevention():
    workspace_dir = Path(__file__).resolve().parent.parent
    storage = TenantStorageService(workspace_dir, tenant_code="CLIENT_A")

    # Attempt path traversal via job_id
    with pytest.raises(SecurityError):
        storage.get_job_output_dir(module_code="INVOICE", job_id="../etc/passwd")

    # Attempt path traversal via module_code
    with pytest.raises(SecurityError):
        storage.get_job_output_dir(module_code="../INVOICE", job_id="job_test_123")

    # Attempt path traversal in filename
    with pytest.raises(SecurityError):
        storage.save_json_output(
            module_code="INVOICE",
            job_id="job_test_123",
            filename="../../secret.json",
            data={"test": "data"}
        )
