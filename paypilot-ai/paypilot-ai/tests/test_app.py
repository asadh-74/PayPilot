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
    {'amount':'0'},{'amount':'1.999'},{'recipient_email':'not-email'},{'description':''}])
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


def test_invoice_items_and_exact_money(client):
    demo(client)
    p=create(client,amount='30.30',items=[{'description':'Consulting','quantity':3,'unit_amount':'10.10'}]).json()
    assert p['amount']=='30.30'
    details=client.get(f"/api/payments/{p['id']}/details").json()
    assert details['items'][0]['unit_amount']=='10.10'
    assert create(client,amount='30.31',items=[{'description':'Work','quantity':3,'unit_amount':'10.10'}]).status_code==422


def test_share_link_private_revocable_and_escaped(client):
    demo(client)
    p=create(client,description='<script>alert(1)</script>').json()
    path=client.post(f"/api/payments/{p['id']}/share").json()['path']
    page=client.get(path)
    assert page.status_code==200 and '&lt;script&gt;' in page.text
    assert '<script>alert(1)' not in page.text
    assert 'buyer@example.com' not in page.text
    newer=client.post(f"/api/payments/{p['id']}/share").json()['path']
    assert client.get(path).status_code==404
    assert client.get(newer).status_code==200
    client.delete(f"/api/payments/{p['id']}/share")
    assert client.get(newer).status_code==404


def test_details_share_and_reminder_owner_isolation(client):
    demo(client)
    pid=create(client).json()['id']
    assert client.post(f'/api/payments/{pid}/reminder-preview').status_code==200
    client.post(f'/api/payments/{pid}/simulate')
    assert client.post(f'/api/payments/{pid}/reminder-preview').status_code==409
    demo(client)
    for suffix,method in [('details','get'),('share','post'),('reminder-preview','post'),('retry-checkout','post')]:
        assert getattr(client,method)(f'/api/payments/{pid}/{suffix}').status_code==404


def test_automation_zero_output_still_records_run(client):
    demo(client)
    client.post('/api/automations/run')
    client.post('/api/automations/run')
    status=client.get('/api/automations/status').json()['latest_run']
    assert status['queued']==0 and status['completed_at']>=status['started_at']


def test_checkout_recovery_preserves_invoice(client,monkeypatch):
    monkeypatch.setenv('PAYMENT_MODE','sandbox')
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    monkeypatch.setenv('APP_BASE_URL','https://example.com')
    monkeypatch.setattr(paypal,'create_order',lambda *args: (_ for _ in ()).throw(RuntimeError('offline')))
    assert create(client).status_code==502
    p=client.get('/api/payments').json()[0]
    monkeypatch.setattr(paypal,'create_order',lambda *args:{'id':'RECOVERED','links':[{'rel':'approve','href':'https://www.sandbox.paypal.com/checkoutnow?token=RECOVERED'}]})
    recovered=client.post(f"/api/payments/{p['id']}/retry-checkout")
    assert recovered.status_code==200 and recovered.json()['id']==p['id']
    assert len(client.get('/api/payments').json())==1
    assert client.post(f"/api/payments/{p['id']}/retry-checkout").status_code==409


def test_expired_link_and_demo_cleanup(client):
    import time
    from app.main import cleanup_demo_workspaces
    demo(client)
    pid=create(client).json()['id']
    path=client.post(f'/api/payments/{pid}/share').json()['path']
    with db.engine.begin() as conn:
        conn.execute(update(db.share_links).values(expires_at=time.time()-1))
    assert client.get(path).status_code==404
    with db.engine.begin() as conn:
        conn.execute(update(db.users).where(db.users.c.role=='demo').values(created_at=time.time()-9*3600))
        conn.execute(update(db.sessions).values(expires_at=time.time()-1))
    cleanup_demo_workspaces()
    with db.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.payments))==0


def admin(c):
    assert c.post('/api/auth/login',json={'password':'test-only-password-long-enough'}).status_code==200


