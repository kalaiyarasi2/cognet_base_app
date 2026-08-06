import pytest
import tempfile
import asyncio
from pathlib import Path
from core.tenant.pipeline import DocumentPipeline
from core.tenant.provider import SingleTenantProvider


def test_invoice_pipeline_execution():
    workspace_dir = Path(__file__).resolve().parent.parent
    SingleTenantProvider.reset_instance()
    pipeline = DocumentPipeline(workspace_dir)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4 dummy invoice content")
        tmp_path = tmp.name

    res = asyncio.run(pipeline.process_document(
        input_path=tmp_path,
        module_code="INVOICE",
        original_file_name="sample_invoice.pdf"
    ))

    assert res.status in ["COMPLETED", "MANUAL_REVIEW"]
    assert res.tenant_id == 1
    assert res.tenant_code == "CLIENT_A"
    assert res.module_code == "INVOICE"
    assert res.output_path is not None
    assert Path(res.output_path).exists()


def test_denied_module_pipeline():
    workspace_dir = Path(__file__).resolve().parent.parent
    SingleTenantProvider.reset_instance()
    pipeline = DocumentPipeline(workspace_dir)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4 dummy loss run content")
        tmp_path = tmp.name

    res = asyncio.run(pipeline.process_document(
        input_path=tmp_path,
        module_code="LOSS_RUN",
        original_file_name="sample_loss_run.pdf"
    ))

    assert res.status == "ACCESS_DENIED"
    assert "disabled for tenant" in res.error_message.lower()


def test_low_confidence_manual_review():
    workspace_dir = Path(__file__).resolve().parent.parent
    SingleTenantProvider.reset_instance()
    pipeline = DocumentPipeline(workspace_dir)

    # Force low confidence thresholds
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4 test dummy")
        tmp_path = tmp.name

    # Patch adapter to simulate low confidence
    from core.tenant.adapters import BaseModuleAdapter
    class LowConfAdapter(BaseModuleAdapter):
        async def process(self, context):
            return {
                "extracted_data": {"invoice_number": "INV-123"},
                "confidence_score": 0.40,
                "module_code": "INVOICE"
            }

    pipeline.registry.register("INVOICE", LowConfAdapter())

    res = asyncio.run(pipeline.process_document(
        input_path=tmp_path,
        module_code="INVOICE",
        original_file_name="low_conf_invoice.pdf"
    ))

    assert res.status == "MANUAL_REVIEW"
    assert res.confidence_score == 0.40
