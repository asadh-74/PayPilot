# PayPilot — invoice and manual payment management

A private FastAPI application for invoices, customer bank-transfer references, administrator review, receipts, collections and message drafts. The editorial light interface uses warm off-white surfaces, an emerald accent, responsive navigation and accessible dialogs.

**PayPilot does not process payments, connect to a bank, or independently verify transfers.** A submitted reference leaves the invoice unpaid until the administrator checks the bank statement and explicitly confirms it. No PayPal configuration is required in manual mode. No emails are sent.

## Workflow

1. Sign in with your privately configured administrator password.
2. Save your business name and receiving-bank instructions in Settings.
3. Create an invoice with customer details, a currency, exact line-item totals, issue/due dates and optional notes.
4. Generate a private customer link. It expires after 24 hours; generating a replacement invalidates the previous link. Links can be revoked.
5. The customer transfers through their own bank and submits the bank reference on the invoice page.
6. Review the submitted reference. Check the bank statement independently and confirm the amount, currency and reference. Reject unmatched references to allow correction.
7. A confirmed invoice becomes paid. Open its receipt or printable customer page. Automation drafts remain unsent; downloadable drafts are available for review.

Overview shows invoice counts, outstanding balances and collection rates **separately per currency**, plus invoice activity and follow-up priorities. Search, status filters, collections aging, automation switches and activity timelines use server records. A new administrator workspace starts empty. Legacy simulated or sandbox invoices retain their source labels.

## Local setup

Python 3.12 is recommended. From the repository root:

```sh
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell instead:
# .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `paypilot-ai/paypilot-ai/.env`. Set a unique `ADMIN_PASSWORD` of at least 16 characters. For an isolated local run, use:

```ini
DATABASE_URL=sqlite:///./paypilot.db
REQUIRE_MYSQL=false
COOKIE_SECURE=false
PAYMENT_MODE=manual
DEMO_ENABLED=false
AUTOMATION_ENABLED=false
```

Then:

```sh
cd paypilot-ai/paypilot-ai
python run.py
```

Open **http://localhost:8000**. The connected app must be served by FastAPI; opening `index.html` directly is unsupported. The static HTML file delivered earlier is a separate design preview.

## Existing Aiven MySQL / Render configuration

The existing verified-TLS SQLAlchemy connection remains intact. Credentials stay server-side. For the existing hosted service retain `DATABASE_URL`, `MYSQL_SSL_CA`, `ADMIN_PASSWORD` and `APP_BASE_URL`; use `REQUIRE_MYSQL=true`, `COOKIE_SECURE=true`, `PAYMENT_MODE=manual`, and `DEMO_ENABLED=false`. Never copy credentials into JavaScript or screenshots.

`render.yaml` remains unchanged in this local integration. Its older demo setting must be overridden to false when approving a release. No Render resources, environment variables, Aiven records or GitHub branches were modified by preparing this change.

The deployment command remains:

```sh
cd paypilot-ai/paypilot-ai && uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
```

The backend health check is `/health`. Existing MySQL startup validates certificate and hostname; it does not silently fall back to SQLite. Hosted database readiness still requires a separate approved release check.

## Storage and compatibility

Existing `pp_payments`, item, reference, share-link and workspace-preference records remain supported. This integration adds only **`pp_invoice_metadata`** for customer names, customer notes and issue dates. SQLAlchemy creates the additive table at startup; no existing payment columns are altered. Back up production before any approved release. Rolling back the application can leave this additive table in place.

New API fields `customer_name`, `notes`, `issue_date` and `due_date` are optional, preserving older invoice requests. `/api/workspace/snapshot` is administrator-only and scopes invoice metadata, items, references, drafts and events to the authenticated workspace. HttpOnly session cookies and request verification headers protect mutations. Browser JavaScript uses external same-origin assets under a strict `script-src 'self'` policy; inline style attributes are permitted for layout. Private records and passwords are not persisted in localStorage.

## Automations and limits

Receipt and overdue-reminder switches are persisted. Manual and scheduled runs use the same deduplication; unpaid invoices awaiting reference review pause reminders. A disabled receipt rule can be caught up by running automation after enabling it or explicitly opening a paid invoice's receipt. Receipt creation is a local business record, not proof supplied by a bank.

The scheduler can run for the administrator workspace while signed out, **only while the server is awake**. Free-host sleep pauses it. There is no guaranteed always-on delivery, bank reconciliation feed, live checkout, FX conversion, SMTP integration, password recovery or team management. The single administrator password is configured server-side. Existing sandbox/demo endpoints are retained for compatibility but are not exposed by this private interface; disable demo creation through configuration.

## Validation

```sh
pip install -r paypilot-ai/paypilot-ai/requirements-dev.txt
cd paypilot-ai/paypilot-ai
python -m pytest -q
node --check app/static/workspace.js
```

Tests cover sessions, workspace isolation, exact decimal totals, date validation, customer-page escaping, expiring/revocable links, reference submission/rejection, explicit confirmation, receipt/draft deduplication and duplicate-reference safeguards. `tests/workspace_ui.cjs` adds a DOM integration test using `jsdom`: run it against an isolated local server at `http://127.0.0.1:8765` configured with the test-only password used in `tests/test_app.py`. It checks real UI event handlers and API calls; it is not a visual browser test. Never run it against production.

`TEST_MYSQL_URL`, if used, must point to a **disposable test database**: tests drop namespaced tables. Never point tests at Aiven production. This local release was validated with isolated SQLite and DOM execution; live Aiven/MySQL and visual desktop/mobile verification remain release checks.