def test_manual_business_flow_without_paypal(client,monkeypatch):
    monkeypatch.setenv('PAYMENT_MODE','manual')
    admin(client)
    assert client.put('/api/workspace',json={'business_name':'Asad Studio','payment_instructions':'Contact our accounts team for transfer details.'}).status_code==200
    p=create(client,amount='2500.00',currency='PKR').json()
    assert p['mode']=='manual' and p['status']=='CREATED'
    assert client.post(f"/api/payments/{p['id']}/simulate").status_code==403
    path=client.post(f"/api/payments/{p['id']}/share").json()['path']
    page=client.get(path)
    assert 'Asad Studio' in page.text and 'bank transfer' in page.text
    assert 'SANDBOX / DEMO' not in page.text
    token=path.split('/')[-1]
    endpoint=f'/api/customer/{token}/report'
    assert client.post(endpoint,json={'reference':'BANK-ABC123'}).status_code==200
    assert client.post(endpoint,json={'reference':'BANK-ABC123'}).status_code==200
    assert client.post(endpoint,json={'reference':'BANK-OTHER'}).status_code==409
    assert client.get('/api/payments').json()[0]['status']=='CREATED'
    assert len(client.get('/api/payment-reports').json())==1
    assert client.post(f"/api/payments/{p['id']}/confirm-manual",json={'reference':'BANK-ABC123','verified':False}).status_code==422
    before=len(client.get('/api/outbox').json())
    for _ in range(2):
        assert client.post(f"/api/payments/{p['id']}/confirm-manual",json={'reference':'BANK-ABC123','verified':True}).json()['status']=='CAPTURED'
    assert len(client.get('/api/outbox').json())==before+1
    assert client.get('/api/payment-reports').json()==[]
    receipt=client.get(f"/api/payments/{p['id']}/receipt").json()['receipt']
    assert 'manual verification' in receipt and 'DEMO' not in receipt


def test_manual_permissions_and_rejected_reference(client,monkeypatch):
    monkeypatch.setenv('PAYMENT_MODE','manual')
    admin(client)
    p=create(client).json()
    path=client.post(f"/api/payments/{p['id']}/share").json()['path']
    token=path.split('/')[-1]
    assert client.post(f'/api/customer/{token}/report',json={'reference':'      '}).status_code==422
    client.post(f'/api/customer/{token}/report',json={'reference':'REFERENCE1'})
    assert client.post(f"/api/payments/{p['id']}/reject-reference").status_code==200
    assert client.post(f'/api/customer/{token}/report',json={'reference':'REFERENCE2'}).status_code==200
    demo(client)
    assert client.get('/api/workspace').status_code==403
    assert client.get('/api/payment-reports').status_code==403
    assert client.post(f"/api/payments/{p['id']}/confirm-manual",json={'reference':'REFERENCE2','verified':True}).status_code==403


def test_private_workspace_demo_disabled(client,monkeypatch):
    monkeypatch.setenv('DEMO_ENABLED','false')
    assert client.post('/api/auth/demo').status_code==403
    admin(client)
    assert client.get('/api/payments').json()==[]


def test_manual_review_pauses_reminders(client,monkeypatch):
    import time
    monkeypatch.setenv('PAYMENT_MODE','manual')
    admin(client)
    p=create(client,due_days=0).json()
    with db.engine.begin() as conn:
        conn.execute(update(db.payments).where(db.payments.c.id==p['id']).values(due_at=time.time()-86400))
    token=client.post(f"/api/payments/{p['id']}/share").json()['path'].split('/')[-1]
    client.post(f'/api/customer/{token}/report',json={'reference':'BANK-REFERENCE'})
    assert client.post('/api/automations/run').json()['queued']==0
    client.post(f"/api/payments/{p['id']}/reject-reference")
    assert client.post('/api/automations/run').json()['queued']==1


def test_manual_reference_cannot_pay_two_invoices(client,monkeypatch):
    monkeypatch.setenv('PAYMENT_MODE','manual')
    admin(client)
    one=create(client).json()['id']
    two=create(client).json()['id']
    body={'reference':'BANK-UNIQUE-123','verified':True}
    assert client.post(f'/api/payments/{one}/confirm-manual',json=body).status_code==200
    assert client.post(f'/api/payments/{two}/confirm-manual',json=body).status_code==409


