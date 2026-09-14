"""
partner_mail_flow.py - Dedicated Mail Ingestion & Multi-Tenant Submission Orchestrator

Monitors a designated inbox, classifies & extracts ACORD and Loss Run documents,
and automatically transforms and dispatches the unified submission payload to the
partner/tenant endpoint using the Config-Driven Submission Engine.
"""

from __future__ import annotations

import os
import sys
import time
import json
import base64
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

# Setup workspace directory
WORKSPACE_DIR = Path(__file__).parent.resolve()
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [PARTNER-FLOW] %(message)s"
)
logger = logging.getLogger("PartnerMailFlow")

# Load environment configurations
from dotenv import load_dotenv
load_dotenv(WORKSPACE_DIR / ".env")

# Core imports
from core.submission.submission_service import SubmissionService
from core.tenant.loaders import TenantConfigLoader

# Optional DB and Outlook agents
try:
    from database import poc_db
    _poc_db_ok = True
except Exception as _db_err:
    poc_db = None
    _poc_db_ok = False
    logger.warning("poc_db not available: %s", _db_err)

try:
    OUTLOOK_AGENT_DIR = WORKSPACE_DIR / "Outlook_Agent"
    if str(OUTLOOK_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(OUTLOOK_AGENT_DIR))
    from outlook_agent_module import OutlookAgentModule, _mark_read
except Exception as _agent_err:
    OutlookAgentModule = None
    _mark_read = None
    logger.warning("OutlookAgentModule not available: %s", _agent_err)

# Extraction imports from start_flow
from start_flow import (
    run_local_extraction,
    classifier_extract,
    load_categories_from_env,
    DocumentClassifier,
    get_active_refresh_token,
)


