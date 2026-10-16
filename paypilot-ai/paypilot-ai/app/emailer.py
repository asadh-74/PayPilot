"""Receipt delivery: real SMTP if configured, otherwise a built-in outbox.

Set SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / SMTP_FROM to send real emails.
Without SMTP everything still works - receipts land in the Outbox panel (and logs).
"""
import os
import smtplib
from email.message import EmailMessage

import db


def send_receipt(payment: dict, receipt_body: str):
    subject = (f"Receipt: {payment['amount']:.2f} {payment['currency']} - "
               f"{payment['description'][:50]}")
    if os.getenv("SMTP_HOST"):
        msg = EmailMessage()
        msg["From"] = os.getenv("SMTP_FROM", "receipts@paypilot.local")
        msg["To"] = payment.get("payer_email") or payment.get("recipient_email") or ""
        msg["Subject"] = subject
        msg.set_content(receipt_body)
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587"))) as s:
            if os.getenv("SMTP_USER"):
                s.starttls()
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(msg)
        db.add_outbox(msg["To"], subject + "  [sent via SMTP]", receipt_body)
    else:
        db.add_outbox(payment.get("recipient_email") or "(no recipient)",
                      subject + "  [outbox - no SMTP configured]", receipt_body)