def test_light_workspace_full_manual_workflow(client, monkeypatch):
    monkeypatch.setenv('PAYMENT_MODE','manual')
    assert client.get('/api/workspace/snapshot').status_code == 401
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    assert client.get('/api/workspace/snapshot').json()['invoices'] == []
    prefs={'business_name':'Fictional Studio','payment_instructions':'TEST ONLY: receiving instructions'}
    assert client.put('/api/workspace',json=prefs).status_code == 200
    today=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).date().isoformat()
    p=create(client, amount='125.50', currency='PKR', customer_name='Fictional Customer', notes='<script>unsafe</script>', issue_date=today,due_date=today,items=[{'description':'Design','quantity':2,'unit_amount':'62.75'}]).json()
    assert 'id' in p
    snapshot=client.get('/api/workspace/snapshot').json()
    assert snapshot['metadata'][0]['customer_name']=='Fictional Customer'
    assert snapshot['items'][0]['unit_amount']=='62.75'
    assert snapshot['business']==prefs
    share=client.post(f"/api/payments/{p['id']}/share").json()['path']
    document=client.get(share)
    assert 'Fictional Customer' in document.text and '&lt;script&gt;' in document.text
    assert '<script>unsafe</script>' not in document.text
    token=share.rsplit('/',1)[-1]
    assert client.post(f'/api/customer/{token}/report',json={'reference':'TEST-REF-12345'}).status_code==200
    assert client.get('/api/workspace/snapshot').json()['invoices'][0]['status']!='CAPTURED'
    assert client.post(f"/api/payments/{p['id']}/confirm-manual",json={'reference':'TEST-REF-12345','verified':False}).status_code==422
    assert client.post(f"/api/payments/{p['id']}/reject-reference").status_code==200
    assert client.post(f'/api/customer/{token}/report',json={'reference':'TEST-REF-54321'}).status_code==200
    for _ in range(2):
        assert client.post(f"/api/payments/{p['id']}/confirm-manual",json={'reference':'TEST-REF-54321','verified':True}).status_code==200
    snapshot=client.get('/api/workspace/snapshot').json()
    assert snapshot['invoices'][0]['status']=='CAPTURED'
    assert len(snapshot['drafts'])==1
    assert snapshot['drafts'][0]['status']=='DRAFT'
    assert snapshot['reports'][0]['status']=='APPROVED'
    assert 'PAYMENT RECEIPT' in client.get(share).text
    client.post('/api/auth/logout')
    assert client.get('/api/workspace/snapshot').status_code==401
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    assert len(client.get('/api/workspace/snapshot').json()['invoices'])==1


def test_snapshot_scope_and_date_validation(client,monkeypatch):
    monkeypatch.setenv('PAYMENT_MODE','manual')
    demo(client)
    assert client.get('/api/workspace/snapshot').status_code==403
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    assert client.get('/api/workspace/snapshot').json()['invoices']==[]
    assert create(client,issue_date='2026-01-02',due_date='2026-01-01').status_code==422
    assert create(client,issue_date='2099-01-01',due_date='2099-01-02').status_code==422


def test_light_ui_served_without_inline_script(client):
    page=client.get('/')
    assert '/static/workspace.js' in page.text
    assert '/static/workspace.css' in page.text
    assert 'onclick=' not in page.text
    assert 'demo-login' not in page.text
    assert 'script-src \'self\';' in page.headers['content-security-policy']
    assert client.get('/static/workspace.js').status_code==200


def test_customer_reference_cannot_be_reused_across_invoices(client, monkeypatch):
    monkeypatch.setenv('PAYMENT_MODE','manual')
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    a,b=create(client).json(),create(client).json()
    links=[client.post(f"/api/payments/{p['id']}/share").json()['path'].rsplit('/',1)[-1] for p in (a,b)]
    report=lambda token: client.post(f'/api/customer/{token}/report',json={'reference':'DUPLICATE-TEST-001'})
    assert report(links[0]).status_code==200
    assert report(links[0]).status_code==200
    assert report(links[1]).status_code==409
    assert all(p['status']!='CAPTURED' for p in client.get('/api/payments').json())



def test_login_explains_invalid_server_password_without_exposing_it(client,monkeypatch):
    monkeypatch.setenv('ADMIN_PASSWORD','short-test')
    assert client.get('/api/config').json()['admin_configured'] is False
    response=client.post('/api/auth/login',json={'password':'short-test'})
    assert response.status_code==503
    assert 'at least 16' in response.json()['detail']
    assert 'short-test' not in response.text
    monkeypatch.setenv('ADMIN_PASSWORD','test-only-password-long-enough')
    assert client.get('/api/config').json()['admin_configured'] is True
    response=client.post('/api/auth/login',json={'password':'wrong-test'})
    assert response.status_code==401
    assert 'does not match' in response.json()['detail']


