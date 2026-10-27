"""Workspace customers, quotes, recurring drafts and verified payment installments."""
import calendar,json,time,uuid
from datetime import date,datetime,timezone
from decimal import Decimal
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,Field,field_validator,ValidationError
from sqlalchemy import select,func,update
from . import db,security
router=APIRouter()

def owner(user=Depends(security.current_user)):
    from .main import admin_only
    admin_only(user)
    return user

def lock(conn,user):
    conn.execute(select(db.users).where(db.users.c.id==user['id']).with_for_update()).first()

def scoped(conn,table,id,user):
    row=conn.execute(select(table).where(table.c.id==id,table.c.owner_id==user['id'])).mappings().first()
    if not row:raise HTTPException(404,'Record not found')
    return dict(row)

class Customer(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    email:str=Field(min_length=3,max_length=254)
    address:str=Field(default='',max_length=800)
    tax_id:str=Field(default='',max_length=100)
    @field_validator('email')
    @classmethod
    def email_valid(cls,v):
        import re
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v):raise ValueError('Enter a valid email')
        return v.strip().lower()

@router.get('/api/customers')
def customers(user=Depends(owner)):
    with db.engine.connect() as conn:
        return [dict(x) for x in conn.execute(select(db.customers).where(db.customers.c.owner_id==user['id']).order_by(db.customers.c.name)).mappings()]

@router.post('/api/customers')
def add_customer(body:Customer,user=Depends(owner)):
    with db.engine.begin() as conn:
        lock(conn,user)
        if conn.scalar(select(db.customers.c.id).where(db.customers.c.owner_id==user['id'],db.customers.c.email==body.email)):
            raise HTTPException(409,'A customer with this email already exists')
        if conn.scalar(select(func.count()).select_from(db.customers).where(db.customers.c.owner_id==user['id']))>=2000:raise HTTPException(409,'Customer limit reached')
        row=dict(id=str(uuid.uuid4()),owner_id=user['id'],**body.model_dump())
        conn.execute(db.customers.insert().values(**row))
    return row

@router.put('/api/customers/{id}')
def edit_customer(id:str,body:Customer,user=Depends(owner)):
    with db.engine.begin() as conn:
        lock(conn,user);scoped(conn,db.customers,id,user)
        if conn.scalar(select(db.customers.c.id).where(db.customers.c.owner_id==user['id'],db.customers.c.email==body.email,db.customers.c.id!=id)):raise HTTPException(409,'Email already used by another customer')
        conn.execute(update(db.customers).where(db.customers.c.id==id).values(**body.model_dump()))
    return {'ok':True}

def balance_rows(conn,rows):
    rows=list(rows)
    if not rows:return []
    sums=dict(conn.execute(select(db.installments.c.payment_id,func.sum(db.installments.c.amount)).where(db.installments.c.owner_id==rows[0]['owner_id']).group_by(db.installments.c.payment_id)).all())
    return [balances(conn,p,sums.get(p['id'],Decimal(0))) for p in rows]

def balances(conn,p,recorded=None):
    total=Decimal(str(p['amount']))
    paid=total if p['status']=='CAPTURED' else recorded if recorded is not None else Decimal(str(conn.scalar(select(func.coalesce(func.sum(db.installments.c.amount),0)).where(db.installments.c.payment_id==p['id']))))
    return {**dict(p),'paid_amount':paid,'balance_due':max(Decimal('0'),total-paid)}

class Installment(BaseModel):
    amount:Decimal=Field(gt=0,max_digits=12,decimal_places=2)
    reference:str=Field(min_length=6,max_length=120,pattern=r'.*\S.*')
    verified:bool=False

@router.get('/api/payments/{pid}/installments')
def ledger(pid:str,user=Depends(owner)):
    from .main import payment,public
    with db.engine.connect() as conn:
        p=payment(conn,pid,user['id'])
        return {'invoice':public(balances(conn,p)),'entries':[public(x) for x in conn.execute(select(db.installments).where(db.installments.c.payment_id==pid).order_by(db.installments.c.created_at)).mappings()]}

@router.post('/api/payments/{pid}/installments')
def record_installment(pid:str,body:Installment,user=Depends(owner)):
    from .main import payment,public,capture_local,audit
    if not body.verified:raise HTTPException(422,'Verify the transfer in your bank statement first')
    reference=body.reference.strip()
    with db.engine.begin() as conn:
        lock(conn,user);p=payment(conn,pid,user['id'],True)
        if p['mode']!='manual':raise HTTPException(409,'Manual invoices only')
        old=conn.execute(select(db.installments).where(db.installments.c.owner_id==user['id'],db.installments.c.reference==reference)).mappings().first()
        if old:
            if old['payment_id']==pid and old['amount']==body.amount:return public(balances(conn,p))
            raise HTTPException(409,'Transfer reference already recorded')
        if conn.scalar(select(db.payment_reports.c.payment_id).where(db.payment_reports.c.owner_id==user['id'],db.payment_reports.c.reference==reference,db.payment_reports.c.status=='APPROVED')):raise HTTPException(409,'Transfer reference already approved')
        b=balances(conn,p)
        if body.amount>b['balance_due']:raise HTTPException(409,'Amount exceeds the remaining balance')
        conn.execute(update(db.outbox).where(db.outbox.c.payment_id==pid,db.outbox.c.kind=='reminder',db.outbox.c.status=='DRAFT').values(status='STALE'))
        conn.execute(db.installments.insert().values(id=str(uuid.uuid4()),owner_id=user['id'],payment_id=pid,amount=body.amount,reference=reference,created_at=time.time()))
        audit(conn,user['id'],pid,'payment.installment','Verified installment recorded: '+str(body.amount)+' '+p['currency'])
        if body.amount==b['balance_due']:
            capture_local(conn,p)
            conn.execute(update(db.payment_reports).where(db.payment_reports.c.payment_id==pid,db.payment_reports.c.status=='SUBMITTED').values(status='CLOSED',reviewed_at=time.time()))
        return public(balances(conn,payment(conn,pid,user['id'])))

