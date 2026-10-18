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
- Receipt automation on capture, scheduled and manual overdue reminder batches, deduplicated outbox.
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
| Overdue follow-up | Scheduled runner or Run automation button | Reminder for overdue unpaid invoice | One per invoice per UTC date |
| Receipt catch-up | Run automation button | Missing receipts when enabled | One per invoice |

Outbox records say `DEMO_OUTBOX`; none are represented as sent. No SMTP, Gmail, or other external notification is enabled. The in-process scheduler checks every five minutes while the server is awake and handles workspaces with an unexpired session. Free Render instances can sleep, so this is not an always-on scheduling guarantee. External delivery is not implemented. You can demonstrate automation safely without messaging real people.

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


## Collections and scheduled automation (v2.1)

The Collections view groups receivables into not due, 1–7, 8–30, and 31+ days overdue, with a separate next-seven-days subtotal. Balances remain separated by currency. Follow-up priorities are ordered by due date with explicit reasons; they are not AI risk scores or forecasts of actual receipts.

The background runner defaults to enabled (`AUTOMATION_ENABLED=true`) with `AUTOMATION_INTERVAL_SECONDS=300` (minimum 60). It honors saved receipt/reminder switches, processes workspaces with an unexpired session, and uses the same transactional daily deduplication as manual runs. Graceful shutdown stops the runner. `/api/automations/status` shows configuration and the latest batch that created messages. No external messages are sent, and no paid worker is provisioned. Deploy with one Uvicorn worker as configured; free-host sleep pauses the scheduler. Use the manual button for a predictable live demonstration.

## Version 2.2 — portfolio workflow

- Optional line items with server-validated exact totals.
- Invoice detail timelines and recovered checkout actions.
- Expiring, revocable customer invoice links; printable invoices/receipts and browser Save as PDF.
- Reviewed reminder drafts and completed-run visibility even when no messages are created.
- Mobile sign-out and expired anonymous-workspace cleanup.

[Portfolio description](portfolio/UPWORK_PROJECT.md) · [90-second recording script](portfolio/DEMO_RECORDING.md) · [Release and setup notes](portfolio/RELEASE_NOTES.md).

The hosted demo's actual database and payment readiness are shown by its configuration and UI; repository support for MySQL does not imply a configured Aiven deployment.
