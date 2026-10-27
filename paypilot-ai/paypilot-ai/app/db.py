"""Namespaced, transactional storage. MySQL in hosted mode; SQLite for local demo."""
import os
import ssl
from sqlalchemy import (create_engine, MetaData, Table, Column, String, Text,
                        Integer, Numeric, Float, UniqueConstraint, inspect, text)
from sqlalchemy.engine import make_url

metadata = MetaData()
users = Table('pp_users', metadata,
    Column('id', String(64), primary_key=True), Column('role', String(16)),
    Column('created_at', Float(53)))
sessions = Table('pp_sessions', metadata,
    Column('token_hash', String(64), primary_key=True),
    Column('user_id', String(64), nullable=False), Column('expires_at', Float(53)))
payments = Table('pp_payments', metadata,
    Column('id', String(36), primary_key=True), Column('owner_id', String(64), index=True),
    Column('idempotency_key', String(64)), Column('request_hash', String(64)),
    Column('paypal_order_id', String(64), unique=True),
    Column('amount', Numeric(12, 2), nullable=False), Column('currency', String(3)),
    Column('description', String(240)), Column('recipient_email', String(254)),
    Column('status', String(24)), Column('mode', String(16)),
    Column('approve_link', Text), Column('receipt_text', Text),
    Column('due_at', Float(53)), Column('created_at', Float(53)), Column('updated_at', Float(53)),
    UniqueConstraint('owner_id', 'idempotency_key', name='pp_owner_request'))
events = Table('pp_events', metadata,
    Column('id', String(64), primary_key=True), Column('owner_id', String(64), index=True),
    Column('payment_id', String(36)), Column('kind', String(64)),
    Column('detail', Text), Column('created_at', Float(53)))
outbox = Table('pp_outbox', metadata,
    Column('id', String(64), primary_key=True), Column('owner_id', String(64), index=True),
    Column('payment_id', String(36)), Column('recipient', String(254)),
    Column('subject', String(300)), Column('body', Text), Column('kind', String(24)),
    Column('status', String(24)), Column('created_at', Float(53)))
settings = Table('pp_settings', metadata,
    Column('owner_id', String(64), primary_key=True),
    Column('receipts', Integer, default=1), Column('reminders', Integer, default=1))
items = Table('pp_invoice_items', metadata,
    Column('id', String(36), primary_key=True), Column('payment_id', String(36), nullable=False, index=True),
    Column('description', String(240), nullable=False), Column('quantity', Integer, nullable=False),
    Column('unit_amount', Numeric(12,2), nullable=False), Column('position', Integer, nullable=False))
automation_runs = Table('pp_automation_runs', metadata,
    Column('owner_id', String(64), primary_key=True), Column('started_at', Float(53)),
    Column('completed_at', Float(53)), Column('queued', Integer), Column('error', String(120)))
share_links = Table('pp_share_links', metadata,
    Column('token_hash', String(64), primary_key=True),
    Column('payment_id', String(36), nullable=False, index=True),
    Column('owner_id', String(64), nullable=False, index=True),
    Column('expires_at', Float(53), nullable=False))
payment_reports = Table('pp_payment_reports', metadata,
    Column('payment_id', String(36), primary_key=True), Column('owner_id', String(64), nullable=False,index=True),
    Column('reference', String(120), nullable=False), Column('status', String(24), nullable=False),
    Column('created_at', Float(53)), Column('reviewed_at', Float(53)))
workspace_preferences = Table('pp_workspace_preferences', metadata,
    Column('owner_id', String(64), primary_key=True), Column('business_name', String(100)),
    Column('payment_instructions', String(2000)))
invoice_metadata = Table('pp_invoice_metadata', metadata,
    Column('payment_id', String(36), primary_key=True),
    Column('owner_id', String(64), nullable=False, index=True),
    Column('customer_name', String(120), nullable=False),
    Column('notes', String(2000), nullable=False, default=''),
    Column('issued_date', String(10), nullable=False))
email_deliveries = Table('pp_email_deliveries', metadata,
    Column('outbox_id', String(64), primary_key=True),
    Column('owner_id', String(64), nullable=False, index=True),
    Column('status', String(24), nullable=False),
    Column('attempted_at', Float(53)), Column('accepted_at', Float(53)),
    Column('error', String(240)))
business_profiles = Table('pp_business_profiles', metadata,
    Column('owner_id', String(64), primary_key=True), Column('data_json', Text, nullable=False))
invoice_documents = Table('pp_invoice_documents', metadata,
    Column('payment_id', String(36), primary_key=True), Column('owner_id', String(64), nullable=False, index=True),
    Column('invoice_number', String(40), nullable=False), Column('data_json', Text, nullable=False),
    UniqueConstraint('owner_id', 'invoice_number', name='pp_owner_invoice_number'))
customers=Table('pp_customers',metadata,
    Column('id',String(36),primary_key=True),Column('owner_id',String(64),index=True),
    Column('name',String(160)),Column('email',String(254)),Column('address',Text),Column('tax_id',String(100)),
    UniqueConstraint('owner_id','email',name='pp_customer_email'))
installments=Table('pp_installments',metadata,
    Column('id',String(36),primary_key=True),Column('owner_id',String(64),index=True),
    Column('payment_id',String(36),index=True),Column('amount',Numeric(12,2)),Column('reference',String(120)),Column('created_at',Float(53)),
    UniqueConstraint('owner_id','reference',name='pp_installment_reference'))
business_drafts=Table('pp_business_drafts',metadata,
    Column('id',String(36),primary_key=True),Column('owner_id',String(64),index=True),Column('title',String(180)),
    Column('kind',String(24)),Column('status',String(24)),Column('data_json',Text),Column('next_date',String(10)),
    Column('payment_id',String(36)),Column('created_at',Float(53)))

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
    # Epoch timestamps require double precision; legacy FLOAT rounded expiry.
    if engine.dialect.name == 'mysql':
        inspector = inspect(engine)
        with engine.begin() as conn:
            for table in metadata.sorted_tables:
                expected = {c.name for c in table.columns if isinstance(c.type, Float)}
                legacy = [c for c in inspector.get_columns(table.name)
                          if c['name'] in expected and c['type'].__class__.__name__ == 'FLOAT']
                if legacy:
                    columns = ', '.join(f"MODIFY COLUMN `{column['name']}` DOUBLE {'NULL' if column['nullable'] else 'NOT NULL'}" for column in legacy)
                    conn.execute(text(f'ALTER TABLE `{table.name}` {columns}'))
