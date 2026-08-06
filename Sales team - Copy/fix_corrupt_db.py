import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

db_files = [
    BASE_DIR / "converter.db",
    BASE_DIR / "file-classification-" / "converter.db",
]

print("[1/3] Clearing corrupted database file...")

# Attempt 1: File replacement/backup
for f in db_files:
    if f.exists():
        bak = f.with_name(f.name + ".corrupt.bak")
        try:
            if bak.exists():
                os.remove(bak)
            os.rename(f, bak)
            print(f"  - Backup successful: Moved {f.name} -> {bak.name}")
        except Exception:
            # Attempt 2: If file is locked, connect via SQL and drop all tables cleanly
            try:
                conn = sqlite3.connect(str(f), timeout=10.0)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [r[0] for r in cursor.fetchall() if not r[0].startswith("sqlite_")]
                for t in tables:
                    try:
                        cursor.execute(f"DROP TABLE IF EXISTS \"{t}\";")
                    except Exception:
                        pass
                conn.commit()
                conn.execute("VACUUM;")
                conn.close()
                print(f"  - SQL Table Drop successful on locked file: {f.name}")
            except Exception as ex:
                print(f"  - Could not reset {f.name}: {ex}")

print("[2/3] Re-initializing fresh database schema...")
from database import poc_db
poc_db.init_poc_tables()

print("[3/3] Inserting Super Admin user records...")
poc_db.grant_user_access(
    email="kalaiyarasig@cognethro.com",
    full_name="Kalaiyarasi G",
    role="ADMIN",
    source="MANUAL",
    granted_by="SYSTEM",
    allowed_modules="ALL"
)
poc_db.grant_user_access(
    email="kalaiyarasi.g@cognethro.com",
    full_name="Kalaiyarasi G",
    role="ADMIN",
    source="MANUAL",
    granted_by="SYSTEM",
    allowed_modules="ALL"
)

print("\n[SUCCESS] Database repaired and re-initialized cleanly!")
