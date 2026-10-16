import hashlib
import hmac
import os
import secrets
import time
from fastapi import HTTPException, Request
from sqlalchemy import select, delete
from . import db

COOKIE = 'paypilot_session'

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def issue_session(conn, uid):
    token = secrets.token_urlsafe(32)
    conn.execute(delete(db.sessions).where(db.sessions.c.expires_at < time.time()))
    conn.execute(db.sessions.insert().values(token_hash=digest(token), user_id=uid,
                                           expires_at=time.time() + 8 * 3600))
    return token

def set_cookie(response, token):
    response.set_cookie(COOKIE, token, httponly=True, samesite='lax',
                        secure=os.getenv('COOKIE_SECURE', 'false') == 'true', max_age=28800)

def current_user(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, 'Sign in or open a demo workspace.')
    with db.engine.connect() as conn:
        row = conn.execute(select(db.users.c.id, db.users.c.role).join(
            db.sessions, db.sessions.c.user_id == db.users.c.id).where(
            db.sessions.c.token_hash == digest(token), db.sessions.c.expires_at > time.time())).mappings().first()
    if not row:
        raise HTTPException(401, 'Session expired. Please sign in again.')
    return dict(row)

def valid_admin(password):
    configured = os.getenv('ADMIN_PASSWORD', '')
    return len(configured) >= 16 and hmac.compare_digest(digest(password), digest(configured))
