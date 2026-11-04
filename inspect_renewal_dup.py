import sqlite3

conn = sqlite3.connect('Sales team - Copy/monitor/universal_token_usage.db')
c = conn.cursor()
c.execute("SELECT id, timestamp, poc_name, file_name, step_name, model, prompt_tokens, cached_tokens, completion_tokens, session_id FROM token_calls WHERE file_name LIKE '%Benefits Renewal%' ORDER BY id ASC")
for r in c.fetchall():
    print("token_call:", r)

print("\n--- summaries ---")
c.execute("SELECT * FROM token_file_summary WHERE file_name LIKE '%Benefits Renewal%' ORDER BY id ASC")
for r in c.fetchall():
    print("summary:", r)

