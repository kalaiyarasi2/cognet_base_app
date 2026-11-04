with open('Sales team - Copy/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '''# Patch rpve_api to log executions to converter.db
try:
    rpve_mod = sys.modules.get("rpve_api")
    if rpve_mod and hasattr(rpve_mod, "process_invoice_data"):
        _orig_rpve_process = rpve_mod.process_invoice_data
        async def _fixed_rpve_process(file_path, original_filename, out_dir=None):
            try:
                from database.poc_db import log_universal
                log_universal(
                    module="RPVE Extractor",
                    action="extract",
                    file_name=str(original_filename),
                    status="STARTED",
                    details="Starting RPVE invoice extraction",
                    processed_by="kalaiyarasig@cognethro.com"
                )
            except Exception:
                pass

            try:
                result = await _orig_rpve_process(file_path, original_filename, out_dir=out_dir)
                try:
                    from database.poc_db import log_universal
                    log_universal(
                        module="RPVE Extractor",
                        action="extract",
                        file_name=str(original_filename),
                        status="SUCCESS",
                        details="RPVE benefit invoice extracted successfully",
                        processed_by="kalaiyarasig@cognethro.com"
                    )
                except Exception:
                    pass
                return result
            except Exception as e:
                try:
                    from database.poc_db import log_universal
                    log_universal(
                        module="RPVE Extractor",
                        action="extract",
                        file_name=str(original_filename),
                        status="FAILED",
                        details=str(e),
                        processed_by="kalaiyarasig@cognethro.com"
                    )
                except Exception:
                    pass
                raise e

        rpve_mod.process_invoice_data = _fixed_rpve_process
        print("[INIT] Patched rpve_api to log to converter.db")
except Exception as _rp_err:
    print(f"[WARN] Failed to patch rpve_api: {_rp_err}")'''

replacement = '''# Patch rpve_api and job_worker to unify token logging & write to converter.db
try:
    rpve_mod = sys.modules.get("rpve_api")
    if rpve_mod and hasattr(rpve_mod, "process_invoice_data"):
        _orig_rpve_process = rpve_mod.process_invoice_data
        async def _fixed_rpve_process(file_path, original_filename, out_dir=None):
            import os
            os.environ["COGNET_ACTIVE_FILE_NAME"] = str(original_filename)
            try:
                from core.universal_token_monitor import set_context
                set_context(poc_name="RPVE", file_name=str(original_filename))
            except Exception:
                pass
            try:
                from database.poc_db import log_universal
                log_universal(
                    module="RPVE Extractor",
                    action="extract",
                    file_name=str(original_filename),
                    status="STARTED",
                    details="Starting RPVE invoice extraction",
                    processed_by="kalaiyarasig@cognethro.com"
                )
            except Exception:
                pass

            try:
                result = await _orig_rpve_process(file_path, original_filename, out_dir=out_dir)
                try:
                    from database.poc_db import log_universal
                    log_universal(
                        module="RPVE Extractor",
                        action="extract",
                        file_name=str(original_filename),
                        status="SUCCESS",
                        details="RPVE benefit invoice extracted successfully",
                        processed_by="kalaiyarasig@cognethro.com"
                    )
                except Exception:
                    pass
                return result
            except Exception as e:
                try:
                    from database.poc_db import log_universal
                    log_universal(
                        module="RPVE Extractor",
                        action="extract",
                        file_name=str(original_filename),
                        status="FAILED",
                        details=str(e),
                        processed_by="kalaiyarasig@cognethro.com"
                    )
                except Exception:
                    pass
                raise e

        rpve_mod.process_invoice_data = _fixed_rpve_process

    # Also patch job_worker._execute_job for async flow pipelines (PartnerMailFlow / /api/process-flow)
    rpve_dir = WORKSPACE_DIR / "rpve"
    if str(rpve_dir) not in sys.path:
        sys.path.insert(0, str(rpve_dir))
    import job_worker
    if hasattr(job_worker, "_execute_job"):
        _orig_execute_job = job_worker._execute_job
        def _monitored_execute_job(job_id: str):
            fname = "invoice.pdf"
            try:
                job_dir = job_worker.get_job_dir(job_id)
                input_dir = job_dir / "input"
                pdf_files = list(input_dir.glob("*.pdf"))
                if pdf_files:
                    fname = pdf_files[0].name

                # Unify token logger filename so chunk extractions aren't named 'document'
                import os
                os.environ["COGNET_ACTIVE_FILE_NAME"] = fname
                from core.universal_token_monitor import set_context
                set_context(poc_name="RPVE", file_name=fname)

                # Log START to converter.db (Universal POC DB Logs)
                from database.poc_db import log_universal
                log_universal(
                    module="RPVE Extractor",
                    action="extract",
                    file_name=fname,
                    status="STARTED",
                    details=f"Starting RPVE flow pipeline (job={job_id})",
                    processed_by="kalaiyarasig@cognethro.com"
                )
            except Exception:
                pass

            try:
                res = _orig_execute_job(job_id)
                try:
                    from database.poc_db import log_universal
                    log_universal(
                        module="RPVE Extractor",
                        action="extract",
                        file_name=fname,
                        status="SUCCESS",
                        details=f"RPVE extraction completed for {fname}",
                        processed_by="kalaiyarasig@cognethro.com"
                    )
                except Exception:
                    pass
                return res
            except Exception as _err:
                try:
                    from database.poc_db import log_universal
                    log_universal(
                        module="RPVE Extractor",
                        action="extract",
                        file_name=fname,
                        status="FAILED",
                        details=str(_err),
                        processed_by="kalaiyarasig@cognethro.com"
                    )
                except Exception:
                    pass
                raise _err

        job_worker._execute_job = _monitored_execute_job
        print("[INIT] Patched rpve_api & job_worker to log to converter.db & unify token names")
except Exception as _rp_err:
    print(f"[WARN] Failed to patch rpve_api / job_worker: {_rp_err}")

# One-time migration: merge split 'document' entries into their real file names
try:
    import sqlite3
    _db_path = WORKSPACE_DIR / "monitor" / "universal_token_usage.db"
    if _db_path.exists():
        _c = sqlite3.connect(str(_db_path), timeout=5.0)
        _c.execute("""
            UPDATE token_calls 
            SET file_name = 'BCBS Invoice April 2026_b3ab9bbc-caf6-4d7e-97a8-fdb539714fe9 1 1.pdf' 
            WHERE file_name = 'document' AND session_id LIKE '%851-1%'
        """)
        _c.commit()
        # Regenerate file summaries
        from core.universal_token_monitor import _rebuild_file_summary
        _rebuild_file_summary()
        _c.close()
except Exception:
    pass'''

if target in content:
    content = content.replace(target, replacement, 1)
    with open('Sales team - Copy/app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS")
else:
    print("TARGET NOT FOUND")

