"""Server-side HTTPS email or TLS SMTP delivery. Configuration and secrets never enter browser state."""
import os
import hashlib
import requests
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr


class DeliveryRejected(Exception):
    """Provider explicitly rejected the request; safe to retry after correction."""


def provider():
    return os.getenv('EMAIL_PROVIDER','resend').lower()


def ready():
    if provider()=='resend': return bool(os.getenv('RESEND_API_KEY') and os.getenv('EMAIL_FROM'))
    if provider()!='smtp': return False
    return bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD') and os.getenv('SMTP_FROM'))


def send(recipient, subject, body, message_id=''):
    sender=os.environ['EMAIL_FROM' if provider()=='resend' else 'SMTP_FROM']
    if any('\r' in v or '\n' in v for v in [recipient,subject,sender]):
        raise ValueError('Invalid email header')
    address=parseaddr(sender)[1]
    if '@' not in address: raise ValueError('Invalid sender address')
    if provider()=='resend':
        payload={'from':sender,'to':[recipient],'subject':subject,'text':body}
        key=hashlib.sha256((message_id+'|'+recipient+'|'+subject+'|'+body).encode()).hexdigest()
        response=requests.post('https://api.resend.com/emails',headers={'Authorization':'Bearer '+os.environ['RESEND_API_KEY'],'Idempotency-Key':'paypilot-'+key},json=payload,timeout=(5,20))
        if 400<=response.status_code<500 and response.status_code not in (408,409):
            raise DeliveryRejected('Email provider rejected this message. Check the API key, verified sender and recipient restrictions.')
        response.raise_for_status()
        if not response.json().get('id'): raise RuntimeError('Provider acceptance was not confirmed')
        return
    message=EmailMessage()
    message['From']=sender;message['To']=recipient;message['Subject']=subject
    message.set_content(body)
    port=int(os.getenv('SMTP_PORT','587'))
    if port not in (465,587): raise ValueError('Use TLS SMTP port 465 or 587')
    ctx=ssl.create_default_context()
    transport=smtplib.SMTP_SSL if port==465 else smtplib.SMTP
    with transport(os.environ['SMTP_HOST'],port,timeout=20,**({'context':ctx} if port==465 else {})) as server:
        if port==587:
            server.ehlo();server.starttls(context=ctx);server.ehlo()
        server.login(os.environ['SMTP_USERNAME'],os.environ['SMTP_PASSWORD'])
        refused=server.send_message(message)
        if refused: raise smtplib.SMTPRecipientsRefused(refused)