class DraftInput(BaseModel):
    title:str=Field(min_length=1,max_length=160)
    invoice:dict
    kind:str=Field(default='quote',pattern='^(quote|recurring)$')
    next_date:date|None=None

@router.post('/api/business-drafts')
def new_draft(body:DraftInput,user=Depends(owner)):
    from .main import PaymentInput
    try:invoice=PaymentInput(**body.invoice)
    except ValidationError:raise HTTPException(422,'Check invoice fields, currency, amounts and line items')
    if invoice.items and sum((i.unit_amount*i.quantity for i in invoice.items),Decimal(0))!=invoice.amount:raise HTTPException(422,'Line items must equal the total')
    if body.kind=='recurring' and body.next_date is None:raise HTTPException(422,'Choose the first billing date')
    with db.engine.begin() as conn:
        lock(conn,user)
        if conn.scalar(select(func.count()).select_from(db.business_drafts).where(db.business_drafts.c.owner_id==user['id']))>=2000:raise HTTPException(409,'Draft limit reached')
        row=dict(id=str(uuid.uuid4()),owner_id=user['id'],title=body.title,kind=body.kind,status='ACTIVE' if body.kind=='recurring' else 'DRAFT',data_json=invoice.model_dump_json(),next_date=body.next_date.isoformat() if body.next_date else None,payment_id=None,created_at=time.time())
        conn.execute(db.business_drafts.insert().values(**row))
    return row

@router.get('/api/business-drafts')
def drafts(user=Depends(owner)):
    with db.engine.connect() as conn:
        return [{**dict(x),'invoice':json.loads(x['data_json'])} for x in conn.execute(select(db.business_drafts).where(db.business_drafts.c.owner_id==user['id']).order_by(db.business_drafts.c.created_at.desc())).mappings()]

@router.post('/api/business-drafts/{id}/convert')
def convert(id:str,request:Request,user=Depends(owner)):
    from .main import PaymentInput,create_payment
    with db.engine.connect() as conn:row=scoped(conn,db.business_drafts,id,user)
    if row['kind']=='recurring':raise HTTPException(409,'Generate a recurring draft first')
    if row['status']=='CANCELLED':raise HTTPException(409,'Draft was cancelled')
    payload=json.loads(row['data_json'])
    # Freeze the conversion request once so retries after midnight stay idempotent.
    with db.engine.begin() as conn:
        lock(conn,user);row=scoped(conn,db.business_drafts,id,user)
        if row['status']=='CANCELLED':raise HTTPException(409,'Draft was cancelled')
        if row['status']=='DRAFT':
            payload.update(issue_date=date.today().isoformat(),due_date=None)
            conn.execute(update(db.business_drafts).where(db.business_drafts.c.id==id).values(status='CONVERTING',data_json=json.dumps(payload)))
        else:payload=json.loads(row['data_json'])
    scope=dict(request.scope);scope['headers']=[(b'idempotency-key',('draft-'+id).encode())]
    result=create_payment(PaymentInput(**payload),Request(scope),user)
    with db.engine.begin() as conn:conn.execute(update(db.business_drafts).where(db.business_drafts.c.id==id).values(status='CONVERTED',payment_id=result['id']))
    return result

@router.post('/api/business-drafts/{id}/cancel')
def cancel(id:str,user=Depends(owner)):
    with db.engine.begin() as conn:
        lock(conn,user);row=scoped(conn,db.business_drafts,id,user)
        if row['status'] not in ('DRAFT','ACTIVE'):raise HTTPException(409,'Only unused drafts or active templates can be cancelled')
        conn.execute(update(db.business_drafts).where(db.business_drafts.c.id==id).values(status='CANCELLED'))
    return {'ok':True}

@router.post('/api/recurring/prepare')
def prepare_recurring(user=Depends(owner)):
    today=date.today();created=0
    with db.engine.begin() as conn:
        lock(conn,user)
        rows=conn.execute(select(db.business_drafts).where(db.business_drafts.c.owner_id==user['id'],db.business_drafts.c.kind=='recurring',db.business_drafts.c.status=='ACTIVE',db.business_drafts.c.next_date<=today.isoformat())).mappings().all()
        for row in rows:
            if conn.scalar(select(func.count()).select_from(db.business_drafts).where(db.business_drafts.c.owner_id==user['id']))>=2000:break
            due=date.fromisoformat(row['next_date']);key=str(uuid.uuid5(uuid.NAMESPACE_URL,row['id']+due.isoformat()))
            if not conn.scalar(select(db.business_drafts.c.id).where(db.business_drafts.c.id==key)):
                conn.execute(db.business_drafts.insert().values(id=key,owner_id=user['id'],title=row['title']+' · '+due.isoformat(),kind='invoice_draft',status='DRAFT',data_json=row['data_json'],created_at=time.time()))
                created+=1
            # Catch up one period per explicit run; never send or issue automatically.
            month=due.month%12+1;year=due.year+(due.month==12)
            anchor=date.fromisoformat(json.loads(row['data_json']).get('_anchor',due.isoformat())).day
            data=json.loads(row['data_json']);data.setdefault('_anchor',due.isoformat())
            nxt=date(year,month,min(anchor,calendar.monthrange(year,month)[1]))
            conn.execute(update(db.business_drafts).where(db.business_drafts.c.id==row['id']).values(next_date=nxt.isoformat(),data_json=json.dumps(data)))
    return {'prepared':created,'message':'Drafts prepared for review; no invoices issued or emails sent.'}
