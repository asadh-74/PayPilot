"""Conservative sentence-to-invoice extraction. Never creates or sends anything."""
import re
from datetime import date, timedelta
from decimal import Decimal

MONEY = r'(?:PKR|USD|EUR|GBP|CAD|AUD|SGD|AED|SAR|Rs\.?|[$€£])\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?)(?![\d.,])'


def parse(text, today=None):
    today = today or date.today()
    text = text.strip()
    if not text:
        raise ValueError('Describe a customer, service and currency amount.')
    if re.search(r'\b(?:tax|discount|VAT|INR|JPY|BRL|MXN)\b|%',text,re.I):
        raise ValueError('Use the item form for taxes, discounts or unsupported currencies.')
    if re.search(r'(?<![\w])[-−]\s*(?:(?:PKR|USD|EUR|GBP|CAD|AUD|SGD|AED|SAR|Rs\.?|[$€£])\s*)?\d',text,re.I):
        raise ValueError('Quantities and amounts must be positive.')
    email = re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text)
    emails = re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text)
    if len(set(emails)) > 1:
        raise ValueError('Use one customer email per invoice.')
    codes = {c.upper() for c in re.findall(r'\b(PKR|USD|EUR|GBP|CAD|AUD|SGD|AED|SAR)\b', text, re.I)}
    if re.search(r'\bRs\.?\s*\d', text, re.I): codes.add('PKR')
    for symbol, code in [('$','USD'),('€','EUR'),('£','GBP')]:
        if symbol in text and not (symbol=='$' and codes & {'CAD','AUD','SGD'}): codes.add(code)
    if len(codes) != 1:
        raise ValueError('Specify exactly one currency, for example PKR 20,000 or USD 250.')
    currency = codes.pop()
    due = today + timedelta(days=14)
    day_match = re.search(r'\bdue\s+in\s+(\d+)\s+days?\b', text, re.I)
    exact = re.search(r'\bdue(?:\s+on)?\s+(\d{4}-\d{2}-\d{2})\b', text, re.I)
    if day_match:
        days=int(day_match.group(1))
        if not 0<=days<=365: raise ValueError('Due date must be within 365 days.')
        due=today+timedelta(days=days)
    elif exact:
        due=date.fromisoformat(exact.group(1))
        if due<today: raise ValueError('Due date is in the past.')
    elif re.search(r'\bdue\b', text, re.I):
        raise ValueError('Use “due in 14 days” or “due 2026-12-01”.')
    work = re.split(r'\bdue\b', text, maxsplit=1, flags=re.I)[0]
    if email: work=work.replace(email.group(), '')
    customer=re.search(r'\b(?:invoice|bill)(?:\s+for)?\s+(.+?)(?=\s+(?:at|for|email)\b|[,;]|$)',work,re.I)
    name=customer.group(1).strip(' ,') if customer else ''
    # Explicit item syntax: 2 logo designs at PKR 5000 each; 3 banners at PKR 1000 each.
    pattern=r'(\d+)\s*(?:x\s+)?([A-Za-z][^;\n]*?)\s+(?:at|@)\s*'+MONEY+r'(?:\s*(?:each|per item))?'
    items=[]
    for match in re.finditer(pattern,work,re.I):
        qty=int(match.group(1)); amount=Decimal(match.group(3).replace(',',''))
        if not 1<=qty<=10000 or amount<=0: raise ValueError('Check quantity and unit price.')
        items.append({'description':match.group(2).strip(' ,'),'quantity':qty,'unit_amount':str(amount)})
    money=list(re.finditer(MONEY,work,re.I))
    if len(items)>30: raise ValueError('Maximum 30 line items.')
    if items:
        if len(items)!=len(money): raise ValueError('Some prices could not be matched to items. Use semicolons between items.')
    else:
        if len(money)!=1: raise ValueError('Use one total amount, or “2 logo designs at PKR 5000 each”.')
        amount=Decimal(money[0].group(1).replace(',',''))
        if amount<=0 or re.search(r'-\s*(?:PKR|USD|EUR|GBP|Rs\.?|[$€£])?\s*\d',work,re.I): raise ValueError('Amount must be positive.')
        desc=re.search(r'\bfor\s+(.+)',work,re.I)
        description=(desc.group(1) if desc else work)
        description=re.sub(MONEY,'',description,flags=re.I)
        description=re.sub(r'\b(?:email|at|total|amount)\b','',description,flags=re.I).strip(' ,.;')
        if not description: raise ValueError('Include a service description, such as “for website design”.')
        items=[{'description':description[:240],'quantity':1,'unit_amount':str(amount)}]
    total=sum((Decimal(i['unit_amount'])*i['quantity'] for i in items),Decimal('0'))
    return {'customer_name':name[:120],'recipient_email':email.group() if email else None,
            'currency':currency,'amount':str(total),'description':items[0]['description'],
            'items':items,'issue_date':today.isoformat(),'due_date':due.isoformat(),'notes':'',
            'provider':'Built-in sentence parser','warnings':['Review extracted details before creating or sending.']+([] if name else ['Customer name needs your review.'])}
