# PayPilot — payments, with less chasing

A hackathon payment operations app by **Asad Hussain**. Describe an invoice in plain English, review its details, collect a **PayPal Sandbox** payment, and follow the receipt through a traceable automation workflow.

**No real funds move. Public demos are isolated. No external emails are sent.**

## What works

- Responsive dashboard, searchable invoice ledger, CSV export, daily activity chart.
- Isolated visitor demos with fictional sample customers and simulated captures.
- Administrator workspace protected by an HttpOnly session cookie.
- Natural-language draft extraction; review required before creating an invoice.
- Exact decimal amounts, supported currency validation, totals grouped by currency.
- PayPal Sandbox order creation, buyer approval, server-side capture reconciliation.
- Verified PayPal webhooks, event replay detection, request idempotency.
- Receipt automation on capture, manual overdue reminder batches, deduplicated outbox.
- Automation switches, activity log, MySQL with verified TLS, Render deployment config.
- SQLite local/demo fallback, explicitly identified as ephemeral when hosted.

## Run locally

Python 3.12 recommended. From the repository root:

```sh
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example paypilot-ai/paypilot-ai/.env
cd paypilot-ai/paypilot-ai
python run.py
```

Open http://localhost:8000 and select **Launch interactive demo**. No API keys are needed. Demo parsing is always offline; configured AI providers are used only by the administrator's parsing endpoint. Public demo sessions expire after eight hours.

## Aiven MySQL + Render

The Blueprint in `render.yaml` requires persistent MySQL. A temporary demo-only Render deployment may explicitly set `REQUIRE_MYSQL=false` and use SQLite while the Aiven account is connected; that mode is **not persistent** and the UI discloses it.

1. In your existing Aiven MySQL service, create a dedicated `paypilot` database. Prefer a user limited to that database. Do not use another app's tables.
2. Copy the MySQL connection URI and project CA certificate from Aiven's connection information.
3. Set Render environment variables privately:
   - `DATABASE_URL=mysql+pymysql://USER:URL_ENCODED_PASSWORD@HOST:PORT/paypilot`
   - `MYSQL_SSL_CA`: the full PEM CA certificate, with real newlines or literal `\n`.
   - `REQUIRE_MYSQL=true`
   - `COOKIE_SECURE=true`
   - `ADMIN_PASSWORD`: a unique secret of at least 16 characters.
   - `APP_BASE_URL`: the deployed HTTPS origin.
   - `DEMO_ENABLED=true` for hackathon visitors, or `false` for admin-only use.
4. Deploy the repository's `main` branch on Render's free Python web service:
   - Build: `pip install -r requirements.txt`
   - Start: `cd paypilot-ai/paypilot-ai && uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
   - Health check: `/health`
5. Verify `/health` reports `database: mysql` and the UI says **MySQL connected**.

MySQL certificate and hostname verification remain enabled. Startup fails on a bad database connection; it does not silently switch a MySQL deployment to SQLite. Tables are prefixed `pp_`; SQLAlchemy creates the initial schema without modifying unrelated tables. Future schema changes require versioned migrations before upgrading existing data.

## PayPal Sandbox

Set `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, and `PAYPAL_WEBHOOK_ID` using **sandbox** credentials. Live API endpoints are rejected. Add `<APP_BASE_URL>/webhooks/paypal` in the PayPal developer dashboard and subscribe to `PAYMENT.CAPTURE.COMPLETED`.

Administrator flow: create invoice → open PayPal approval → approve with a sandbox buyer → return → click **Sync**. Capture status and amount/currency are verified before recording payment. Verified capture webhooks also reconcile payment. The email field labels the customer; it does **not** redirect funds or perform a payout. All orders belong to the configured sandbox merchant.

If checkout creation fails, retry the unchanged form: its idempotency key and persisted invoice ID prevent a second invoice. If credentials were missing, configure them and retry using the original request key; failed pending requests are retained for diagnosis.

Reference APIs: [PayPal webhook verification](https://developer.paypal.com/api/rest/webhooks/rest/), [PayPal request idempotency](https://developer.paypal.com/api/make-api-requests), [Aiven Python connection](https://aiven.io/docs/products/mysql/howto/connect-with-python).

## Automations

| Rule | Trigger | Result | Duplicate protection |
| --- | --- | --- | --- |
| Instant receipt | Confirmed/simulated capture | Receipt and outbox preview | One per invoice |
| Overdue follow-up | Run automation button | Reminder for overdue unpaid invoice | One per invoice per UTC date |
| Receipt catch-up | Run automation button | Missing receipts when enabled | One per invoice |

Outbox records say `DEMO_OUTBOX`; none are represented as sent. No SMTP, Gmail, or other external notification is enabled. Reminder scheduling and external delivery are intentionally not claimed as implemented. You can demonstrate automation safely without messaging real people.

## Tests

```sh
pip install -r paypilot-ai/paypilot-ai/requirements-dev.txt
cd paypilot-ai/paypilot-ai
python -m pytest -q
```

CI tests against SQLite and an isolated MySQL 8.4 container. `TEST_MYSQL_URL` is for a **disposable test database only**: tests drop `pp_` tables on that connection. Never point it at Aiven or production data.

Tests cover authentication, request header protection, workspace isolation, amount/currency validation, request replay, capture/receipt deduplication, webhook verification and mismatches, currency analytics, reminder rules, CSV injection protection, parser ambiguity, and health endpoints.

## Hackathon scope and limits

This is a sandbox portfolio app, not a production financial service. There is one administrator account, process-local request throttling, and no password recovery or team administration. Free hosting can sleep; wake the app before presenting. Demo records are fictional, sessions are isolated, and simulated captures are clearly distinguished from verified PayPal sandbox captures. No real billing, payouts, refunds, subscriptions, or real-time FX conversion is implemented. Uploaded files and document OCR are not implemented.

Optional AI keys stay server-side. OpenAI/Anthropic/Ollama parsing falls back to conservative local parsing if unavailable; review all extracted values. Receipt messages and analytics are deterministic, not claimed as generated by an LLM. Data export is scoped to the signed-in workspace.

See [the demo script](paypilot-ai/paypilot-ai/DEMO_VIDEO_SCRIPT.md) and [submission notes](paypilot-ai/paypilot-ai/SUBMISSION.md).
