import os
import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update, select, func
from app.main import app, paypal, limits
from app import db, ai_service

HEAD={'X-PayPilot-Client':'dashboard'}

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL',f'sqlite:///{tmp_path}/test.db')
    monkeypatch.setenv('ADMIN_PASSWORD','test-only-password-long-enough')
    monkeypatch.setenv('COOKIE_SECURE','false')
    monkeypatch.setenv('DEMO_ENABLED','true')
    monkeypatch.setenv('REQUIRE_MYSQL','false')
    monkeypatch.setenv('AUTOMATION_ENABLED','false')
    limits.clear()
    if os.getenv('TEST_MYSQL_URL'):
        def mysql_init():
            db.engine=create_engine(os.environ['TEST_MYSQL_URL'])
            db.metadata.drop_all(db.engine)
            db.metadata.create_all(db.engine)
        monkeypatch.setattr(db,'init_db',mysql_init)
    with TestClient(app) as c:
        c.headers.update(HEAD)
        yield c

def demo(c):
    assert c.post('/api/auth/demo').status_code==200

def create(c,**overrides):
    return c.post('/api/payments',headers={'Idempotency-Key':str(uuid.uuid4())},json={
        'amount':'125.50','currency':'USD','description':'Design work','recipient_email':'buyer@example.com',**overrides})

def test_auth_and_csrf(client):
    assert client.get('/api/payments').status_code==401
    assert client.post('/api/auth/demo',headers={'X-PayPilot-Client':''}).status_code==403
    assert client.post('/api/auth/login',json={'password':'bad'}).status_code==401
    assert client.post('/api/auth/login',json={'password':'test-only-password-long-enough'}).status_code==200
    assert client.get('/api/auth/me').json()['role']=='admin'
    assert 'httponly' in client.cookies.get('paypilot_session','').lower() or client.cookies.get('paypilot_session')
    client.post('/api/auth/logout')
    assert client.get('/api/payments').status_code==401

def test_demo_seed_and_isolation(client):
    demo(client)
    rows=client.get('/api/payments').json()
    assert len(rows)==6
    original=rows[0]['id']
    demo(client)
    assert client.post(f'/api/payments/{original}/simulate').status_code==404
    assert client.get(f'/api/payments/{original}/receipt').status_code==404
    assert original not in [p['id'] for p in client.get('/api/payments').json()]

def test_capture_receipt_and_dedup(client):
    demo(client)
    p=create(client).json()
    assert client.get(f"/api/payments/{p['id']}/receipt").status_code==409
    before=len(client.get('/api/outbox').json())
    for _ in range(3):
        assert client.post(f"/api/payments/{p['id']}/simulate").json()['status']=='CAPTURED'
    assert len(client.get('/api/outbox').json())==before+1
    r=client.get(f"/api/payments/{p['id']}/receipt").json()['receipt']
    assert 'DEMO' in r and '125.50 USD' in r

def test_idempotent_creation(client):
    demo(client)
    body={'amount':'25.00','description':'Test'}
    headers={'Idempotency-Key':'same-request-123'}
    first=client.post('/api/payments',headers=headers,json=body)
    second=client.post('/api/payments',headers=headers,json=body)
    assert first.status_code==second.status_code==200
    assert first.json()['id']==second.json()['id']
    assert client.post('/api/payments',headers=headers,json={**body,'amount':'26'}).status_code==409

@pytest.mark.parametrize('overrides',[{'amount':'-1'},{'amount':'NaN'},{'amount':'Infinity'},
    {'amount':'0'},{'amount':'1.999'},{'currency':'PKR'},{'recipient_email':'not-email'},{'description':''}])
def test_invalid_values(client,overrides):
    demo(client)
    assert create(client,**overrides).status_code==422

def test_currency_analytics(client):
    demo(client)
    create(client,amount='100',currency='EUR')
    a=client.get('/api/analytics').json()
    assert Decimal(str(a['currencies']['EUR']['pending']))==100
    assert Decimal(str(a['currencies']['USD']['captured']))==2620
    assert a['overdue_count']==2

def test_automation_daily_dedup_and_disabled(client):
    demo(client)
    assert client.post('/api/automations/run').json()['queued']==2
    assert client.post('/api/automations/run').json()['queued']==0
    assert client.put('/api/automations',json={'receipts':False,'reminders':False}).status_code==200
    p=create(client).json()
    before=len(client.get('/api/outbox').json())
    client.post(f"/api/payments/{p['id']}/simulate")
    assert len(client.get('/api/outbox').json())==before

def test_forged_webhook(client,monkeypatch):
    demo(client)
    monkeypatch.setattr(paypal,'verify_webhook',lambda *args:False)
    assert client.post('/webhooks/paypal',json={'event_type':'PAYMENT.CAPTURE.COMPLETED'}).status_code==401

