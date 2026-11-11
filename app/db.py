"""Tiny SQLite store for quotes/jobs."""
import json, sqlite3, time, uuid
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "bioquote.db"

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS jobs(
        id TEXT PRIMARY KEY, created REAL, request TEXT, job_type TEXT,
        quote_json TEXT, amount_usd REAL, status TEXT,
        paypal_order_id TEXT, approve_url TEXT, file_path TEXT, result_json TEXT)""")
    return c

def create_job(request, job_type, quote, amount, file_path=None):
    jid = uuid.uuid4().hex[:10]
    with _conn() as c:
        c.execute("INSERT INTO jobs(id,created,request,job_type,quote_json,amount_usd,status,file_path)"
                  " VALUES(?,?,?,?,?,?,?,?)",
                  (jid, time.time(), request, job_type, json.dumps(quote), amount, "quoted", file_path))
    return jid

def get_job(jid):
    with _conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    return dict(r) if r else None

def get_job_by_order(order_id):
    with _conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE paypal_order_id=?", (order_id,)).fetchone()
    return dict(r) if r else None

def update_job(jid, **fields):
    keys = ", ".join(f"{k}=?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE jobs SET {keys} WHERE id=?", (*fields.values(), jid))

def list_jobs():
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM jobs ORDER BY created DESC")]
