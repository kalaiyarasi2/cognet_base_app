import os
import re
import sys
import subprocess
import uuid
import shutil
import asyncio
import time
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from universal_trash import move_to_trash

app = FastAPI(title="Renewal Intellect API")

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"

INPUT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Explicit output endpoint with URL unquoting for filenames with spaces (%20)
@app.get("/output/{filename:path}")
async def get_output_file(filename: str):
    import urllib.parse
    decoded_name = urllib.parse.unquote(filename)
    target_path = OUTPUT_DIR / decoded_name
    
    if not target_path.exists():
        target_path = OUTPUT_DIR / filename
        
    if not target_path.exists():
        for f in OUTPUT_DIR.iterdir():
            if f.name.lower() in (decoded_name.lower(), filename.lower()):
                target_path = f
                break

    if not target_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found in output directory")
        
    return FileResponse(
        path=target_path,
        filename=target_path.name,
        media_type="application/octet-stream"
    )

# In-memory database of jobs
# job_id -> {
#     "job_id": str,
#     "status": "pending" | "processing" | "success" | "failed",
#     "invoice_name": str,
#     "census_name": str,
#     "invoice_size": int,
#     "census_size": int,
#     "created_at": float,
#     "completed_at": float | None,
#     "download_url": str | None,
#     "error": str | None,
#     "logs": str
# }
jobs = {}

def run_pipeline_sync(job_id: str, command: list, out_census_path: Path, log_path: Path, invoice_name: str, census_name: str, processed_by: str = "SYSTEM"):
    jobs[job_id]["status"] = "processing"
    
    # Try to import DB logger
    try:
        import sys
        workspace_root = str(BASE_DIR.parent.parent)
        if workspace_root not in sys.path:
            sys.path.insert(0, workspace_root)
        from database.poc_db import log_universal
    except ImportError:
        log_universal = None
    
    try:
        log_path.parent.mkdir(exist_ok=True)
        
        # Start subprocess synchronously (run in a separate thread so it doesn't block the main event loop)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            cwd=str(BASE_DIR)
        )
        
        # Stream stdout line by line as it is produced
        with open(log_path, "w", encoding="utf-8") as f:
            for line in process.stdout:
                # Stream to backend terminal
                sys.stdout.write(line)
                sys.stdout.flush()
                
                # Save to log file
                f.write(line)
                f.flush()
                
                # Update in-memory job log
                jobs[job_id]["logs"] += line
                
        process.wait()
        
        if process.returncode == 0:
            jobs[job_id]["status"] = "success"
            jobs[job_id]["completed_at"] = time.time()
            jobs[job_id]["download_url"] = f"http://localhost:8000/output/{out_census_path.name}"
            jobs[job_id]["rates_json_url"] = f"http://localhost:8000/output/extracted_rates_{job_id}.json"
            print(f"Job {job_id} completed successfully.", flush=True)
            
            if log_universal:
                log_universal("RENEWAL_PROCESS", "Census Roster Rate Audit", f"{census_name} & {invoice_name}", "SUCCESS", f"http://localhost:8000/output/{out_census_path.name}", processed_by=processed_by)
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["completed_at"] = time.time()
            jobs[job_id]["error"] = f"Pipeline process exited with returncode {process.returncode}."
            print(f"Job {job_id} failed with returncode {process.returncode}.", flush=True)
            
            if log_universal:
                log_universal("RENEWAL_PROCESS", "Census Roster Rate Audit", f"{census_name} & {invoice_name}", "FAILED", f"Pipeline process exited with returncode {process.returncode}.", processed_by=processed_by)
            
    except Exception as e:
        import traceback
        err_msg = f"Exception in job {job_id}:\n{e}\n{traceback.format_exc()}"
        print(err_msg, flush=True)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["completed_at"] = time.time()
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["logs"] += f"\n[ERROR] {err_msg}"
        
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[ERROR] {err_msg}")
        except Exception:
            pass
            
        if log_universal:
            try:
                log_universal("RENEWAL_PROCESS", "Census Roster Rate Audit", f"{census_name} & {invoice_name}", "FAILED", str(e), processed_by=processed_by)
            except Exception:
                pass

