"""Namespaced, transactional storage. MySQL in hosted mode; SQLite for local demo."""
import os
import ssl
from sqlalchemy import (create_engine, MetaData, Table, Column, String, Text,
                        Integer, Numeric, Float, UniqueConstraint)
from sqlalchemy.engine import make_url

metadata = MetaData()
users = Table('pp_users', metadata,
    Column('id', String(64), primary_key=True), Column('role', String(16)),
    Column('created_at', Float))
sessions = Table('pp_sessions', metadata,
    Column('token_hash', String(64), primary_key=True),
    Column('user_id', String(64), nullable=False), Column('expires_at', Float))
payments = Table('pp_payments', metadata,
    Column('id', String(36), primary_key=True), Column('owner_id', String(64), index=True),
    Column('idempotency_key', String(64)), Column('request_hash', String(64)),
    Column('paypal_order_id', String(64), unique=True),
    Column('amount', Numeric(12, 2), nullable=False), Column('currency', String(3)),
    Column('description', String(240)), Column('recipient_email', String(254)),
    Column('status', String(24)), Column('mode', String(16)),
    Column('approve_link', Text), Column('receipt_text', Text),
    Column('due_at', Float), Column('created_at', Float), Column('updated_at', Float),
    UniqueConstraint('owner_id', 'idempotency_key', name='pp_owner_request'))
events = Table('pp_events', metadata,
    Column('id', String(64), primary_key=True), Column('owner_id', String(64), index=True),
    Column('payment_id', String(36)), Column('kind', String(64)),
    Column('detail', Text), Column('created_at', Float))
outbox = Table('pp_outbox', metadata,
    Column('id', String(64), primary_key=True), Column('owner_id', String(64), index=True),
    Column('payment_id', String(36)), Column('recipient', String(254)),
    Column('subject', String(300)), Column('body', Text), Column('kind', String(24)),
    Column('status', String(24)), Column('created_at', Float))
settings = Table('pp_settings', metadata,
    Column('owner_id', String(64), primary_key=True),
    Column('receipts', Integer, default=1), Column('reminders', Integer, default=1))
items = Table('pp_invoice_items', metadata,
    Column('id', String(36), primary_key=True), Column('payment_id', String(36), nullable=False, index=True),
    Column('description', String(240), nullable=False), Column('quantity', Integer, nullable=False),
    Column('unit_amount', Numeric(12,2), nullable=False), Column('position', Integer, nullable=False))
automation_runs = Table('pp_automation_runs', metadata,
    Column('owner_id', String(64), primary_key=True), Column('started_at', Float),
    Column('completed_at', Float), Column('queued', Integer), Column('error', String(120)))
share_links = Table('pp_share_links', metadata,
    Column('token_hash', String(64), primary_key=True),
    Column('payment_id', String(36), nullable=False, index=True),
    Column('owner_id', String(64), nullable=False, index=True),
    Column('expires_at', Float, nullable=False))
engine = None

def init_db():
    global engine
    url = os.getenv('DATABASE_URL', 'sqlite:///./paypilot.db')
    if os.getenv('REQUIRE_MYSQL', 'false').lower() == 'true' and not url.startswith('mysql'):
        raise RuntimeError('A MySQL DATABASE_URL is required for this deployment')
    kwargs = {'pool_pre_ping': True}
    if url.startswith('mysql'):
        parsed = make_url(url).set(drivername='mysql+pymysql')
        ca = os.getenv('MYSQL_SSL_CA', '').replace('\\n', '\n')
        ctx = ssl.create_default_context(cadata=ca or None)
        kwargs['connect_args'] = {'ssl': ctx, 'connect_timeout': 10}
        kwargs.update(pool_recycle=280, pool_size=3, max_overflow=2)
        url = parsed
    elif url.startswith('sqlite'):
        kwargs['connect_args'] = {'check_same_thread': False, 'timeout': 20}
    else:
        raise RuntimeError('Only MySQL and local SQLite are supported')
    engine = create_engine(url, **kwargs)
    metadata.create_all(engine)
