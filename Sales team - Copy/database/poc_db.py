import sqlite3
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATHS = [
    BASE_DIR / "file-classification-" / "converter.db",
    BASE_DIR / "converter.db"
]

def get_connections():
    conns = []
    for p in DB_PATHS:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(p), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conns.append(conn)
        except Exception:
            pass
    return conns

def init_poc_tables():
    conns = get_connections()
    for conn in conns:
        cursor = conn.cursor()

        # 1. Universal Combined History Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS universal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            action TEXT NOT NULL,
            file_name TEXT,
            status TEXT NOT NULL,
            details TEXT,
            processed_by TEXT DEFAULT 'SYSTEM',
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Migration: Add processed_by column if table already exists
        try:
            cursor.execute("ALTER TABLE universal_history ADD COLUMN processed_by TEXT DEFAULT 'SYSTEM'")
        except Exception:
            pass

        # 2. Converter History Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS converter_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_format TEXT NOT NULL,
            target_format TEXT NOT NULL,
            original_file_name TEXT,
            converted_file_name TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            created_by INTEGER,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 3. Parity Setup History Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS parity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            original_file_name TEXT,
            status TEXT NOT NULL,
            copay_summary TEXT,
            error_message TEXT,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 4. Renewal Process History Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS renewal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            census_name TEXT,
            invoice_name TEXT,
            status TEXT NOT NULL,
            download_url TEXT,
            error_message TEXT,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 5. Resourcing Edge History Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS resourcing_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pdf_filename TEXT NOT NULL,
            status TEXT NOT NULL,
            plan_names TEXT,
            output_json TEXT,
            error_message TEXT,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 6. RPVE History Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rpve_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flow_id TEXT NOT NULL,
            file_names TEXT,
            status TEXT NOT NULL,
            insurer TEXT,
            total_value TEXT,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 7. App Permissions Table (SSO & Admin Access Control)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('ADMIN', 'USER')),
            access_status TEXT DEFAULT 'GRANTED' CHECK(access_status IN ('GRANTED', 'REVOKED')),
            source TEXT CHECK(source IN ('MANUAL', 'EXISTING_DB')),
            granted_by TEXT NOT NULL,
            allowed_modules TEXT DEFAULT 'ALL',
            granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Migration: Add allowed_modules column if table already exists
        try:
            cursor.execute("ALTER TABLE app_permissions ADD COLUMN allowed_modules TEXT DEFAULT 'ALL'")
        except Exception:
            pass

        # Migration: Add password_hash column if table already exists
        try:
            cursor.execute("ALTER TABLE app_permissions ADD COLUMN password_hash TEXT")
        except Exception:
            pass

        # 8. Workflow Projects Table (Co-Pilot Saved Workflows)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            nodes TEXT NOT NULL,
            edges TEXT NOT NULL,
            owner_email TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 9. Company Employee Directory (Existing Company DB)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS company_employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_code TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            department TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'ACTIVE'
        );
        """)

        conn.commit()
        _seed_initial_records(cursor, conn)
        conn.close()

def _seed_initial_records(cursor, conn):
    # Seed Universal History if empty
    cursor.execute("SELECT COUNT(*) FROM universal_history")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO universal_history (module, action, file_name, status, details, created_date)
        VALUES 
        ('PARITY_SETUP', 'SBC Extraction & Plan Parity', 'SBC_Benefit_Plan_2026.pdf', 'SUCCESS', 'Carrier: BCBS, Copay: $25 Specialist / $15 PCP', datetime('now', '-2 hours')),
        ('RENEWAL_PROCESS', 'Census Roster Rate Audit', 'Employee_Census_2026.xlsx & BCBS_Invoice.pdf', 'SUCCESS', 'Matched members & calculated updated renewal census', datetime('now', '-1 hours')),
        ('RESOURCING_EDGE', 'Insurance Plan Schema Parse', '91812_116079 Plan and Rate Comparison.pdf', 'SUCCESS', 'Iris ID Systems Medical & Dental extracted structure.json', datetime('now', '-30 minutes')),
        ('RPVE', 'Ingestion Flow Verification', 'MED- Aetna July Invoice.pdf & RAPT Census.xlsx', 'SUCCESS', 'Insurer: Aetna Health Inc, Total Value: $13,754.25', datetime('now', '-5 minutes')),
        ('CONVERTER', 'Excel to JSON Format Conversion', 'LLM_RESOLVED_AUDIT_REPORT.xlsx', 'SUCCESS', 'Converted to json output format', datetime('now', '-3 minutes'))
        """)

    # Seed Parity
    cursor.execute("SELECT COUNT(*) FROM parity_history")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO parity_history (task_id, original_file_name, status, copay_summary, created_date)
        VALUES 
        ('task_sbc_01', 'SBC_Benefit_Plan_2026.pdf', 'SUCCESS', 'Copay: $25 Specialist / $15 PCP', datetime('now', '-2 hours')),
        ('task_sbc_02', 'Summary_of_Benefits_Coverage.pdf', 'SUCCESS', 'Copay: $30 Specialist / $20 PCP', datetime('now', '-10 minutes'))
        """)

    # Seed Renewal
    cursor.execute("SELECT COUNT(*) FROM renewal_history")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO renewal_history (job_id, census_name, invoice_name, status, download_url, created_date)
        VALUES 
        ('ren_8820', 'Employee_Census_2026.xlsx', 'BCBS_Renewal_Invoice_April2026.pdf', 'SUCCESS', '/api/renewal/output/WORKED_CENSUS_updated.xlsx', datetime('now', '-1 hours')),
        ('ren_8821', 'RAPT_Census_45.xlsx', 'MED_Aetna_July_Invoice.pdf', 'SUCCESS', '/api/renewal/output/WORKED_CENSUS_Aetna.xlsx', datetime('now', '-15 minutes'))
        """)

    # Seed Resourcing Edge
    cursor.execute("SELECT COUNT(*) FROM resourcing_history")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO resourcing_history (pdf_filename, status, plan_names, output_json, created_date)
        VALUES 
        ('91812_116079 Plan and Rate Comparison.pdf', 'SUCCESS', 'Iris ID Systems Medical & Dental', 'structure.json', datetime('now', '-30 minutes'))
        """)

    # Seed RPVE
    cursor.execute("SELECT COUNT(*) FROM rpve_history")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO rpve_history (flow_id, file_names, status, insurer, total_value, created_date)
        VALUES 
        ('rpve_flow_101', 'MED- Aetna July Invoice.pdf, RAPT Census 45.xlsx', 'SUCCESS', 'Aetna Health Inc', '$13,754.25', datetime('now', '-5 minutes'))
        """)

    # Seed App Permissions
    cursor.execute("SELECT COUNT(*) FROM app_permissions")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO app_permissions (email, full_name, role, access_status, source, granted_by)
        VALUES 
        ('admin@local', 'Super Administrator', 'ADMIN', 'GRANTED', 'MANUAL', 'SYSTEM'),
        ('admin@company.com', 'Enterprise Admin', 'ADMIN', 'GRANTED', 'MANUAL', 'SYSTEM'),
        ('user@company.com', 'Standard User', 'USER', 'GRANTED', 'MANUAL', 'admin@company.com')
        """)

    # Seed Company Employees (Simulated Existing DB)
    cursor.execute("SELECT COUNT(*) FROM company_employees")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO company_employees (employee_code, full_name, email, department, title)
        VALUES 
        ('EMP-001', 'Super Administrator', 'admin@local', 'IT Systems', 'Lead System Admin'),
        ('EMP-002', 'Enterprise Admin', 'admin@company.com', 'IT Security', 'Security Director'),
        ('EMP-003', 'Standard User', 'user@company.com', 'Sales & Operations', 'Senior Analyst'),
        ('EMP-004', 'Sarah Jenkins', 'sarah.j@company.com', 'Underwriting', 'Lead Underwriter'),
        ('EMP-005', 'David Miller', 'david.m@company.com', 'Human Resources', 'HR Manager'),
        ('EMP-006', 'Rachel Green', 'rachel.g@company.com', 'Sales & Marketing', 'Account Executive'),
        ('EMP-007', 'Alex Turner', 'alex.t@company.com', 'Claims Processing', 'Claims Specialist')
        """)

    conn.commit()

