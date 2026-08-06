import sqlite3
from pathlib import Path

base_dir = Path(__file__).resolve().parent

db_paths = [
    base_dir / "converter.db",
    base_dir / "file-classification-" / "converter.db"
]

for db_path in db_paths:
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Kalaiyarasi G is the SUPER ADMIN (ADMIN role, NULL tenant_code)
            cursor.execute("UPDATE app_permissions SET role = 'ADMIN', tenant_code = NULL WHERE LOWER(email) = 'kalaiyarasig@cognethro.com'")
            
            conn.commit()
            conn.close()
            print(f"[OK] Cleaned Kalaiyarasi G as SUPER ADMIN (role=ADMIN, tenant_code=NULL) in {db_path.name}")
        except Exception as e:
            print(f"[WARN] Error updating DB {db_path}: {e}")
