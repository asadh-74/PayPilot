"""Invoice snapshots, private PDF exports, and currency-separated receivables."""
import csv
import io
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from . import db, security

router=APIRouter()

class BusinessProfile(BaseModel):
    address:str=Field(default='',max_length=800)
    registration_id:str=Field(default='',max_length=100)
    contact_email:str=Field(default='',max_length=254)
    website:str=Field(default='',max_length=300)
    terms:str=Field(default='',max_length=1500)

def business_profile(conn,owner):
    value=conn.scalar(select(db.business_profiles.c.data_json).where(db.business_profiles.c.owner_id==owner))
    return json.loads(value) if value else BusinessProfile().model_dump()

@router.get('/api/business-profile')
def get_profile(user=Depends(security.current_user)):
    with db.engine.connect() as conn:return business_profile(conn,user['id'])

@router.put('/api/business-profile')
def save_profile(body:BusinessProfile,user=Depends(security.current_user)):
    from .main import admin_only,audit
    admin_only(user)
    with db.engine.begin() as conn:
        conn.execute(select(db.users).where(db.users.c.id==user['id']).with_for_update()).first()
        conn.execute(delete(db.business_profiles).where(db.business_profiles.c.owner_id==user['id']))
        conn.execute(db.business_profiles.insert().values(owner_id=user['id'],data_json=json.dumps(body.model_dump(),ensure_ascii=False)))
        audit(conn,user['id'],None,'billing.profile_updated','Business billing details updated for future invoices')
    return {'ok':True}

def freeze_invoice(conn,p,body,sequence):
    prefs=conn.execute(select(db.workspace_preferences).where(db.workspace_preferences.c.owner_id==p['owner_id'])).mappings().first() or {}
    snapshot=business_profile(conn,p['owner_id'])
    snapshot.update(business_name=prefs.get('business_name') or 'My business',
        payment_instructions=prefs.get('payment_instructions') or '',customer_address=body.customer_address,
        customer_tax_id=body.customer_tax_id,purchase_order=body.purchase_order)
    number=f"INV-{datetime.fromtimestamp(p['created_at'],timezone.utc).year}-{sequence:06d}"
    conn.execute(db.invoice_documents.insert().values(payment_id=p['id'],owner_id=p['owner_id'],invoice_number=number,data_json=json.dumps(snapshot,ensure_ascii=False)))

def document_info(conn,p):
    row=conn.execute(select(db.invoice_documents).where(db.invoice_documents.c.payment_id==p['id'],db.invoice_documents.c.owner_id==p['owner_id'])).mappings().first()
    if row:return {**json.loads(row['data_json']),'invoice_number':row['invoice_number'],'historical_snapshot':True}
    # Never present current business data as historical information on old invoices.
    return {'invoice_number':'INV-'+p['id'][:8].upper(),'business_name':'PayPilot invoice','historical_snapshot':False}

@router.get('/api/payments/{pid}/pdf')
def invoice_pdf(pid:str,user=Depends(security.current_user)):
    from .main import payment
    with db.engine.connect() as conn:
        p=payment(conn,pid,user['id'])
        info=document_info(conn,p)
        meta=conn.execute(select(db.invoice_metadata).where(db.invoice_metadata.c.payment_id==pid)).mappings().first() or {}
        items=conn.execute(select(db.items).where(db.items.c.payment_id==pid).order_by(db.items.c.position)).mappings().all()
    return Response(build_pdf(p,meta,items,info),media_type='application/pdf',headers={
        'Content-Disposition':f'attachment; filename="{info["invoice_number"]}.pdf"','Cache-Control':'no-store'})