def test_sentence_invoice_parse_is_preview_only(client):
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    r=client.post('/api/invoice-drafts/parse',json={'prompt':'Invoice Cedar Studio at billing@customer.example for 2 logo designs at PKR 5000 each; 3 banners at PKR 1000 each, due in 14 days.'})
    assert r.status_code==200
    d=r.json()
    assert d['customer_name']=='Cedar Studio' and d['recipient_email']=='billing@customer.example'
    assert d['amount']=='13000' and len(d['items'])==2
    assert d['items'][0]['quantity']==2 and d['items'][1]['unit_amount']=='1000'
    assert client.get('/api/payments').json()==[]
    assert client.get('/api/outbox').json()==[]
    for prompt in ['Invoice Cedar for logo PKR 12,34', 'Invoice Cedar for logo PKR 50 and USD 20', 'Invoice Cedar for logo PKR 10.999', 'Invoice Cedar for logo PKR -50', 'Invoice Cedar for -2 logos at PKR 50 each', 'Invoice Cedar for logo PKR 50 with tax 10%', 'Invoice Cedar for logo PKR 50 due Friday']:
        assert client.post('/api/invoice-drafts/parse',json={'prompt':prompt}).status_code==422
    demo(client)
    assert client.post('/api/invoice-drafts/parse',json={'prompt':'Invoice Cedar for logo PKR 50'}).status_code==403


def test_email_preparation_review_delivery_and_dedup(client,monkeypatch):
    from app import mail_service
    monkeypatch.setenv('PAYMENT_MODE','manual')
    monkeypatch.setenv('APP_BASE_URL','https://invoice.example')
    monkeypatch.setattr(mail_service,'ready',lambda:True)
    calls=[]
    monkeypatch.setattr(mail_service,'send',lambda *args:calls.append(args))
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    p=create(client,recipient_email='recipient@test.invalid').json()
    path=f"/api/payments/{p['id']}/email-draft"
    d=client.post(path).json()
    assert d['status']=='DRAFT' and '/invoice/' in d['body'] and not calls
    send=f"/api/outbox/{d['id']}/send"
    assert client.post(send,json={'reviewed':False}).status_code==422
    assert client.post(send,json={'reviewed':True}).status_code==422
    # Controlled test recipient only; transport is mocked, never external.
    with db.engine.begin() as conn:
        conn.execute(update(db.outbox).where(db.outbox.c.id==d['id']).values(recipient='recipient@unit-test.test'))
    assert client.post(send,json={'reviewed':True}).json()['status']=='ACCEPTED'
    assert len(calls)==1
    assert client.post(send,json={'reviewed':True}).json()['status']=='ACCEPTED'
    assert len(calls)==1
    s=client.get('/api/workspace/snapshot').json()
    assert s['deliveries'][0]['status']=='ACCEPTED'
    assert next(m for m in s['drafts'] if m['id']==d['id'])['status']=='SENT'
    assert s['invoices'][0]['status']!='CAPTURED'
    client.post('/api/auth/logout')
    assert client.post(send,json={'reviewed':True}).status_code==401


def test_email_not_configured_and_uncertain_delivery(client,monkeypatch):
    from app import mail_service
    monkeypatch.setenv('PAYMENT_MODE','manual')
    monkeypatch.setenv('APP_BASE_URL','https://invoice.example')
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    p=create(client,recipient_email='recipient@unit-test.test').json()
    d=client.post(f"/api/payments/{p['id']}/email-draft").json()
    path=f"/api/outbox/{d['id']}/send"
    monkeypatch.setattr(mail_service,'ready',lambda:False)
    assert client.post(path,json={'reviewed':True}).status_code==503
    assert client.get('/api/workspace/snapshot').json()['deliveries']==[]
    monkeypatch.setattr(mail_service,'ready',lambda:True)
    def uncertain(*args): raise TimeoutError('private-provider-token must not leak')
    monkeypatch.setattr(mail_service,'send',uncertain)
    r=client.post(path,json={'reviewed':True})
    assert r.status_code==502 and 'private-provider-token' not in r.text
    assert client.post(path,json={'reviewed':True}).status_code==409
    s=client.get('/api/workspace/snapshot').json()
    assert s['deliveries'][0]['status']=='UNKNOWN' and s['drafts'][0]['status']=='DRAFT'


