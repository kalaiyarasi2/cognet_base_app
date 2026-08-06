import pytest
import tempfile
import asyncio
from unittest.mock import MagicMock, patch
from pathlib import Path
from core.tenant.provider import SingleTenantProvider
from core.tenant.pipeline import DocumentPipeline


@pytest.fixture
def mock_external_services(monkeypatch):
    """Mocks external cloud and AI APIs."""
    # Mock OpenAI
    mock_openai_client = MagicMock()
    monkeypatch.setattr("openai.OpenAI", lambda *args, **kwargs: mock_openai_client)

    # Mock Requests / MS Graph
    monkeypatch.setattr("requests.get", MagicMock(return_value=MagicMock(status_code=200, json=lambda: {})))
    monkeypatch.setattr("requests.post", MagicMock(return_value=MagicMock(status_code=200, json=lambda: {})))

    return mock_openai_client


def test_email_tenant_context_and_isolation(mock_external_services):
    workspace_dir = Path(__file__).resolve().parent.parent
    SingleTenantProvider.reset_instance()
    provider = SingleTenantProvider.get_instance(workspace_dir)

    assert provider.tenant.tenant_id == 1
    assert provider.tenant.tenant_code == "CLIENT_A"

    # Simulate email attachment pipeline calls
    pipeline = DocumentPipeline(workspace_dir)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp1, \
         tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp2:
        tmp1.write(b"%PDF-1.4 Attachment 1 SBC")
        tmp2.write(b"%PDF-1.4 Attachment 2 Renewal Disabled")
        att1_path = tmp1.name
        att2_path = tmp2.name

    # Attachment 1: SBC (Allowed)
    res1 = asyncio.run(pipeline.process_document(att1_path, "SBC", "attachment1.pdf"))
    assert res1.status in ["COMPLETED", "MANUAL_REVIEW"]
    assert res1.tenant_id == 1
    assert res1.tenant_code == "CLIENT_A"

    # Attachment 2: RENEWAL (Disabled)
    res2 = asyncio.run(pipeline.process_document(att2_path, "RENEWAL", "attachment2.pdf"))
    assert res2.status == "ACCESS_DENIED"
    assert res2.tenant_id == 1

    # Verify that failure of Attachment 2 does NOT throw or halt execution
    assert res1 is not None and res2 is not None