@app.post("/api/process")
async def process_renewal(
    request: Request,
    invoice: UploadFile = File(...),
    census: UploadFile = File(...)
):
    try:
        # Generate unique IDs for the files
        job_id = str(uuid.uuid4())
        
        # Save uploaded files
        invoice_path = INPUT_DIR / f"{job_id}_{invoice.filename}"
        census_path = INPUT_DIR / f"{job_id}_{census.filename}"
        census_stem = Path(census.filename).stem
        # Strip any leading UUID job-prefix (e.g. "<uuid>_original" → "original")
        _uuid_re = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_', re.IGNORECASE)
        clean_census_stem = _uuid_re.sub('', census_stem)
        out_census_name = f"{clean_census_stem}_updated_census_{job_id}.xlsx"
        out_census_path = OUTPUT_DIR / out_census_name
        log_path = OUTPUT_DIR / f"logs_{job_id}.txt"

        invoice_contents = await invoice.read()
        with open(invoice_path, "wb") as buffer:
            buffer.write(invoice_contents)
            
        census_contents = await census.read()
        with open(census_path, "wb") as buffer:
            buffer.write(census_contents)
            
        invoice_size = len(invoice_contents)
        census_size = len(census_contents)
            
        # Run the backend python script as a subprocess
        # Use sys.executable to ensure subprocess uses the active virtual environment
        python_exe = sys.executable
        
        script_path = str(BASE_DIR / "invoice_census_audit.py")
        
        command = [
            python_exe,
            "-u",  # Unbuffered binary stdout and stderr
            script_path,
            "--census", str(census_path),
            "--invoices", str(invoice_path),
            "--out-census", str(out_census_path)
        ]
        
        # Initialize job metadata
        jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "invoice_name": invoice.filename,
            "census_name": census.filename,
            "invoice_size": invoice_size,
            "census_size": census_size,
            "created_at": time.time(),
            "completed_at": None,
            "download_url": None,
            "rates_json_url": None,
            "error": None,
            "logs": ""
        }
        
        processed_by = request.headers.get("X-Processed-By") or "SYSTEM"
        
        # Start worker task in a background thread to prevent Blocking IOError & Windows loop limits
        asyncio.create_task(asyncio.to_thread(run_pipeline_sync, job_id, command, out_census_path, log_path, invoice.filename, census.filename, processed_by))
        
        # Return job info immediately (without full logs)
        return JSONResponse({k: v for k, v in jobs[job_id].items() if k != "logs"})
        
    except Exception as e:
        print(f"Exception: {e}", flush=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs")
async def list_jobs():
    job_list = []
    for job_id, job in jobs.items():
        summary = {k: v for k, v in job.items() if k != "logs"}
        summary["log_length"] = len(job["logs"])
        job_list.append(summary)
        
    # Sort by created_at descending
    job_list.sort(key=lambda x: x["created_at"], reverse=True)
    return JSONResponse(job_list)

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(jobs[job_id])

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job = jobs[job_id]
    invoice_path = INPUT_DIR / f"{job_id}_{job['invoice_name']}"
    census_path = INPUT_DIR / f"{job_id}_{job['census_name']}"
    census_stem = Path(job['census_name']).stem
    _uuid_re = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_', re.IGNORECASE)
    clean_census_stem = _uuid_re.sub('', census_stem)
    out_census_path = OUTPUT_DIR / f"{clean_census_stem}_updated_census_{job_id}.xlsx"
    rates_json_path = OUTPUT_DIR / f"extracted_rates_{job_id}.json"
    log_path = OUTPUT_DIR / f"logs_{job_id}.txt"
    
    for path in (invoice_path, census_path, out_census_path, rates_json_path, log_path):
        try:
            if path.exists():
                move_to_trash(path, module_name="Renewal_process")
        except Exception:
            pass
            
    del jobs[job_id]
    return JSONResponse({"status": "success", "message": f"Job deleted successfully."})

if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True, access_log=False)