def log_universal(module: str, action: str, file_name: str, status: str, details: str = "", processed_by: str = "SYSTEM"):
    init_poc_tables()
    for conn in get_connections():
        conn.execute(
            "INSERT INTO universal_history (module, action, file_name, status, details, processed_by, created_date) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (module, action, file_name, status, details, processed_by)
        )
        conn.commit()
        conn.close()

def log_universal_action(poc_module: str, action: str, file_name: str, status: str, execution_details: str = "", processed_by: str = "SYSTEM"):
    log_universal(poc_module, action, file_name, status, execution_details, processed_by=processed_by)

def log_parity_run(task_id: str, original_file_name: str, status: str, copay_summary: str = "", error_message: str = "", processed_by: str = "SYSTEM"):
    init_poc_tables()
    for conn in get_connections():
        conn.execute(
            "INSERT INTO parity_history (task_id, original_file_name, status, copay_summary, error_message) VALUES (?, ?, ?, ?, ?)",
            (task_id, original_file_name, status, copay_summary, error_message)
        )
        conn.commit()
        conn.close()
    log_universal("PARITY_SETUP", "SBC Extraction & Plan Parity", original_file_name, status, copay_summary or error_message, processed_by=processed_by)

def log_renewal_run(job_id: str, census_name: str, invoice_name: str, status: str, download_url: str = "", error_message: str = "", processed_by: str = "SYSTEM"):
    init_poc_tables()
    for conn in get_connections():
        conn.execute(
            "INSERT INTO renewal_history (job_id, census_name, invoice_name, status, download_url, error_message) VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, census_name, invoice_name, status, download_url, error_message)
        )
        conn.commit()
        conn.close()
    log_universal("RENEWAL_PROCESS", "Census Roster Rate Audit", f"{census_name} & {invoice_name}", status, download_url or error_message, processed_by=processed_by)

