import sqlite3
from pathlib import Path
from database import poc_db

WORKSPACE_DIR = Path(__file__).parent.resolve()
DB_PATH = WORKSPACE_DIR / "converter.db"

def verify_db():
    print("=" * 70)
    print("1. DATABASE TABLES VERIFICATION")
    print(f"Database Path: {DB_PATH}")
    print("=" * 70)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print("Found Tables in converter.db:", ", ".join(tables))

    print("\n" + "=" * 70)
    print("2. REGISTERED TENANTS IN DATABASE")
    print("=" * 70)
    tenants = poc_db.list_tenants()
    for t in tenants:
        code = str(t.get('tenant_code'))
        name = str(t.get('tenant_name'))
        active = str(t.get('active'))
        modules = str(t.get('enabled_modules'))
        print(f"  * Code: {code:<12} | Name: {name:<25} | Active: {active:<5} | Modules: {modules}")

    print("\n" + "=" * 70)
    print("3. RECENT AUDIT LOGS IN universal_history (LAST 8)")
    print("=" * 70)
    cursor.execute("PRAGMA table_info(universal_history)")
    cols = [col[1] for col in cursor.fetchall()]
    print("universal_history columns:", cols)

    cursor.execute("SELECT * FROM universal_history ORDER BY id DESC LIMIT 8")
    rows = cursor.fetchall()
    if rows:
        for r in rows:
            print(f"  * Record: {r}")
    else:
        print("  * No history entries found.")

    conn.close()
    print("\n" + "=" * 70)
    print("DATABASE VERIFICATION COMPLETE: ALL SYSTEMS CONNECTED")
    print("=" * 70)

if __name__ == "__main__":
    verify_db()
