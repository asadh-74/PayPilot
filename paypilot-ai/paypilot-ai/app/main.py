"""PayPilot AI - FastAPI application.

Run:  uvicorn app.main:app --reload --port 8000
"""
import os
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import ai_service
import db
import emailer
from paypal_client import PayPalClient

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

app = FastAPI(title="PayPilot AI", version="1.0.0")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
paypal = PayPalClient()
db.init_db()


# ------------------------------------------------------------- request models
class CreatePaymentRequest(BaseModel):
    prompt: str | None = None          # natural-language, AI-parsed
    amount: float | None = None        # or explicit fields
    currency: str = "USD"
    description: str | None = None
    recipient_email: str | None = None


# ------------------------------------------------------------------- frontend
@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html")) as f:
        return f.read()


@app.get("/return")
def paypal_return(order_id: str | None = None):
    """Buyer is redirected here after approving in the PayPal sandbox popup."""
    return RedirectResponse(f"/?approved={order_id or ''}")


@app.get("/cancel")
def paypal_cancel():
    return RedirectResponse("/?cancelled=1")


# -------------------------------------------------------------------- payments
@app.post("/api/payments")
def create_payment(body: CreatePaymentRequest, request: Request):
    base = os.getenv("APP_BASE_URL") or str(request.base_url).rstrip("/")

    if body.prompt:
        try:
            parsed = ai_service.parse_payment_prompt(body.prompt)
        except ValueError as e:
            raise HTTPException(422, str(e))
    else:
        if not body.amount or body.amount <= 0:
            raise HTTPException(422, "Provide either a prompt or a positive amount.")
        parsed = {"amount": round(body.amount, 2),
                  "currency": (body.currency or "USD").upper(),
                  "description": body.description or "Payment",
                  "recipient_email": body.recipient_email}

    try:
        order = paypal.create_order(
            amount=parsed["amount"], currency=parsed["currency"],
            description=parsed["description"], reference_id=db.new_id(),
            return_url=f"{base}/return", cancel_url=f"{base}/cancel")
    except RuntimeError as e:   # missing creds -> clear setup hint
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"PayPal API error: {e}")

    approve = paypal.approve_link(order)
    pid = db.insert_payment({
        "paypal_order_id": order["id"], "amount": parsed["amount"],
        "currency": parsed["currency"], "description": parsed["description"],
        "recipient_email": parsed["recipient_email"],
        "status": order.get("status", "CREATED"),
        "approve_link": approve, "raw": order})

    return {"id": pid, "paypal_order_id": order["id"], "approve_link": approve,
            **{k: parsed[k] for k in ("amount", "currency", "description", "recipient_email")}}


@app.get("/api/payments")
def list_payments():
    rows = db.list_payments()
    for r in rows:
        r["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["created_at"]))
    return rows


@app.post("/api/payments/{pid}/refresh")
def refresh_payment(pid: str):
    """Sync one payment with PayPal; capture if the buyer already approved."""
    p = db.get_payment(pid)
    if not p:
        raise HTTPException(404, "payment not found")
    try:
        order = paypal.get_order(p["paypal_order_id"])
    except Exception as e:
        raise HTTPException(502, f"PayPal API error: {e}")

    status = order.get("status", p["status"])
    fields: dict = {"status": status}
    payer = (((order.get("payer") or {}).get("email_address")))
    if payer:
        fields["payer_email"] = payer
    if status == "APPROVED":                      # buyer approved -> capture now
        try:
            capture = paypal.capture_order(p["paypal_order_id"])
            status = capture.get("status", "COMPLETED")
            fields["status"] = "CAPTURED" if status == "COMPLETED" else status
            fields["raw_json"] = str(capture)
        except Exception as e:
            raise HTTPException(502, f"Capture failed: {e}")
    db.update_payment(pid, **fields)
    return db.get_payment(pid)


@app.get("/api/payments/{pid}/receipt")
def get_receipt(pid: str, regenerate: bool = False):
    p = db.get_payment(pid)
    if not p:
        raise HTTPException(404, "payment not found")
    if regenerate or not p.get("receipt_text"):
        body = ai_service.generate_receipt(p)
        db.update_payment(pid, receipt_text=body)
        return {"receipt": body}
    return {"receipt": p["receipt_text"]}


# -------------------------------------------------------------------- insights
@app.get("/api/insights")
def insights():
    return {"provider": ai_service.active_provider(),
            "insights": ai_service.generate_insights(db.list_payments(100))}


@app.get("/api/config")
def config():
    return {"ai_provider": ai_service.active_provider(),
            "paypal_ready": bool(paypal.client_id and paypal.client_secret),
            "paypal_base": paypal.base}


# ------------------------------------------------------------- paypal webhooks
@app.post("/webhooks/paypal")
async def paypal_webhook(request: Request):
    """Receive PayPal sandbox webhooks (e.g. PAYMENT.CAPTURE.COMPLETED).

    Configure in the PayPal Developer Dashboard -> App -> Webhooks,
    URL: <APP_BASE_URL>/webhooks/paypal  (use ngrok/cloudflared locally).
    """
    payload = await request.json()
    event_type = payload.get("event_type", "UNKNOWN")
    resource = payload.get("resource", {})
    order_id = ((resource.get("supplementary_data") or {})
                .get("related_ids", {}).get("order_id"))

    db.add_webhook_event(event_type, order_id, payload)

    if event_type == "PAYMENT.CAPTURE.COMPLETED" and order_id:
        p = db.find_payment_by_order(order_id)
        if p and p["status"] != "CAPTURED":
            payer = (resource.get("payer") or {}).get("email_address")
            db.update_payment(p["id"], status="CAPTURED", payer_email=payer)
            fresh = db.get_payment(p["id"])
            receipt = ai_service.generate_receipt(fresh)
            db.update_payment(p["id"], receipt_text=receipt)
            emailer.send_receipt(fresh, receipt)
    return JSONResponse({"received": True}, status=200)


@app.get("/api/webhooks")
def webhook_log():
    rows = db.list_webhook_events()
    for r in rows:
        r["received_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["received_at"]))
    return rows


# --------------------------------------------------------------------- outbox
@app.get("/api/outbox")
def outbox():
    rows = db.list_outbox()
    for r in rows:
        r["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["created_at"]))
    return rows
