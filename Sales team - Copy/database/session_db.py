import sqlite3
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SESSION_DB_PATH = BASE_DIR / "database" / "user_sessions.db"

def get_session_connection():
    SESSION_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SESSION_DB_PATH), check_same_thread=False, timeout=60.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
    except Exception:
        pass
    return conn

def init_session_db():
    conn = get_session_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_logins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            user_name TEXT,
            user_role TEXT,
            ip_address TEXT NOT NULL,
            user_agent TEXT,
            login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'IDLE', 'REVOKED', 'LOGGED_OUT'))
        );
        """)
        conn.commit()
    except Exception as e:
        print(f"[WARN] Error initializing user_sessions.db: {e}")
    finally:
        conn.close()

def record_session(email: str, name: str = "", role: str = "USER", ip_address: str = "127.0.0.1", user_agent: str = "Unknown"):
    init_session_db()
    clean_email = email.strip().lower() if email else "anonymous"
    conn = get_session_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM user_logins WHERE user_email = ? AND ip_address = ? AND status = 'ACTIVE'",
            (clean_email, ip_address)
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE user_logins SET last_active = datetime('now'), user_agent = ? WHERE id = ?",
                (user_agent, row[0])
            )
        else:
            cursor.execute(
                """INSERT INTO user_logins (user_email, user_name, user_role, ip_address, user_agent, login_time, last_active, status)
                   VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'), 'ACTIVE')""",
                (clean_email, name or clean_email, role, ip_address, user_agent)
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"[WARN] Error recording user session in user_sessions.db: {e}")
        return False
    finally:
        conn.close()

def get_active_sessions():
    init_session_db()
    conn = get_session_connection()
    records = []
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, user_email, user_name, user_role, ip_address, user_agent, login_time, last_active, status
               FROM user_logins
               ORDER BY last_active DESC LIMIT 200"""
        )
        rows = cursor.fetchall()
        records = [dict(row) for row in rows]
    except Exception as e:
        print(f"[WARN] Error reading user_sessions.db: {e}")
    finally:
        conn.close()
    return records

def revoke_session(session_id: int):
    init_session_db()
    conn = get_session_connection()
    try:
        conn.execute("UPDATE user_logins SET status = 'REVOKED' WHERE id = ?", (session_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"[WARN] Error revoking session {session_id} in user_sessions.db: {e}")
        return False
    finally:
        conn.close()

# Auto-initialize database on import
init_session_db()