def test_expired_email_link_cannot_be_sent(client,monkeypatch):
    import time
    from app import mail_service
    monkeypatch.setenv('PAYMENT_MODE','manual')
    monkeypatch.setenv('APP_BASE_URL','https://invoice.example')
    monkeypatch.setattr(mail_service,'ready',lambda:True)
    monkeypatch.setattr(mail_service,'send',lambda *args:pytest.fail('Expired link must not be emailed'))
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    p=create(client,recipient_email='recipient@unit-test.test').json()
    d=client.post(f"/api/payments/{p['id']}/email-draft").json()
    with db.engine.begin() as conn: conn.execute(update(db.share_links).values(expires_at=time.time()-300))
    assert client.post(f"/api/outbox/{d['id']}/send",json={'reviewed':True}).status_code==409
    refreshed=client.post(f"/api/payments/{p['id']}/email-draft").json()
    assert refreshed['body']!=d['body']


def test_https_mail_transport_and_rejection(monkeypatch):
    from app import mail_service
    monkeypatch.setenv('EMAIL_PROVIDER','resend')
    monkeypatch.setenv('EMAIL_FROM','PayPilot <billing@sender.test>')
    monkeypatch.setenv('RESEND_API_KEY','private-test-key')
    calls=[]
    class Response:
        status_code=200
        def raise_for_status(self): pass
        def json(self): return {'id':'test-provider-id'}
    response=Response()
    def post(*args,**kwargs): calls.append((args,kwargs)); return response
    monkeypatch.setattr(mail_service.requests,'post',post)
    assert mail_service.ready()
    for _ in range(2): mail_service.send('customer@unit.test','Invoice','Review invoice','draft-1')
    assert calls[0][0][0]=='https://api.resend.com/emails'
    assert calls[0][1]['json']['text']=='Review invoice'
    assert calls[0][1]['headers']['Idempotency-Key']==calls[1][1]['headers']['Idempotency-Key']
    response.status_code=422
    with pytest.raises(mail_service.DeliveryRejected): mail_service.send('customer@unit.test','Invoice','Body','draft-2')
    before=len(calls)
    with pytest.raises(ValueError): mail_service.send('customer@unit.test','Injected\nHeader','Body')
    assert len(calls)==before


def test_email_retry_requires_provider_check_and_explicit_send(client,monkeypatch):
    from app import mail_service
    monkeypatch.setenv('PAYMENT_MODE','manual')
    monkeypatch.setenv('APP_BASE_URL','https://invoice.example')
    monkeypatch.setattr(mail_service,'ready',lambda:True)
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    p=create(client,recipient_email='recipient@unit-test.test').json()
    d=client.post(f"/api/payments/{p['id']}/email-draft").json()
    root=f"/api/outbox/{d['id']}"
    def uncertain(*args): raise TimeoutError()
    monkeypatch.setattr(mail_service,'send',uncertain)
    assert client.post(root+'/send',json={'reviewed':True}).status_code==502
    assert client.post(root+'/retry-check',json={'confirmed_not_sent':False}).status_code==422
    assert client.post(root+'/retry-check',json={'confirmed_not_sent':True}).status_code==200
    def rejected(*args): raise mail_service.DeliveryRejected()
    monkeypatch.setattr(mail_service,'send',rejected)
    assert client.post(root+'/send',json={'reviewed':True}).status_code==502
    assert client.get('/api/workspace/snapshot').json()['deliveries'][0]['status']=='FAILED'
    calls=[]
    monkeypatch.setattr(mail_service,'send',lambda *args:calls.append(args))
    assert client.post(root+'/send',json={'reviewed':True}).status_code==200
    assert len(calls)==1


def test_old_reminder_cannot_be_sent_after_payment(client,monkeypatch):
    from app import mail_service
    monkeypatch.setenv('PAYMENT_MODE','manual')
    monkeypatch.setattr(mail_service,'ready',lambda:True)
    monkeypatch.setattr(mail_service,'send',lambda *args:pytest.fail('Stale reminder must not send'))
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    p=create(client,recipient_email='recipient@unit-test.test').json()
    with db.engine.begin() as conn:
        conn.execute(update(db.payments).where(db.payments.c.id==p['id']).values(status='CAPTURED'))
        conn.execute(db.outbox.insert().values(id='stale-reminder',owner_id=conn.execute(select(db.payments.c.owner_id).where(db.payments.c.id==p['id'])).scalar_one(),payment_id=p['id'],recipient='recipient@unit-test.test',kind='reminder',subject='Reminder',body='Old reminder',status='DRAFT',created_at=0))
    assert client.post('/api/outbox/stale-reminder/send',json={'reviewed':True}).status_code==409

