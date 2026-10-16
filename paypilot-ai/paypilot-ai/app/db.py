"""SQLite persistence for PayPilot AI."""
import json
import os
import sqlite3
import time
import uuid

DB_PATH = os.getenv("PAYPILOT_DB", os.path.join(os.path.dirname(__file__), "paypilot.db"))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY,
        paypal_order_id TEXT,
        amount REAL NOT NULL,
        currency TEXT NOT NULL,
        description TEXT NOT NULL,
        recipient_email TEXT,
        status TEXT NOT NULL DEFAULT 'CREATED',
        payer_email TEXT,
        approve_link TEXT,
        receipt_text TEXT,
        raw_json TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS webhook_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        order_id TEXT,
        payload TEXT NOT NULL,
        received_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient TEXT,
        subject TEXT,
        body TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    """)
    conn.commit()
    conn.close()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def insert_payment(p: dict) -> str:
    pid = new_id()
    now = time.time()
    conn = get_conn()
    conn.execute(
        """INSERT INTO payments (id, paypal_order_id, amount, currency, description,
           recipient_email, status, approve_link, raw_json, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (pid, p.get("paypal_order_id"), p["amount"], p["currency"],
         p["description"], p.get("recipient_email"), p.get("status", "CREATED"),
         p.get("approve_link"), json.dumps(p.get("raw", {}), default=str), now, now))
    conn.commit()
    conn.close()
    return pid


def update_payment(pid: str, **fields):
    if not fields:
        return
    fields["updated_at"] = time.time()
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn = get_conn()
    conn.execute(f"UPDATE payments SET {cols} WHERE id = ?", (*fields.values(), pid))
    conn.commit()
    conn.close()


def get_payment(pid: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def find_payment_by_order(order_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM payments WHERE paypal_order_id = ?",
                       (order_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_payments(limit: int = 100) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM payments ORDER BY created_at DESC LIMIT ?",
        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_webhook_event(event_type: str, order_id: str | None, payload: dict):
    conn = get_conn()
    conn.execute(
        "INSERT INTO webhook_events (event_type, order_id, payload, received_at) VALUES (?,?,?,?)",
        (event_type, order_id, json.dumps(payload, default=str), time.time()))
    conn.commit()
    conn.close()


def list_webhook_events(limit: int = 50) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM webhook_events ORDER BY received_at DESC LIMIT ?",
        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_outbox(recipient: str | None, subject: str, body: str):
    conn = get_conn()
    conn.execute("INSERT INTO outbox (recipient, subject, body, created_at) VALUES (?,?,?,?)",
                 (recipient, subject, body, time.time()))
    conn.commit()
    conn.close()


def list_outbox(limit: int = 50) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM outbox ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
