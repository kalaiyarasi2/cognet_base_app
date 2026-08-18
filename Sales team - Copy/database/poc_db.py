import sqlite3
import os
import random
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "converter.db"

def get_connections():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=60.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
    except Exception:
        pass
    return [conn]

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
            role TEXT NOT NULL CHECK(role IN ('ADMIN', 'TENANT_ADMIN', 'USER')),
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
            
        # Migration: Recreate table if old CHECK constraint limits role to just 'ADMIN', 'USER'
        try:
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='app_permissions'")
            row = cursor.fetchone()
            if row and "'ADMIN', 'USER'" in row[0]:
                cursor.execute("ALTER TABLE app_permissions RENAME TO app_permissions_old")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('ADMIN', 'TENANT_ADMIN', 'USER')),
                    access_status TEXT DEFAULT 'GRANTED' CHECK(access_status IN ('GRANTED', 'REVOKED')),
                    source TEXT CHECK(source IN ('MANUAL', 'EXISTING_DB')),
                    granted_by TEXT NOT NULL,
                    allowed_modules TEXT DEFAULT 'ALL',
                    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    password_hash TEXT
                );
                """)
                cursor.execute("INSERT INTO app_permissions (id, email, full_name, role, access_status, source, granted_by, allowed_modules, granted_at, password_hash) SELECT id, email, full_name, role, access_status, source, granted_by, allowed_modules, granted_at, password_hash FROM app_permissions_old")
                cursor.execute("DROP TABLE app_permissions_old")
        except Exception as e:
            print(f"[WARN] Failed to migrate app_permissions table constraint: {e}")

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

        # 10. Tenant Management Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            tenant_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_code TEXT UNIQUE NOT NULL,
            tenant_name TEXT NOT NULL,
            email TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            enabled_modules TEXT DEFAULT 'INVOICE,SBC',
            output_root TEXT DEFAULT '',
            default_confidence_threshold REAL DEFAULT 0.85,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Migrations for tenants table
        try:
            cursor.execute("ALTER TABLE tenants ADD COLUMN output_root TEXT DEFAULT ''")
        except Exception:
            pass
            
        try:
            cursor.execute("ALTER TABLE tenants ADD COLUMN default_confidence_threshold REAL DEFAULT 0.85")
        except Exception:
            pass
            
        try:
            cursor.execute("ALTER TABLE tenants ADD COLUMN created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except Exception:
            pass

        # 11. Payroll Extractor History
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS payroll_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            original_file_name TEXT NOT NULL,
            status TEXT NOT NULL,
            summary TEXT,
            error_message TEXT,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 12. File Classification History
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS classification_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            status TEXT NOT NULL,
            category TEXT,
            error_message TEXT,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        conn.commit()
        _seed_initial_records(cursor, conn)
        conn.close()

def _seed_initial_records(cursor, conn):
    pass

# ── IN-MEMORY OTP STORE ──
# Key: (email, purpose), Value: (otp_code, timestamp)
_in_memory_otps = {}

def store_otp(email: str, purpose: str) -> str:
    otp_code = str(random.randint(100000, 999999))
    _in_memory_otps[(email.lower(), purpose)] = (otp_code, datetime.now())
    return otp_code

def verify_otp(email: str, otp_code: str, purpose: str) -> bool:
    key = (email.lower(), purpose)
    if key not in _in_memory_otps:
        return False
        
    stored_code, timestamp = _in_memory_otps[key]
    
    # Check if within 10 minutes (600 seconds)
    if (datetime.now() - timestamp).total_seconds() > 600:
        del _in_memory_otps[key]
        return False
        
    if stored_code == otp_code:
        del _in_memory_otps[key] # OTP is single-use
        return True
        
    return False

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

def log_payroll_run(task_id: str, original_file_name: str, status: str, summary: str = "", error_message: str = "", processed_by: str = "SYSTEM"):
    init_poc_tables()
    for conn in get_connections():
        conn.execute(
            "INSERT INTO payroll_history (task_id, original_file_name, status, summary, error_message) VALUES (?, ?, ?, ?, ?)",
            (task_id, original_file_name, status, summary, error_message)
        )
        conn.commit()
        conn.close()
    log_universal("PAYROLL_EXTRACTOR", "Payroll Register Extraction", original_file_name, status, summary or error_message, processed_by=processed_by)

def log_classification_run(task_id: str, file_name: str, status: str, category: str = "", error_message: str = "", processed_by: str = "SYSTEM"):
    init_poc_tables()
    for conn in get_connections():
        conn.execute(
            "INSERT INTO classification_history (task_id, file_name, status, category, error_message) VALUES (?, ?, ?, ?, ?)",
            (task_id, file_name, status, category, error_message)
        )
        conn.commit()
        conn.close()
    log_universal("CLASSIFICATION", "Document Semantic Classification", file_name, status, category or error_message, processed_by=processed_by)

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
        finally:
            conn.close()
    return None

def grant_user_access(email: str, full_name: str, role: str, source: str = "MANUAL", granted_by: str = "admin@local", allowed_modules: str = "ALL"):
    """Grant or update user access in the app_permissions DB."""
    init_poc_tables()
    clean_email = email.strip().lower()
    clean_name = full_name.strip() if full_name else clean_email.split('@')[0].capitalize()
    role_upper = role.upper() if role.upper() in ("ADMIN", "TENANT_ADMIN", "USER") else "USER"
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
        finally:
            conn.close()

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
        finally:
            conn.close()

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
        finally:
            conn.close()

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
        finally:
            conn.close()
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
        finally:
            conn.close()
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
        finally:
            conn.close()
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

# ── Tenant Management Database Helpers ────────────────────────────────────────

def list_tenants():
    """List all configured tenants."""
    init_poc_tables()
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tenants ORDER BY tenant_id ASC")
            rows = cursor.fetchall()
            tenants = []
            for r in rows:
                d = dict(r)
                d["active"] = bool(d.get("active", 1))
                modules_str = d.get("enabled_modules") or ""
                if isinstance(modules_str, str):
                    d["enabled_modules"] = [m.strip() for m in modules_str.split(",") if m.strip()]
                tenants.append(d)
            return tenants
        except Exception as e:
            print(f"[WARN] Error listing tenants: {e}")
        finally:
            conn.close()
    return []

def get_tenant(tenant_code: str):
    """Fetch a single tenant by tenant_code."""
    init_poc_tables()
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tenants WHERE UPPER(tenant_code) = UPPER(?)", (tenant_code.strip(),))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d["active"] = bool(d.get("active", 1))
                modules_str = d.get("enabled_modules") or ""
                if isinstance(modules_str, str):
                    d["enabled_modules"] = [m.strip() for m in modules_str.split(",") if m.strip()]
                return d
        except Exception:
            pass
        finally:
            conn.close()
    return None

def create_tenant(tenant_code: str, tenant_name: str, email: str, active: bool = True, enabled_modules = None, default_confidence_threshold: float = 0.85, output_root: str = ""):
    """Create a new tenant record."""
    init_poc_tables()
    if enabled_modules is None:
        enabled_modules = ["INVOICE", "SBC"]
    if isinstance(enabled_modules, list):
        modules_str = ",".join(enabled_modules)
    else:
        modules_str = str(enabled_modules)

    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tenants (tenant_code, tenant_name, email, active, enabled_modules, default_confidence_threshold, output_root)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (tenant_code.strip().upper(), tenant_name.strip(), email.strip().lower(), 1 if active else 0, modules_str, default_confidence_threshold, output_root))
            conn.commit()
            return True
        except Exception as e:
            print(f"[WARN] Error creating tenant {tenant_code}: {e}")
            raise e
        finally:
            conn.close()
    return False

def update_tenant(tenant_code: str, **kwargs):
    """Update tenant fields (active, enabled_modules, default_confidence_threshold, email, tenant_name)."""
    init_poc_tables()
    current = get_tenant(tenant_code)
    if not current:
        return False

    for conn in get_connections():
        try:
            cursor = conn.cursor()
            updates = []
            params = []
            
            if "tenant_name" in kwargs and kwargs["tenant_name"] is not None:
                updates.append("tenant_name = ?")
                params.append(kwargs["tenant_name"])
            if "email" in kwargs and kwargs["email"] is not None:
                updates.append("email = ?")
                params.append(kwargs["email"])
            if "active" in kwargs and kwargs["active"] is not None:
                updates.append("active = ?")
                params.append(1 if kwargs["active"] else 0)
            if "enabled_modules" in kwargs and kwargs["enabled_modules"] is not None:
                mods = kwargs["enabled_modules"]
                if isinstance(mods, list):
                    mods = ",".join(mods)
                updates.append("enabled_modules = ?")
                params.append(mods)
            if "default_confidence_threshold" in kwargs and kwargs["default_confidence_threshold"] is not None:
                updates.append("default_confidence_threshold = ?")
                params.append(kwargs["default_confidence_threshold"])
            if "output_root" in kwargs and kwargs["output_root"] is not None:
                updates.append("output_root = ?")
                params.append(kwargs["output_root"])

            if not updates:
                return True

            params.append(tenant_code.strip().upper())
            sql = f"UPDATE tenants SET {', '.join(updates)} WHERE UPPER(tenant_code) = UPPER(?)"
            cursor.execute(sql, params)
            conn.commit()
            return True
        except Exception as e:
            print(f"[WARN] Error updating tenant {tenant_code}: {e}")
        finally:
            conn.close()
    return False

def delete_tenant(tenant_code: str):
    """Delete a tenant by tenant_code."""
    init_poc_tables()
    for conn in get_connections():
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tenants WHERE UPPER(tenant_code) = UPPER(?)", (tenant_code.strip(),))
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            pass
        finally:
            conn.close()
    return False

# Initialize tables on import
init_poc_tables()





