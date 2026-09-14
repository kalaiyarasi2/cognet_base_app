"""
test_local_submission_run.py - Standalone Local Test for Multi-Tenant Submission

Runs classification, extraction, payload transformation, and submission using
local sample files (EKS Ventures ACORD and BerkleyNet Loss Runs).
"""

import os
import sys
import json
import asyncio
from pathlib import Path

WORKSPACE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(WORKSPACE_DIR))

from dotenv import load_dotenv
load_dotenv(WORKSPACE_DIR / ".env")

from partner_mail_flow import PartnerMailFlowOrchestrator

async def run_test():
    print("=" * 70)
    print("STARTING LOCAL SUBMISSION PIPELINE TEST")
    print("=" * 70)

    # 1. Check for sample PDF files in parent or local directory
    root_dir = WORKSPACE_DIR.parent
    sample_acord = root_dir / "EKS Ventures, Inc. - Acord.pdf"
    sample_lossrun = root_dir / "BerkleyNet 24-25.pdf"

    pdf_files = []
    for f in [sample_acord, sample_lossrun]:
        if f.exists():
            pdf_files.append(f)
            print(f"[FOUND] Sample PDF: {f.name}")
        else:
            print(f"[MISSING] Sample file not found: {f}")

    if not pdf_files:
        print("[ERROR] No sample PDF files found to test.")
        return

    # 2. Setup mock email item
    mock_email = {
        "id": "LOCAL_TEST_SUBMISSION_001",
        "sender": {"emailAddress": {"address": "test_broker@cognethro.com"}},
        "subject": "Commercial Lines Submission - EKS Ventures (ACORD + Loss Runs)",
        "receivedDateTime": "2026-09-11T12:00:00Z"
    }

    # 3. Initialize Orchestrator for client_a
    orchestrator = PartnerMailFlowOrchestrator(tenant_folder="client_a")

    # 4. Run end-to-end processing package
    print("\n--> Processing package through AI Classifier, Extractor & Transformer...\n")
    result = await orchestrator.process_email_package(
        email_item=mock_email,
        downloaded_pdfs=pdf_files,
        token="mock_local_token"
    )

    print("\n" + "=" * 70)
    print("EXECUTION RESULT SUMMARY:")
    print("=" * 70)
    print(f"Status:      {result.get('status')}")
    print(f"Status Code: {result.get('status_code')}")
    print(f"Tenant:      {result.get('tenant_folder')}")

    if result.get("transformed_payload"):
        print("\n--- GENERATED UNIFIED JSON PAYLOAD (FIRST 500 CHARS) ---")
        payload_str = json.dumps(result["transformed_payload"], indent=2)
        print(payload_str[:500] + "\n... [truncated] ...")
        
        # Save output JSON for review
        output_json_path = WORKSPACE_DIR / "latest_test_submission_payload.json"
        with open(output_json_path, "w", encoding="utf-8") as out_f:
            out_f.write(payload_str)
        print(f"\n[SAVED] Full output JSON saved to: {output_json_path}")

if __name__ == "__main__":
    asyncio.run(run_test())
