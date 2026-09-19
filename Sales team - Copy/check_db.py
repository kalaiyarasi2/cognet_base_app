import sqlite3
import json

db_path = r"c:\Users\Intern\cognet full app\Sales team - Copy\converter.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT timestamp, module, action, file_name, status, details FROM universal_logs ORDER BY timestamp DESC LIMIT 5")
rows = cursor.fetchall()

print("Recent Universal Logs:")
for row in rows:
    print(f"[{row['timestamp']}] {row['module']} - {row['action']} - {row['file_name']} -> {row['status']}")
    print(f"Details: {row['details']}")
    print("-" * 50)

conn.close()
