"""PayPilot: sandbox payments, isolated demos, and transactional automation."""
import csv
import hashlib
import io
import json
import os
import re
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Lock, Event, Thread

from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update, delete, func, text
from sqlalchemy.exc import IntegrityError
from . import db, ai_service, security
from .paypal_client import PayPalClient

paypal = PayPalClient()
STATIC = Path(__file__).parent / 'static'
limits = defaultdict(deque)
limit_lock = Lock()

@asynccontextmanager
async def lifespan(app):
    db.init_db()
    stop = Event()
    worker = None
    if scheduler_enabled():
        worker = Thread(target=automation_loop, args=(stop,), daemon=True, name='paypilot-automation')
        worker.start()
    try:
        yield
    finally:
        stop.set()
        if worker:
            worker.join(timeout=25)
        db.engine.dispose()

app = FastAPI(title='PayPilot API', version='2.1.0', lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
app.mount('/static', StaticFiles(directory=STATIC), name='static')

@app.middleware('http')
async def protections(request, call_next):
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and request.url.path != '/webhooks/paypal':
        if request.headers.get('x-paypilot-client') != 'dashboard':
            return JSONResponse({'detail': 'Missing request verification header'}, status_code=403)
    if request.method == 'POST':
        key = (request.client.host if request.client else 'unknown', request.url.path)
        with limit_lock:
            now = time.monotonic()
            # Bound memory and expire old paths/IPs.
            if len(limits) > 10000:
                limits.clear()
            bucket = limits[key]
            while bucket and bucket[0] < now - 60:
                bucket.popleft()
            ceiling = 10 if request.url.path.startswith('/api/auth') else 60
            if len(bucket) >= ceiling:
                return JSONResponse({'detail': 'Please wait a minute before trying again.'}, status_code=429)
            bucket.append(now)
    try:
        response = await call_next(request)
    except Exception:
        # Never expose SQL connection strings, provider payloads, or credentials.
        return JSONResponse({'detail': 'Service unavailable. Please retry shortly.'}, status_code=503)
    response.headers.update({'X-Content-Type-Options':'nosniff', 'Referrer-Policy':'same-origin',
        'X-Frame-Options':'DENY', 'Cache-Control':'no-store',
        'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
    return response

class Login(BaseModel):
    password: str = Field(max_length=512)

class PaymentInput(BaseModel):
    amount: Decimal = Field(gt=0, le=9999999, max_digits=12, decimal_places=2)
    currency: str = 'USD'
    description: str = Field(min_length=1, max_length=240)
    recipient_email: str | None = Field(default=None, max_length=254)
    due_days: int = Field(default=7, ge=0, le=365)

    @field_validator('currency')
    @classmethod
    def currency_supported(cls, value):
        value = value.upper()
        if value not in {'USD','EUR','GBP','CAD','AUD','SGD'}:
            raise ValueError('Choose USD, EUR, GBP, CAD, AUD, or SGD')
        return value

    @field_validator('recipient_email')
    @classmethod
    def email_valid(cls, value):
        if value and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
            raise ValueError('Enter a valid email address')
        return value or None

class Prompt(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)

class Rules(BaseModel):
    receipts: bool
    reminders: bool

def uid():
    return str(uuid.uuid4())

def payment(conn, pid, owner=None, lock=False):
    query = select(db.payments).where(db.payments.c.id == pid)
    if owner:
        query = query.where(db.payments.c.owner_id == owner)
    if lock:
        query = query.with_for_update()
    row = conn.execute(query).mappings().first()
    if not row:
        raise HTTPException(404, 'Payment not found')
    return dict(row)

def public(row):
    return {k: float(v) if isinstance(v, Decimal) else v for k,v in dict(row).items()
            if k not in ('owner_id','request_hash','idempotency_key')}

def audit(conn, owner, pid, kind, detail, event_id=None):
    conn.execute(db.events.insert().values(id=event_id or uid(), owner_id=owner,
                 payment_id=pid, kind=kind, detail=detail, created_at=time.time()))

def queue_message(conn, p, kind, key):
    if conn.execute(select(db.outbox.c.id).where(db.outbox.c.id == key)).first():
        return False
    body = (f"{'DEMO — simulated payment. ' if p['mode']=='demo' else 'PAYPAL SANDBOX — test funds only. '}"
            f"{'Payment received' if kind=='receipt' else 'Payment reminder'}: "
            f"{p['amount']:.2f} {p['currency']} for {p['description']}. Reference {p['id']}.")
    conn.execute(db.outbox.insert().values(id=key, owner_id=p['owner_id'], payment_id=p['id'],
                 recipient=p['recipient_email'] or 'customer@example.com', kind=kind,
                 subject=f"{kind.title()} · {p['description'][:120]}", body=body,
                 status='DEMO_OUTBOX', created_at=time.time()))
    if kind == 'receipt':
        conn.execute(update(db.payments).where(db.payments.c.id == p['id']).values(receipt_text=body))
    audit(conn, p['owner_id'], p['id'], f'automation.{kind}', 'Saved to controlled outbox; no email sent.')
    return True

def capture_local(conn, p):
    if p['status'] == 'CAPTURED':
        return
    conn.execute(update(db.payments).where(db.payments.c.id==p['id']).values(status='CAPTURED', updated_at=time.time()))
    audit(conn,p['owner_id'],p['id'],'payment.captured',f"{'Simulated' if p['mode']=='demo' else 'Sandbox'} capture confirmed")
    rule = conn.execute(select(db.settings).where(db.settings.c.owner_id==p['owner_id'])).mappings().one()
    if rule['receipts']:
        queue_message(conn,p,'receipt',f"receipt-{p['id']}")

def seed(conn, owner):
    now = time.time()
    samples = [('Brand identity design','Maya Studio',480,'CAPTURED',2),
               ('Website development','Northstar Labs',1250,'CAPTURED',4),
               ('Monthly SEO retainer','Olive & Co',320,'CREATED',10),
               ('Product photography','Lumen Goods',650,'CREATED',1),
               ('UX research sprint','Orbit Design',890,'CAPTURED',6),
               ('API integration','Atlas Works',2400,'CREATED',9)]
    for desc, name, amount, status, days in samples:
        pid = uid()
        p = dict(id=pid, owner_id=owner, amount=Decimal(amount),currency='USD',
                 description=f'{desc} · {name}',recipient_email=name.split()[0].lower()+'@example.com',
                 status='CREATED',mode='demo', due_at=now+(7-days)*86400,
                 created_at=now-days*86400,updated_at=now-days*86400)
        conn.execute(db.payments.insert().values(**p))
        audit(conn,owner,pid,'invoice.created','Fictional hackathon sample')
        if status=='CAPTURED':
            capture_local(conn,p)

@app.get('/', response_class=HTMLResponse)
def index():
    return (STATIC/'index.html').read_text()

@app.get('/health')
def health():
    try:
        with db.engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        return {'status':'ok','database':db.engine.dialect.name,'version':'2.1.0'}
    except Exception:
        raise HTTPException(503,'Database is not ready')

@app.get('/api/config')
def config():
    return {'sandbox_ready':bool(paypal.client_id and paypal.client_secret),
            'demo_enabled':os.getenv('DEMO_ENABLED','true')=='true',
            'database':db.engine.dialect.name,
            'persistence':'ephemeral demo storage' if db.engine.dialect.name=='sqlite' else 'persistent MySQL',
            'ai_provider':ai_service.active_provider()}

@app.post('/api/auth/demo')
def demo(response: Response):
    if os.getenv('DEMO_ENABLED','true')!='true':
        raise HTTPException(403,'Demo is disabled')
    owner='demo-'+uid()
    with db.engine.begin() as conn:
        conn.execute(db.users.insert().values(id=owner,role='demo',created_at=time.time()))
        conn.execute(db.settings.insert().values(owner_id=owner,receipts=1,reminders=1))
        seed(conn,owner)
        token=security.issue_session(conn,owner)
    security.set_cookie(response,token)
    return {'role':'demo'}

@app.post('/api/auth/login')
def login(body: Login,response: Response):
    if not security.valid_admin(body.password):
        raise HTTPException(401,'Invalid credentials or administrator not configured')
    with db.engine.begin() as conn:
        if not conn.execute(select(db.users).where(db.users.c.id=='admin')).first():
            conn.execute(db.users.insert().values(id='admin',role='admin',created_at=time.time()))
            conn.execute(db.settings.insert().values(owner_id='admin',receipts=1,reminders=1))
        token=security.issue_session(conn,'admin')
    security.set_cookie(response,token)
    return {'role':'admin'}

@app.get('/api/auth/me')
def me(user=Depends(security.current_user)):
    return {'role':user['role']}

@app.post('/api/auth/logout')
def logout(request: Request,response: Response):
    with db.engine.begin() as conn:
        conn.execute(delete(db.sessions).where(db.sessions.c.token_hash==security.digest(request.cookies.get(security.COOKIE,''))))
    response.delete_cookie(security.COOKIE)
    return {'ok':True}

@app.post('/api/parse')
def parse(body: Prompt,user=Depends(security.current_user)):
    try:
        # Public demos never incur AI provider charges.
        parsed = ai_service._regex_extract(body.prompt) if user['role']=='demo' else ai_service.parse_payment_prompt(body.prompt)
        result = PaymentInput(**parsed)
        return {**result.model_dump(mode='json'),'provider':'Offline parser' if user['role']=='demo' else ai_service.active_provider()}
    except (ValueError,TypeError):
        raise HTTPException(422,'Could not safely parse this request. Try “Charge $250 USD for a logo design”, or use the form.')

@app.post('/api/payments')
def create_payment(body: PaymentInput,request: Request,user=Depends(security.current_user)):
    key=request.headers.get('idempotency-key','')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{8,64}',key):
        raise HTTPException(422,'Provide an 8–64 character Idempotency-Key')
    fingerprint=hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    now=time.time()
    with db.engine.begin() as conn:
        # Serialize creations per workspace, including concurrent duplicate requests.
        conn.execute(select(db.users).where(db.users.c.id==user['id']).with_for_update()).first()
        previous=conn.execute(select(db.payments).where(db.payments.c.owner_id==user['id'],db.payments.c.idempotency_key==key)).mappings().first()
        if previous:
            if previous['request_hash']!=fingerprint:
                raise HTTPException(409,'This request key was already used for different details')
            p=dict(previous)
        else:
            count=conn.scalar(select(func.count()).select_from(db.payments).where(db.payments.c.owner_id==user['id']))
            if count>=2000 or (user['role']=='demo' and count>=50):
                raise HTTPException(409,'Workspace invoice limit reached')
            pid=uid()
            p=dict(id=pid,owner_id=user['id'],idempotency_key=key,request_hash=fingerprint,
                **body.model_dump(exclude={'due_days'}),status='CREATED' if user['role']=='demo' else 'PENDING',
                mode='demo' if user['role']=='demo' else 'sandbox',
                created_at=now,updated_at=now,due_at=now+body.due_days*86400)
            conn.execute(db.payments.insert().values(**p))
            audit(conn,user['id'],pid,'invoice.created','Payment details confirmed by user')
    if p['mode']=='sandbox' and p['status']=='PENDING':
        base=os.getenv('APP_BASE_URL','').rstrip('/')
        if not base.startswith('https://'):
            raise HTTPException(503,'Configure an HTTPS APP_BASE_URL before sandbox checkout')
        try:
            order=paypal.create_order(p['amount'],p['currency'],p['description'],p['id'],base+'/return',base+'/cancel')
            link=paypal.approve_link(order)
            if not link or not link.startswith('https://www.sandbox.paypal.com/'):
                raise ValueError('Unexpected approval URL')
        except Exception:
            raise HTTPException(502,'Sandbox checkout unavailable. Retry the same request; it will not create a duplicate invoice.')
        with db.engine.begin() as conn:
            conn.execute(update(db.payments).where(db.payments.c.id==p['id']).values(
                paypal_order_id=order['id'],approve_link=link,status='CREATED',updated_at=time.time()))
            p=payment(conn,p['id'])
    return public(p)

@app.get('/api/payments')
def list_payments(user=Depends(security.current_user)):
    with db.engine.connect() as conn:
        return [public(p) for p in conn.execute(select(db.payments).where(db.payments.c.owner_id==user['id']).order_by(db.payments.c.created_at.desc())).mappings()]

@app.post('/api/payments/{pid}/simulate')
def simulate(pid: str,user=Depends(security.current_user)):
    with db.engine.begin() as conn:
        p=payment(conn,pid,user['id'],True)
        if user['role']!='demo' or p['mode']!='demo':
            raise HTTPException(403,'Simulation is only available inside a demo workspace')
        capture_local(conn,p)
        return public(payment(conn,pid))

def validate_capture(order,p):
    captures=[capture for unit in order.get('purchase_units',[]) for capture in unit.get('payments',{}).get('captures',[])]
    return any(c.get('status')=='COMPLETED' and c.get('amount',{}).get('currency_code')==p['currency']
               and Decimal(c.get('amount',{}).get('value','-1'))==p['amount'] for c in captures)

@app.post('/api/payments/{pid}/refresh')
def refresh(pid: str,user=Depends(security.current_user)):
    with db.engine.connect() as conn:
        p=payment(conn,pid,user['id'])
    if p['mode']!='sandbox' or not p['paypal_order_id']:
        raise HTTPException(409,'This invoice has no PayPal sandbox order')
    try:
        order=paypal.get_order(p['paypal_order_id'])
        if order.get('status')=='APPROVED':
            order=paypal.capture_order(p['paypal_order_id'])
        completed=validate_capture(order,p)
    except Exception:
        raise HTTPException(502,'Unable to verify sandbox payment. Please retry.')
    with db.engine.begin() as conn:
        p=payment(conn,pid,user['id'],True)
        if completed:
            capture_local(conn,p)
        return public(payment(conn,pid))

@app.get('/api/payments/{pid}/receipt')
def receipt(pid: str,user=Depends(security.current_user)):
    with db.engine.begin() as conn:
        p=payment(conn,pid,user['id'],True)
        if p['status']!='CAPTURED':
            raise HTTPException(409,'Receipts are available only after confirmed capture')
        queue_message(conn,p,'receipt',f'receipt-{pid}')
        return {'receipt':payment(conn,pid)['receipt_text']}

@app.get('/api/analytics')
def analytics(user=Depends(security.current_user)):
    rows=list_payments(user)
    currencies={}
    for p in rows:
        c=currencies.setdefault(p['currency'],{'captured':Decimal(0),'pending':Decimal(0),'overdue':Decimal(0)})
        amount=Decimal(str(p['amount']))
        c['captured' if p['status']=='CAPTURED' else 'pending']+=amount
        if p['status']!='CAPTURED' and p['due_at']<time.time():
            c['overdue']+=amount
    daily=[]
    for offset in range(6,-1,-1):
        day=datetime.fromtimestamp(time.time()-offset*86400,timezone.utc).date()
        selected=[p for p in rows if datetime.fromtimestamp(p['created_at'],timezone.utc).date()==day]
        daily.append({'day':day.isoformat(),'created':len(selected),'captured':sum(p['status']=='CAPTURED' for p in selected)})
    captured=sum(p['status']=='CAPTURED' for p in rows)
    overdue=sum(p['status']!='CAPTURED' and p['due_at']<time.time() for p in rows)
    return {'currencies':currencies,'count':len(rows),'captured_count':captured,'overdue_count':overdue,
            'conversion':round(captured/len(rows)*100) if rows else 0,'daily':daily,
            'insights':[f'{overdue} overdue invoice(s) need follow-up.',
                        f'{captured} of {len(rows)} invoices have confirmed capture.',
                        'Revenue is grouped by currency; no exchange rates or mixed-currency totals are assumed.']}

@app.get('/api/automations')
def rules(user=Depends(security.current_user)):
    with db.engine.connect() as conn:
        r=conn.execute(select(db.settings).where(db.settings.c.owner_id==user['id'])).mappings().one()
        return {'receipts':bool(r['receipts']),'reminders':bool(r['reminders'])}

@app.put('/api/automations')
def save_rules(body: Rules,user=Depends(security.current_user)):
    with db.engine.begin() as conn:
        conn.execute(update(db.settings).where(db.settings.c.owner_id==user['id']).values(**body.model_dump()))
        audit(conn,user['id'],None,'automation.updated','Receipt and reminder rules updated')
    return body

@app.post('/api/automations/run')
def run_rules(user=Depends(security.current_user)):
    queued=0
    day=datetime.now(timezone.utc).date().isoformat()
    with db.engine.begin() as conn:
        rule=conn.execute(select(db.settings).where(db.settings.c.owner_id==user['id']).with_for_update()).mappings().one()
        rows=conn.execute(select(db.payments).where(db.payments.c.owner_id==user['id']).with_for_update()).mappings().all()
        for p in rows:
            if p['status']=='CAPTURED' and rule['receipts']:
                queued+=queue_message(conn,p,'receipt',f"receipt-{p['id']}")
            elif p['status']!='CAPTURED' and p['due_at']<time.time() and rule['reminders']:
                queued+=queue_message(conn,p,'reminder',f"reminder-{p['id']}-{day}")
        if queued:
            audit(conn,user['id'],None,'automation.run',f'{queued} new outbox item(s); daily deduplication applied')
    return {'queued':queued,'delivery':'controlled outbox; no external messages sent'}

@app.get('/api/outbox')
def outbox(user=Depends(security.current_user)):
    with db.engine.connect() as conn:
        return [public(r) for r in conn.execute(select(db.outbox).where(db.outbox.c.owner_id==user['id']).order_by(db.outbox.c.created_at.desc()).limit(100)).mappings()]

@app.get('/api/events')
def events(user=Depends(security.current_user)):
    with db.engine.connect() as conn:
        return [public(r) for r in conn.execute(select(db.events).where(db.events.c.owner_id==user['id']).order_by(db.events.c.created_at.desc()).limit(100)).mappings()]

@app.get('/api/export')
def export(user=Depends(security.current_user)):
    output=io.StringIO()
    writer=csv.writer(output)
    fields=['id','description','amount','currency','status','mode','recipient_email']
    writer.writerow(fields)
    for p in list_payments(user):
        vals=[str(p.get(k) or '') for k in fields]
        writer.writerow(["'"+v if v.lstrip().startswith(('=','+','-','@')) else v for v in vals])
    return Response(output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=paypilot-invoices.csv'})

@app.post('/webhooks/paypal')
async def webhook(request: Request):
    raw=await request.body()
    if len(raw)>262144:
        raise HTTPException(413,'Payload too large')
    try:
        payload=json.loads(raw)
        if not isinstance(payload,dict) or not paypal.verify_webhook(request.headers,payload):
            raise HTTPException(401,'Webhook signature could not be verified')
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400,'Invalid or unverifiable webhook')
    event_id=payload.get('id','')
    if not isinstance(event_id,str) or not 1<=len(event_id)<=60:
        raise HTTPException(422,'Invalid event ID')
    resource=payload.get('resource',{})
    order_id=resource.get('supplementary_data',{}).get('related_ids',{}).get('order_id')
    try:
        with db.engine.begin() as conn:
            p=conn.execute(select(db.payments).where(db.payments.c.paypal_order_id==order_id,
                           db.payments.c.mode=='sandbox').with_for_update()).mappings().first() if order_id else None
            if not p:
                return {'received':True,'matched':False}
            if conn.execute(select(db.events.c.id).where(db.events.c.id=='wh-'+event_id)).first():
                return {'received':True,'duplicate':True}
            if payload.get('event_type')=='PAYMENT.CAPTURE.COMPLETED':
                amount=resource.get('amount',{})
                if resource.get('status')!='COMPLETED' or amount.get('currency_code')!=p['currency'] or Decimal(amount.get('value','-1'))!=p['amount']:
                    raise HTTPException(422,'Capture does not match invoice')
                capture_local(conn,p)
            audit(conn,p['owner_id'],p['id'],'paypal.webhook',str(payload.get('event_type',''))[:100],'wh-'+event_id)
    except IntegrityError:
        return {'received':True,'duplicate':True}
    return {'received':True}

@app.get('/return')
def payment_return(token: str=''):
    return RedirectResponse('/?checkout=returned')

@app.get('/cancel')
def payment_cancel():
    return RedirectResponse('/?checkout=cancelled')



def scheduler_enabled():
    return os.getenv('AUTOMATION_ENABLED', 'true').lower() == 'true'


def scheduler_interval():
    try:
        return max(60, min(86400, int(os.getenv('AUTOMATION_INTERVAL_SECONDS', '300'))))
    except ValueError:
        return 300


def automation_tick():
    """Process only workspaces with an unexpired session; never send externally."""
    with db.engine.connect() as conn:
        owners = conn.execute(select(db.users.c.id, db.users.c.role).where(
            db.users.c.id.in_(select(db.sessions.c.user_id).where(
                db.sessions.c.expires_at > time.time())))).mappings().all()
    for owner in owners:
        try:
            run_rules(dict(owner))
        except Exception:
            # Keep other workspaces running; do not log database secrets.
            import logging
            logging.getLogger(__name__).warning('Automation workspace pass failed; will retry next interval')


def automation_loop(stop):
    while not stop.wait(scheduler_interval()):
        try:
            automation_tick()
        except Exception:
            import logging
            logging.getLogger(__name__).warning('Automation database pass failed; will retry next interval')


@app.get('/api/automations/status')
def automation_status(user=Depends(security.current_user)):
    with db.engine.connect() as conn:
        last = conn.execute(select(db.events.c.created_at).where(
            db.events.c.owner_id == user['id'], db.events.c.kind == 'automation.run'
        ).order_by(db.events.c.created_at.desc()).limit(1)).scalar()
    return {'enabled': scheduler_enabled(), 'interval_seconds': scheduler_interval(),
            'last_action_at': last, 'delivery': 'preview_only',
            'scope': 'Workspaces with an active session. Runs while the server is awake.'}


@app.get('/api/collections')
def collections(user=Depends(security.current_user)):
    """Explainable due-date planning; no FX or predictive payment claims."""
    now = time.time()
    groups = {}
    priorities = []
    for p in list_payments(user):
        if p['status'] == 'CAPTURED':
            continue
        days = (now - p['due_at']) / 86400
        bucket = 'not_due' if days <= 0 else 'days_1_7' if days <= 7 else 'days_8_30' if days <= 30 else 'days_31_plus'
        group = groups.setdefault(p['currency'], {k: Decimal('0') for k in (
            'not_due', 'days_1_7', 'days_8_30', 'days_31_plus', 'due_next_7_days')})
        amount = Decimal(str(p['amount']))
        group[bucket] += amount
        if now <= p['due_at'] <= now + 7 * 86400:
            group['due_next_7_days'] += amount
        if days > 0:
            priorities.append({'id': p['id'], 'description': p['description'],
                'amount': str(amount), 'currency': p['currency'],
                'days_overdue': max(1, int(days)), 'due_at': p['due_at'],
                'reason': 'Checkout setup incomplete' if p['status'] == 'PENDING' else 'Past invoice due date',
                'next_action': 'Configure sandbox and retry original request' if p['status'] == 'PENDING' else 'Prepare overdue follow-up'})
    priorities.sort(key=lambda p: p['due_at'])
    return {'currencies': {c: {k: str(v.quantize(Decimal('.01'))) for k, v in g.items()} for c, g in groups.items()},
            'priorities': priorities, 'as_of': now,
            'basis': 'Invoice due dates, not a prediction of collection. Currencies are never combined.'}