class PartnerMailFlowOrchestrator:
    """
    Orchestrates dedicated email intake, extraction, and partner submission.
    """

    def __init__(self, tenant_folder: str = "client_a"):
        self.tenant_folder = tenant_folder
        self.submission_service = SubmissionService(workspace_dir=WORKSPACE_DIR)
        self.config_loader = TenantConfigLoader(base_dir=WORKSPACE_DIR)
        self.submission_config = self.config_loader.load_submission_config(tenant_folder)
        self.staging_dir = WORKSPACE_DIR / "temp_partner_staging"
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self._processed_msg_ids = set()

    def is_submission_enabled(self) -> bool:
        return self.submission_config.enabled

    async def process_email_package(
        self,
        email_item: Dict[str, Any],
        downloaded_pdfs: List[Path],
        token: str = "",
    ) -> Dict[str, Any]:
        """
        Processes all attachments for an email submission, runs GPU extraction,
        and submits the unified payload via SubmissionService.
        """
        sender_val = email_item.get("sender") or email_item.get("from") or {}
        if isinstance(sender_val, dict):
            sender_email = sender_val.get("emailAddress", {}).get("address", "unknown@sender.com")
        elif isinstance(sender_val, str):
            sender_email = sender_val
        else:
            sender_email = "unknown@sender.com"

        subject = str(email_item.get("subject", "No Subject"))
        message_id = str(email_item.get("id", ""))
        received_time = str(email_item.get("receivedDateTime", ""))

        logger.info("=" * 60)
        logger.info("Processing Email Submission: Sender=%s | Subject='%s'", sender_email, subject)
        logger.info("=" * 60)

        categories = load_categories_from_env()
        classifier = DocumentClassifier(categories=categories)

        acord_json_data: Optional[Dict[str, Any]] = None
        loss_run_json_data: Optional[Dict[str, Any]] = None
        source_pdf_paths: List[str] = []

        for pdf_path in downloaded_pdfs:
            if not pdf_path.exists() or not pdf_path.name.lower().endswith(".pdf"):
                continue

            source_pdf_paths.append(str(pdf_path.resolve()))
            logger.info("Classifying document: %s", pdf_path.name)

            try:
                text, pdf_type, rotation = classifier_extract(pdf_path, max_pages=3)
                category, score = classifier.classify(text)
            except Exception as e:
                logger.error("Classification error for %s: %s", pdf_path.name, e)
                category, score = "Others", 0.0
                text = ""

            logger.info("Category determined: %s (Confidence: %.2f)", category, score)

            # Run GPU / Local Extraction
            extract_result = await run_local_extraction(category, pdf_path, text)
            
            cat_upper = category.upper()
            json_target = extract_result.get("json") or extract_result.get("json_path")
            json_content = None
            if json_target and os.path.exists(json_target):
                try:
                    with open(json_target, "r", encoding="utf-8") as f:
                        json_content = json.load(f)
                except Exception as ex:
                    logger.warning("Failed to load extracted JSON (%s): %s", json_target, ex)
            elif isinstance(extract_result.get("data"), dict):
                json_content = extract_result.get("data")
            elif isinstance(extract_result, dict) and any(k in extract_result for k in ["Applicant", "SummaryLevel", "claims"]):
                json_content = extract_result

            if "ACORD" in cat_upper or "WORK_COMPENSATION" in cat_upper or "COMPENSATION" in cat_upper or "ACORD" in pdf_path.name.upper():
                acord_json_data = json_content or acord_json_data
            elif "LOSS" in cat_upper or "CLAIM" in cat_upper or "INSURANCE" in cat_upper or "BERKLEY" in pdf_path.name.upper():
                loss_run_json_data = json_content or loss_run_json_data

        # Execute submission via SubmissionService
        logger.info("Invoking Multi-Tenant Submission Service for tenant '%s'...", self.tenant_folder)
        submission_result = self.submission_service.process_and_submit(
            tenant_folder=self.tenant_folder,
            acord_data=acord_json_data,
            loss_run_data=loss_run_json_data,
            pdf_file_paths=source_pdf_paths,
            email_address=sender_email,
            extra_metadata={
                "subject": subject,
                "message_id": message_id,
                "received_at": received_time,
            }
        )

        status = submission_result.get("status", "UNKNOWN")
        logger.info("Submission Result: Status=%s | StatusCode=%s", status, submission_result.get("status_code"))

        # Log Audit entry into SQLite
        if _poc_db_ok:
            try:
                poc_db.log_universal(
                    module="PARTNER_SUBMISSION",
                    action=f"Tenant Submission ({self.tenant_folder})",
                    file_name=subject,
                    status=status,
                    details=json.dumps({
                        "sender": sender_email,
                        "status_code": submission_result.get("status_code"),
                        "error": submission_result.get("error"),
                        "pdf_count": len(source_pdf_paths),
                    }),
                    processed_by=sender_email
                )
            except Exception as db_err:
                logger.warning("Failed to log audit entry to converter.db: %s", db_err)

        # Mark Email Read in Outlook once processed
        if token and message_id and _mark_read:
            try:
                _mark_read(token, message_id)
                logger.info("Marked message %s as READ in mailbox.", message_id)
            except Exception as e:
                logger.warning("Could not mark message as read: %s", e)

        return submission_result

    async def run_listener(self, poll_interval: int = 60, user_email: Optional[str] = None, once: bool = False):
        """
        Continuously polls the designated mailbox and processes submissions.
        """
        # Resolve target email from argument, tenant config, or .env
        clean_tenant = self.tenant_folder.upper()
        resolved_email = (
            user_email
            or os.getenv(f"{clean_tenant}_MONITOR_EMAIL")
            or os.getenv(f"{clean_tenant.replace('_TEAM', '')}_MONITOR_EMAIL")
            or os.getenv("PARTNER_POC_MONITOR_EMAIL")
            or None
        )
        
        logger.info(
            "Starting Partner Mail Flow Listener for Tenant: '%s' | Monitored Mailbox: %s (Interval: %ds)",
            self.tenant_folder,
            resolved_email or "Default Connected Dashboard Account",
            poll_interval
        )
        
        while True:
            try:
                if OutlookAgentModule is not None:
                    agent = OutlookAgentModule(user_email=resolved_email)
                    refresh_token = get_active_refresh_token(resolved_email)
                    token = agent.get_access_token(refresh_token=refresh_token, allow_device_flow=False)
                    emails = agent.fetch_unread_emails(refresh_token=refresh_token) or []

                    if emails:
                        logger.info("Detected %d unread email(s).", len(emails))
                        for email in emails:
                            msg_id = str(email.get("id", str(time.time())))
                            if msg_id in self._processed_msg_ids:
                                continue

                            attachments = email.get("attachments", [])
                            if not attachments:
                                continue

                            msg_staging = self.staging_dir / msg_id
                            msg_staging.mkdir(parents=True, exist_ok=True)

                            downloaded = []
                            for att in attachments:
                                fname = att.get("filename") or att.get("name") or ""
                                if fname.lower().endswith(".pdf") and att.get("content_bytes"):
                                    fpath = msg_staging / fname
                                    fpath.write_bytes(base64.b64decode(att["content_bytes"]))
                                    downloaded.append(fpath)

                            if downloaded:
                                self._processed_msg_ids.add(msg_id)
                                await self.process_email_package(email, downloaded, token=token)
                    else:
                        logger.debug("No new unread emails.")

            except Exception as err:
                logger.error("Error during listener cycle: %s", err, exc_info=True)

            if once:
                break

            await asyncio.sleep(poll_interval)


def main():
    parser = argparse.ArgumentParser(description="Dedicated Partner Mail Ingestion & Submission Flow")
    parser.add_argument("--tenant", default="client_a", help="Tenant configuration code (default: client_a)")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds (default: 60)")
    parser.add_argument("--email", default=None, help="Target mailbox to monitor")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()

    orchestrator = PartnerMailFlowOrchestrator(tenant_folder=args.tenant)
    asyncio.run(orchestrator.run_listener(poll_interval=args.interval, user_email=args.email, once=args.once))


if __name__ == "__main__":
    main()