def build_pdf(p,meta,items,info):
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether
    fontdir=Path(reportlab.__file__).parent/'fonts'
    if 'PayPilot' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('PayPilot',str(fontdir/'Vera.ttf')))
        pdfmetrics.registerFont(TTFont('PayPilotBold',str(fontdir/'VeraBd.ttf')))
        pdfmetrics.registerFontFamily('PayPilot',normal='PayPilot',bold='PayPilotBold',italic='PayPilot',boldItalic='PayPilotBold')
    styles=getSampleStyleSheet()
    normal=ParagraphStyle('Body',fontName='PayPilot',fontSize=9,leading=14,textColor=colors.HexColor('#27332f'),spaceAfter=6)
    title=ParagraphStyle('Heading',parent=normal,fontName='PayPilotBold',fontSize=27,leading=34,spaceAfter=12)
    muted=ParagraphStyle('Muted',parent=normal,fontSize=8,textColor=colors.HexColor('#61746b'))
    def para(value,style=normal):return Paragraph(escape(str(value or '')).replace('\n','<br/>'),style)
    buf=io.BytesIO();doc=SimpleDocTemplate(buf,pagesize=(595.28,841.89),leftMargin=44,rightMargin=44,topMargin=42,bottomMargin=48,title=info['invoice_number'],author=info.get('business_name',''))
    money=lambda amount:f"{Decimal(str(amount)):,.2f} {p['currency']}"
    paid=p['status']=='CAPTURED'
    story=[para('INVOICE',title),para(info['invoice_number']),para('Payment recorded' if paid else 'Awaiting payment',muted),Spacer(1,14)]
    seller='\n'.join(str(info.get(k) or '') for k in ('business_name','address','contact_email','website') if info.get(k))
    if info.get('registration_id'):seller+='\nRegistration / tax reference: '+info['registration_id']
    buyer='\n'.join(str(x) for x in (meta.get('customer_name','Customer'),p.get('recipient_email',''),info.get('customer_address','')) if x)
    if info.get('customer_tax_id'):buyer+='\nCustomer tax reference: '+info['customer_tax_id']
    parties=Table([[para('FROM',muted),para('BILL TO',muted)],[para(seller),para(buyer)]],colWidths=[253,254]);parties.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),15)]));story+=[parties,Spacer(1,14)]
    issue=meta.get('issued_date') or datetime.fromtimestamp(p['created_at'],timezone.utc).date().isoformat()
    due=datetime.fromtimestamp(p['due_at'],timezone.utc).date().isoformat()
    story+=[para(f'Issued: {issue}    Due: {due}    Currency: {p["currency"]}',muted)]
    if info.get('purchase_order'):story.append(para('Purchase order: '+info['purchase_order'],muted))
    rows=[[para('DESCRIPTION',muted),para('QTY',muted),para('UNIT PRICE',muted),para('AMOUNT',muted)]]
    for item in items or [{'description':p['description'],'quantity':1,'unit_amount':p['amount']}]:
        rows.append([para(item['description']),para(item['quantity']),para(f"{Decimal(str(item['unit_amount'])):,.2f}"),para(f"{Decimal(str(item['unit_amount']))*item['quantity']:,.2f}")])
    table=Table(rows,colWidths=[265,42,95,105],repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf3ed')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),0.7,colors.HexColor('#10734b')),('LINEBELOW',(0,1),(-1,-1),0.25,colors.HexColor('#dde5df')),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story+=[Spacer(1,10),table,Spacer(1,16),para('TOTAL  '+money(p['amount']),ParagraphStyle('Total',parent=normal,fontName='PayPilotBold',fontSize=16,leading=22)),para('Balance due: '+money(0 if paid else p['amount']))]
    for label,key in [('Payment instructions','payment_instructions'),('Terms','terms')]:
        if info.get(key):story.extend([Spacer(1,12),para(label,ParagraphStyle(label,parent=normal,fontName='PayPilotBold')),para(info[key])])
    if meta.get('notes'):story.extend([Spacer(1,12),para('Notes',muted),para(meta['notes'])])
    notice='Manual payment record: transfers take place outside PayPilot. Paid status reflects administrator confirmation, not independent bank verification.' if p['mode']=='manual' else 'SANDBOX / DEMO: no real payment is represented by this document.'
    if not info.get('historical_snapshot'):notice+=' Legacy invoice: original seller billing details were not stored.'
    story.extend([Spacer(1,18),para(notice,muted)])
    def footer(canvas,document):
        canvas.saveState();canvas.setFont('PayPilot',8);canvas.setFillColor(colors.HexColor('#61746b'));canvas.drawString(44,25,info['invoice_number']);canvas.drawRightString(551,25,f'Page {document.page}');canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buf.getvalue()

@router.get('/api/reports/receivables')
def receivables(user=Depends(security.current_user)):
    from .main import public
    with db.engine.connect() as conn:
        rows=conn.execute(select(db.payments).where(db.payments.c.owner_id==user['id'],db.payments.c.mode=='manual')).mappings().all()
        docs={x['payment_id']:x['invoice_number'] for x in conn.execute(select(db.invoice_documents).where(db.invoice_documents.c.owner_id==user['id'])).mappings()}
    groups={};records=[];now=time.time()
    for p in rows:
        amount=Decimal(str(p['amount']));paid=p['status']=='CAPTURED';days=max(0,int((now-p['due_at'])/86400))
        bucket='paid' if paid else 'not_due' if p['due_at']>=now else 'overdue_1_30' if now-p['due_at']<=30*86400 else 'overdue_31_60' if now-p['due_at']<=60*86400 else 'overdue_61_plus'
        group=groups.setdefault(p['currency'],{k:Decimal('0') for k in ('invoiced','paid','not_due','overdue_1_30','overdue_31_60','overdue_61_plus','outstanding')})
        group['invoiced']+=amount;group[bucket]+=amount
        if not paid:group['outstanding']+=amount
        records.append({'number':docs.get(p['id'],'INV-'+p['id'][:8].upper()),'customer_email':p['recipient_email'] or '', 'currency':p['currency'],'amount':f'{amount:.2f}','balance':f'{0 if paid else amount:.2f}','bucket':bucket,'due_date':datetime.fromtimestamp(p['due_at'],timezone.utc).date().isoformat()})
    return {'as_of':datetime.now(timezone.utc).isoformat(),'basis':'Manual invoices only. No FX conversion or tax calculation. Paid balances reflect administrator confirmation.','currencies':{c:{k:f'{v:.2f}' for k,v in g.items()} for c,g in groups.items()},'invoices':records}

@router.get('/api/reports/receivables.csv')
def receivables_csv(user=Depends(security.current_user)):
    rows=receivables(user)['invoices'];buf=io.StringIO();writer=csv.DictWriter(buf,fieldnames=['number','customer_email','currency','amount','balance','bucket','due_date']);writer.writeheader()
    for row in rows:writer.writerow({k:"'"+str(v) if str(v).lstrip().startswith(('=','+','-','@')) else v for k,v in row.items()})
    return Response('\ufeff'+buf.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="paypilot-receivables.csv"'})


@router.get('/api/customer/{token}/pdf')
def customer_pdf(token:str):
    if len(token)>100:raise HTTPException(404,'Invoice link unavailable')
    with db.engine.connect() as conn:
        link=conn.execute(select(db.share_links).where(db.share_links.c.token_hash==security.digest(token),db.share_links.c.expires_at>time.time())).mappings().first()
        if not link:raise HTTPException(404,'Invoice link expired or revoked')
        owner=link['owner_id'];pid=link['payment_id']
    return invoice_pdf(pid,{'id':owner})