def test_billing_snapshot_pdf_and_revocation(client,monkeypatch,tmp_path):
    from pypdf import PdfReader
    from io import BytesIO
    monkeypatch.setenv('PAYMENT_MODE','manual')
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    assert client.put('/api/business-profile',json={'address':'Paris, France','terms':'Pay within 14 days'}).status_code==200
    p=create(client,customer_name='René Studio',customer_address='12 Example Street',purchase_order='PO-42').json()
    client.put('/api/business-profile',json={'address':'Changed address'})
    pdf=client.get(f"/api/payments/{p['id']}/pdf")
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
    text=''.join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
    assert 'Paris, France' in text and 'Changed address' not in text
    assert '125.50 USD' in text and 'PO-42' in text and 'René' in text
    token=client.post(f"/api/payments/{p['id']}/share").json()['path'].split('/')[-1]
    assert client.get(f'/api/customer/{token}/pdf').status_code==200
    client.delete(f"/api/payments/{p['id']}/share")
    assert client.get(f'/api/customer/{token}/pdf').status_code==404
    demo(client)
    assert client.get(f"/api/payments/{p['id']}/pdf").status_code==404

def test_receivables_currency_aging_and_csv(client,monkeypatch):
    import time
    monkeypatch.setenv('PAYMENT_MODE','manual')
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    p=create(client,amount='0.30',currency='AED').json()
    create(client,amount='2.50',currency='SAR')
    with db.engine.begin() as conn:
        conn.execute(update(db.payments).where(db.payments.c.id==p['id']).values(due_at=time.time()-40*86400))
    report=client.get('/api/reports/receivables').json()
    assert report['currencies']['AED']['overdue_31_60']=='0.30'
    assert report['currencies']['SAR']['outstanding']=='2.50'
    assert 'INV-' in client.get('/api/reports/receivables.csv').text
    demo(client)
    assert client.get('/api/reports/receivables').json()['invoices']==[]

def test_invoice_numbers_idempotent(client,monkeypatch):
    monkeypatch.setenv('PAYMENT_MODE','manual')
    client.post('/api/auth/login',json={'password':'test-only-password-long-enough'})
    body={'amount':'10','description':'Test'}
    for _ in range(2):
        assert client.post('/api/payments',headers={'Idempotency-Key':'billing-test-key'},json=body).status_code==200
    create(client)
    docs=client.get('/api/workspace/snapshot').json()['invoice_documents']
    assert len(docs)==2
    assert sorted(d['invoice_number'][-6:] for d in docs)==['000001','000002']

def admin_login(c):
    assert c.post('/api/auth/login',json={'password':'test-only-password-long-enough'}).status_code==200

def test_customer_directory_validation_and_isolation(client):
    admin_login(client)
    body={'name':'Cedar Studio','email':'BILLING@example.com','address':'Fictional address'}
    r=client.post('/api/customers',json=body);assert r.status_code==200
    id=r.json()['id'];assert r.json()['email']=='billing@example.com'
    assert client.post('/api/customers',json=body).status_code==409
    assert client.put('/api/customers/'+id,json={**body,'name':'Updated'}).status_code==200
    assert client.get('/api/customers').json()[0]['name']=='Updated'
    assert client.post('/api/customers',json={**body,'email':'bad'}).status_code==422
    demo(client);assert client.get('/api/customers').status_code==403