def test_verified_webhook_match_and_replay(client,monkeypatch):
    demo(client)
    pid=create(client).json()['id']
    with db.engine.begin() as c:
        c.execute(update(db.payments).where(db.payments.c.id==pid).values(mode='sandbox',paypal_order_id='ORDER123'))
    monkeypatch.setattr(paypal,'verify_webhook',lambda *args:True)
    payload={'id':'EVENT123','event_type':'PAYMENT.CAPTURE.COMPLETED','resource':{
        'status':'COMPLETED','amount':{'value':'1.00','currency_code':'USD'},
        'supplementary_data':{'related_ids':{'order_id':'ORDER123'}}}}
    assert client.post('/webhooks/paypal',json=payload).status_code==422
    payload['resource']['amount']['value']='125.50'
    before=len(client.get('/api/outbox').json())
    assert client.post('/webhooks/paypal',json=payload).status_code==200
    assert client.post('/webhooks/paypal',json=payload).json()['duplicate']
    assert len(client.get('/api/outbox').json())==before+1

def test_demo_cannot_simulate_sandbox(client):
    demo(client)
    pid=create(client).json()['id']
    with db.engine.begin() as c:
        c.execute(update(db.payments).where(db.payments.c.id==pid).values(mode='sandbox'))
    assert client.post(f'/api/payments/{pid}/simulate').status_code==403

def test_export_formula_escape(client):
    demo(client)
    create(client,description='=HYPERLINK("https://example.com")')
    assert "'=HYPERLINK" in client.get('/api/export').text

@pytest.mark.parametrize('prompt,amount,currency',[
    ('Charge $1,250.50 USD for website design','1250.50','USD'),
    ('Invoice €49.99 for consulting','49.99','EUR'),
    ('Charge 250 GBP for branding','250','GBP')])
def test_parser(prompt,amount,currency):
    p=ai_service._regex_extract(prompt)
    assert Decimal(p['amount'])==Decimal(amount)
    assert p['currency']==currency

@pytest.mark.parametrize('prompt',['Charge -$25 for test','Charge $10 and $20 for test','Charge $50 PKR for test','Charge €50 USD for test'])
def test_ambiguous_parser(prompt):
    with pytest.raises(ValueError):
        ai_service._regex_extract(prompt)

def test_health_and_headers(client):
    assert client.get('/health').json()['status']=='ok'
    r=client.get('/')
    assert r.status_code==200 and 'Content-Security-Policy' in r.headers
    assert client.get('/static/app.js').status_code==200



def test_collections_currency_aging_and_isolation(client):
    import time
    demo(client)
    pid=create(client, amount='99.95', currency='EUR').json()['id']
    with db.engine.begin() as conn:
        conn.execute(update(db.payments).where(db.payments.c.id==pid).values(due_at=time.time()-40*86400))
    result=client.get('/api/collections').json()
    assert result['currencies']['EUR']['days_31_plus']=='99.95'
    assert result['currencies']['USD']['days_1_7']=='2720.00'
    assert result['priorities'][0]['id']==pid
    demo(client)
    assert 'EUR' not in client.get('/api/collections').json()['currencies']


def test_scheduler_tick_dedup_disabled_rules_and_expired_session(client):
    import time
    from app.main import automation_tick
    demo(client)
    automation_tick()
    assert len([r for r in client.get('/api/outbox').json() if r['kind']=='reminder'])==2
    automation_tick()
    assert len([r for r in client.get('/api/outbox').json() if r['kind']=='reminder'])==2
    assert client.get('/api/automations/status').json()['last_action_at'] is not None
    demo(client)
    client.put('/api/automations',json={'receipts':False,'reminders':False})
    automation_tick()
    assert not [r for r in client.get('/api/outbox').json() if r['kind']=='reminder']
    client.put('/api/automations',json={'receipts':True,'reminders':True})
    with db.engine.begin() as conn:
        conn.execute(update(db.sessions).values(expires_at=time.time()-1))
        before=conn.scalar(select(func.count()).select_from(db.outbox))
    automation_tick()
    with db.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.outbox))==before


def test_new_endpoints_require_auth(client):
    assert client.get('/api/collections').status_code==401
    assert client.get('/api/automations/status').status_code==401


def test_background_loop_starts_runs_and_stops(client, monkeypatch):
    import time
    from threading import Event, Thread
    from app.main import automation_loop
    demo(client)
    monkeypatch.setattr('app.main.scheduler_interval', lambda: 0.02)
    stop = Event()
    worker = Thread(target=automation_loop, args=(stop,))
    worker.start()
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if client.get('/api/automations/status').json()['last_action_at']:
                break
            time.sleep(0.02)
        assert client.get('/api/automations/status').json()['last_action_at']
    finally:
        stop.set()
        worker.join(2)
    assert not worker.is_alive()