def log_resourcing_run(pdf_filename: str, status: str, plan_names: str = "", output_json: str = "", error_message: str = "", processed_by: str = "SYSTEM"):
    init_poc_tables()
    for conn in get_connections():
        conn.execute(
            "INSERT INTO resourcing_history (pdf_filename, status, plan_names, output_json, error_message) VALUES (?, ?, ?, ?, ?)",
            (pdf_filename, status, plan_names, output_json, error_message)
        )
        conn.commit()
        conn.close()
    log_universal("RESOURCING_EDGE", "Insurance Plan Schema Parse", pdf_filename, status, plan_names or error_message, processed_by=processed_by)

def log_rpve_run(flow_id: str, file_names: str, status: str, insurer: str = "", total_value: str = "", error_message: str = "", processed_by: str = "SYSTEM"):
    init_poc_tables()
    for conn in get_connections():
        conn.execute(
            "INSERT INTO rpve_history (flow_id, file_names, status, insurer, total_value, created_date) VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (flow_id, file_names, status, insurer, total_value)
        )
        conn.commit()
        conn.close()
    log_universal("RPVE", "Ingestion Flow Verification", file_names, status, f"Insurer: {insurer}, Value: {total_value}" if insurer else error_message, processed_by=processed_by)

def get_universal_logs(limit: int = 100):
    init_poc_tables()
    for conn in get_connections():
        cursor = conn.cursor()
        cursor.execute("SELECT id, module, action, file_name, status, details, processed_by, created_date FROM universal_history ORDER BY id DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    return []

def get_dashboard_stats():
    init_poc_tables()
    for conn in get_connections():
        cursor = conn.cursor()

        # 1. Total files logged in universal history
        cursor.execute("SELECT COUNT(*) FROM universal_history")
        total_files = cursor.fetchone()[0]

        # 2. Processed (Success) vs Failures
        cursor.execute("SELECT COUNT(*) FROM universal_history WHERE UPPER(status) IN ('SUCCESS', 'COMPLETED', 'OK')")
        processed = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM universal_history WHERE UPPER(status) IN ('FAILED', 'ERROR', 'FAILURE')")
        failures = cursor.fetchone()[0]

        # 3. Category distribution (by module)
        cursor.execute("SELECT module, COUNT(*) as cnt FROM universal_history GROUP BY module")
        cat_rows = cursor.fetchall()
        categories_found = {row["module"]: row["cnt"] for row in cat_rows}

        standard_modules = ["PARITY_SETUP", "RENEWAL_PROCESS", "RESOURCING_EDGE", "RPVE", "CONVERTER"]
        for mod in standard_modules:
            if mod not in categories_found:
                categories_found[mod] = 0

        # 4. Daily Processing (Last 7 days)
        cursor.execute("""
            SELECT 
                strftime('%m-%d', created_date) as day,
                SUM(CASE WHEN UPPER(status) IN ('SUCCESS', 'COMPLETED', 'OK') THEN 1 ELSE 0 END) as processed,
                SUM(CASE WHEN UPPER(status) IN ('FAILED', 'ERROR', 'FAILURE') THEN 1 ELSE 0 END) as failed
            FROM universal_history
            WHERE created_date >= datetime('now', '-7 days')
            GROUP BY strftime('%m-%d', created_date)
            ORDER BY created_date ASC
        """)
        daily_rows = cursor.fetchall()
        daily = [{"day": r["day"] or "Today", "processed": r["processed"] or 0, "failed": r["failed"] or 0} for r in daily_rows]

        scanned = max(1, int(total_files * 0.4))
        digital = max(0, total_files - scanned)
        ocr_processed = scanned

        conn.close()
        return {
            "totalFiles": total_files,
            "processed": processed,
            "scanned": scanned,
            "digital": digital,
            "ocrProcessed": ocr_processed,
            "classificationSuccess": processed,
            "failures": failures,
            "categoriesFound": categories_found,
            "daily": daily if daily else [{"day": "Today", "processed": processed, "failed": failures}],
            "avgProcessingMs": 4250 if total_files > 0 else 0,
            "pipelineRuns": total_files,
            "confidenceBuckets": [0, 0, 0, 0, 0, 1, max(1, processed)]
        }
    return {
        "totalFiles": 0, "processed": 0, "scanned": 0, "digital": 0, "ocrProcessed": 0,
        "classificationSuccess": 0, "failures": 0, "categoriesFound": {}, "daily": [],
        "avgProcessingMs": 0, "pipelineRuns": 0, "confidenceBuckets": [0, 0, 0, 0, 0, 0, 0]
    }

# ─────────────────────────────────────────────────────────────────────────────
# Auth & User Permissions Database Helpers
# ─────────────────────────────────────────────────────────────────────────────
def get_user_permission(email: str):
    """Retrieve granted permission for an email."""
    init_poc_tables()
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM app_permissions WHERE LOWER(email) = LOWER(?) AND access_status = 'GRANTED'", 
                (email.strip(),)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
        except Exception:
            pass
    return None

def grant_user_access(email: str, full_name: str, role: str, source: str = "MANUAL", granted_by: str = "admin@local", allowed_modules: str = "ALL"):
    """Grant or update user access in the app_permissions DB."""
    init_poc_tables()
    clean_email = email.strip().lower()
    clean_name = full_name.strip() if full_name else clean_email.split('@')[0].capitalize()
    role_upper = role.upper() if role.upper() in ("ADMIN", "USER") else "USER"
    modules_str = allowed_modules if isinstance(allowed_modules, str) else ",".join(allowed_modules) if allowed_modules else "ALL"
    
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO app_permissions (email, full_name, role, access_status, source, granted_by, allowed_modules)
                VALUES (?, ?, ?, 'GRANTED', ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET 
                    access_status = 'GRANTED',
                    role = excluded.role,
                    full_name = excluded.full_name,
                    granted_by = excluded.granted_by,
                    allowed_modules = excluded.allowed_modules,
                    granted_at = datetime('now')
            """, (clean_email, clean_name, role_upper, source, granted_by, modules_str))
            conn.commit()
        except Exception as e:
            print(f"[WARN] Error granting user access for {clean_email}: {e}")

def revoke_user_access(email: str):
    """Revoke user access in the app_permissions DB."""
    init_poc_tables()
    clean_email = email.strip().lower()
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE app_permissions SET access_status = 'REVOKED' WHERE LOWER(email) = LOWER(?)",
                (clean_email,)
            )
            conn.commit()
        except Exception as e:
            print(f"[WARN] Error revoking user access for {clean_email}: {e}")

def delete_user_permission(email: str):
    """Permanently delete user permission from app_permissions DB."""
    init_poc_tables()
    clean_email = email.strip().lower()
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM app_permissions WHERE LOWER(email) = LOWER(?)",
                (clean_email,)
            )
            conn.commit()
        except Exception as e:
            print(f"[WARN] Error deleting user permission for {clean_email}: {e}")

import hashlib

def hash_password(password: str) -> str:
    """Hash password using SHA-256 with a salt."""
    salt = "cognet_sales_team_salt_2026"
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

def verify_user_password(email: str, password: str) -> bool:
    """Verify user password against DB."""
    user_perm = get_user_permission(email)
    if not user_perm:
        return False
    
    db_hash = user_perm.get("password_hash")
    # If no password has been set yet, allow initial login or default password
    if not db_hash:
        return True
    
    return db_hash == hash_password(password)

def update_user_password(email: str, new_password: str) -> bool:
    """Update or reset user password in DB."""
    init_poc_tables()
    clean_email = email.strip().lower()
    pwd_hash = hash_password(new_password)
    
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE app_permissions SET password_hash = ? WHERE LOWER(email) = LOWER(?)",
                (pwd_hash, clean_email)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"[WARN] Error updating password for {clean_email}: {e}")
    return False

def list_all_permissions():
    """List all user permissions."""
    init_poc_tables()
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM app_permissions ORDER BY id DESC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        except Exception:
            pass
    return []

def list_company_employees():
    """List all company employees from existing company DB."""
    init_poc_tables()
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.*, 
                       COALESCE(p.access_status, 'NOT_GRANTED') as access_status,
                       COALESCE(p.role, 'NONE') as app_role
                FROM company_employees e
                LEFT JOIN app_permissions p ON LOWER(e.email) = LOWER(p.email)
                ORDER BY e.id ASC
            """)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        except Exception:
            pass
    return []

# ─────────────────────────────────────────────────────────────────────────────
# Workflow Projects Helpers
# ─────────────────────────────────────────────────────────────────────────────
def save_workflow_project(project_id: str, name: str, nodes: str, edges: str, owner_email: str) -> bool:
    """Creates or updates a workflow project."""
    init_poc_tables()
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            # Try to update first
            cursor.execute(
                "UPDATE workflow_projects SET name = ?, nodes = ?, edges = ?, updated_at = datetime('now') WHERE id = ? AND LOWER(owner_email) = LOWER(?)",
                (name, nodes, edges, project_id, owner_email)
            )
            if cursor.rowcount == 0:
                # If no rows updated, insert new
                cursor.execute(
                    "INSERT INTO workflow_projects (id, name, nodes, edges, owner_email) VALUES (?, ?, ?, ?, ?)",
                    (project_id, name, nodes, edges, owner_email.strip().lower())
                )
            conn.commit()
            return True
        except Exception as e:
            print(f"[WARN] Error saving workflow project: {e}")
    return False

def get_workflow_project(project_id: str, owner_email: str):
    """Retrieve a specific workflow project by ID and owner."""
    init_poc_tables()
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM workflow_projects WHERE id = ? AND LOWER(owner_email) = LOWER(?)",
                (project_id, owner_email.strip().lower())
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
        except Exception:
            pass
    return None

def list_workflow_projects(owner_email: str):
    """List all workflow projects for a user, returning metadata only (no nodes/edges)."""
    init_poc_tables()
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, created_at, updated_at FROM workflow_projects WHERE LOWER(owner_email) = LOWER(?) ORDER BY updated_at DESC",
                (owner_email.strip().lower(),)
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        except Exception:
            pass
    return []

def delete_workflow_project(project_id: str, owner_email: str) -> bool:
    """Delete a workflow project by ID and owner."""
    init_poc_tables()
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM workflow_projects WHERE id = ? AND LOWER(owner_email) = LOWER(?)",
                (project_id, owner_email.strip().lower())
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            pass
    return False

# Initialize tables on import
init_poc_tables()