def test_installments_exact_balance_idempotency_and_overpay(client,monkeypatch):
    monkeypatch.setenv('PAYMENT_MODE','manual');admin_login(client)
    p=create(client,amount='100').json();url=f"/api/payments/{p['id']}/installments"
    body={'amount':'30.10','reference':'BANK-ONE','verified':True}
    assert client.post(url,json={**body,'verified':False}).status_code==422
    first=client.post(url,json=body);assert first.status_code==200
    assert first.json()['balance_due']=='69.90'
    assert client.post(url,json=body).json()['balance_due']=='69.90'
    assert client.post(url,json={**body,'amount':'31'}).status_code==409
    assert client.post(url,json={**body,'reference':'BANK-TWO','amount':'70'}).status_code==409
    assert client.post(f"/api/payments/{p['id']}/confirm-manual",json={'reference':'BANK-TWO','verified':True}).status_code==409
    report=client.get('/api/reports/receivables').json()['currencies']['USD']
    assert report['paid']=='30.10' and report['outstanding']=='69.90'
    a=client.get('/api/analytics').json()['currencies']['USD']
    assert Decimal(str(a['captured']))==Decimal('30.10') and Decimal(str(a['pending']))==Decimal('69.90')
    assert client.post(url,json={**body,'reference':'BANK-TWO','amount':'69.90'}).json()['status']=='CAPTURED'
    assert len(client.get(url).json()['entries'])==2
    assert client.get('/api/reports/receivables').json()['currencies']['USD']['paid']=='100.00'
    other=create(client).json()
    assert client.post(f"/api/payments/{other['id']}/installments",json=body).status_code==409

def test_quote_conversion_retries_and_cancel(client,monkeypatch):
    monkeypatch.setenv('PAYMENT_MODE','manual');admin_login(client)
    body={'title':'Website proposal','invoice':{'amount':'200','description':'Website','customer_name':'Example'}}
    r=client.post('/api/business-drafts',json=body);assert r.status_code==200
    id=r.json()['id'];url='/api/business-drafts/'+id+'/convert'
    first=client.post(url);assert first.status_code==200,first.text
    assert client.post(url).json()['id']==first.json()['id']
    assert len(client.get('/api/payments').json())==1
    assert client.get('/api/outbox').json()==[]
    id2=client.post('/api/business-drafts',json=body).json()['id']
    assert client.post('/api/business-drafts/'+id2+'/cancel').status_code==200
    assert client.post('/api/business-drafts/'+id2+'/convert').status_code==409

def test_recurring_drafts_only_and_no_duplicate(client):
    from datetime import date
    admin_login(client)
    r=client.post('/api/business-drafts',json={'title':'Monthly support','kind':'recurring','next_date':date.today().isoformat(),'invoice':{'amount':'150','description':'Support'}})
    assert r.status_code==200
    assert client.post('/api/recurring/prepare').json()['prepared']==1
    assert client.post('/api/recurring/prepare').json()['prepared']==0
    assert client.get('/api/payments').json()==[] and client.get('/api/outbox').json()==[]
    rows=client.get('/api/business-drafts').json()
    draft=next(x for x in rows if x['kind']=='invoice_draft')
    assert client.post('/api/business-drafts/'+draft['id']+'/convert').status_code==200

def test_partial_payment_pdf_and_stale_reminder(client,monkeypatch):
    import time
    from io import BytesIO
    from pypdf import PdfReader
    monkeypatch.setenv('PAYMENT_MODE','manual');admin_login(client)
    p=create(client,amount='100').json()
    with db.engine.begin() as conn:conn.execute(update(db.payments).where(db.payments.c.id==p['id']).values(due_at=time.time()-86400))
    client.post('/api/automations/run')
    original=client.get('/api/outbox').json()[0]
    client.post(f"/api/payments/{p['id']}/installments",json={'amount':'25','reference':'BANK-PARTIAL','verified':True})
    assert next(x for x in client.get('/api/outbox').json() if x['id']==original['id'])['status']=='STALE'
    assert client.post('/api/automations/run').json()['queued']==1
    current=next(x for x in client.get('/api/outbox').json() if x['status']=='DRAFT')
    assert '75.00 USD' in current['body'] and len(current['id'])<=64
    pdf=client.get(f"/api/payments/{p['id']}/pdf")
    text=''.join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
    assert 'Balance due: 75.00 USD' in text
    assert Decimal(client.get('/api/collections').json()['currencies']['USD']['days_1_7'])==75

def test_recurring_scheduler_and_invalid_quote(client):
    from datetime import date
    from app.main import automation_tick
    admin_login(client)
    assert client.post('/api/business-drafts',json={'title':'Bad','invoice':{'amount':'NaN','description':'Bad'}}).status_code==422
    assert client.post('/api/business-drafts',json={'title':'Monthly','kind':'recurring','next_date':date.today().isoformat(),'invoice':{'amount':'20','description':'Support'}}).status_code==200
    automation_tick();automation_tick()
    rows=client.get('/api/business-drafts').json()
    assert len([x for x in rows if x['kind']=='invoice_draft'])==1
    assert client.get('/api/payments').json()==[]
