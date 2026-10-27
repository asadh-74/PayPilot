# PayPilot — invoice and manual payment management

A private FastAPI application for invoices, customer bank-transfer references, administrator review, receipts, collections and message drafts. The editorial light interface uses warm off-white surfaces, an emerald accent, responsive navigation and accessible dialogs.

**PayPilot does not process payments, connect to a bank, or independently verify transfers.** A submitted reference leaves the invoice unpaid until the administrator checks the bank statement and explicitly confirms it. No PayPal configuration is required in manual mode. Emails remain drafts until an administrator reviews the recipient and content and explicitly sends them through a configured server-side provider.

## Workflow

1. Sign in with your privately configured administrator password.
2. Save your business name and receiving-bank instructions in Settings.
3. Write an invoice sentence to fill customer details, currency, line items and due date, or fill the form manually. Review exact totals, then create the invoice.
4. Choose **Create & prepare email**, review the recipient and message, then explicitly send; or generate a private customer link. It expires after 24 hours; generating a replacement invalidates the previous link. Links can be revoked.
5. The customer transfers through their own bank and submits the bank reference on the invoice page.
6. Review the submitted reference. Check the bank statement independently and confirm the amount, currency and reference. Reject unmatched references to allow correction.
7. A confirmed invoice becomes paid. Open its receipt or printable customer page. Automation drafts remain unsent until explicitly reviewed and sent; downloadable drafts are also available.

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

Existing `pp_payments`, item, reference, share-link and workspace-preference records remain supported. This integration adds **`pp_invoice_metadata`** for customer names, customer notes and issue dates, and **`pp_email_deliveries`** for delivery attempts and acceptance states. SQLAlchemy creates the additive table at startup; legacy MySQL timestamp columns are widened from FLOAT to DOUBLE for expiry precision. No records are deleted. Back up production before any approved release. Rolling back the application can leave this additive table in place.

New API fields `customer_name`, `notes`, `issue_date` and `due_date` are optional, preserving older invoice requests. `/api/workspace/snapshot` is administrator-only and scopes invoice metadata, items, references, drafts and events to the authenticated workspace. HttpOnly session cookies and request verification headers protect mutations. Browser JavaScript uses external same-origin assets under a strict `script-src 'self'` policy; inline style attributes are permitted for layout. Private records and passwords are not persisted in localStorage.

## Sentence invoices and email

Example (fictional preview data):

> Invoice Cedar Studio at billing@customer.example for 2 logo designs at PKR 5000 each; 3 banners at PKR 1000 each, due in 14 days.

The built-in deterministic parser fills a reviewable PKR 13,000 invoice. It makes no external AI request, saves nothing and sends nothing. Use explicit numeric prices, one supported currency, semicolons between quantity items, and `due in N days` or `due YYYY-MM-DD`. Mixed currencies, ambiguous dates, taxes and discounts require correction rather than silent inference. Review extracted details before creating. Reserved illustrative email addresses are blocked from sending.

Configure email privately on the server:

```ini
EMAIL_PROVIDER=resend
RESEND_API_KEY=<private provider API key>
EMAIL_FROM=<provider-approved sender>
APP_BASE_URL=https://YOUR-SERVICE.onrender.com
```

Resend uses HTTPS. Render Free blocks outbound SMTP ports 25, 465 and 587 ([Render documentation](https://render.com/docs/free)); do not use SMTP on that plan. Other compatible hosting can use `EMAIL_PROVIDER=smtp`, `SMTP_HOST`, `SMTP_PORT=587` (STARTTLS) or `465` (TLS), `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM`. No provider credentials enter frontend state. Provider setup, sender verification and any charges are separate from the app.

Invoice emails contain a private 24-hour customer link and manual-transfer instructions. Rebuilding an unsent invoice email replaces previous customer links. Expired/revoked links cannot be sent. Receipt/reminder switches only prepare drafts. Each send requires a recipient/content review checkbox. Acceptance is recorded separately from inbox delivery; no inbox delivery claim is made. Provider acceptance and pending/uncertain attempts block duplicate sends. A timeout requires checking provider records and explicitly enabling a retry before a separate send. Definite provider rejections remain failed drafts for correction. Production sending has not been tested with real credentials.

## Automations and limits

Receipt and overdue-reminder switches are persisted. Manual and scheduled runs use the same deduplication; unpaid invoices awaiting reference review pause reminders. A disabled receipt rule can be caught up by running automation after enabling it or explicitly opening a paid invoice's receipt. Receipt creation is a local business record, not proof supplied by a bank.

The scheduler can run for the administrator workspace while signed out, **only while the server is awake**. Free-host sleep pauses it. There is no guaranteed always-on delivery, bank reconciliation feed, live checkout, FX conversion, inbox-delivery webhooks, password recovery or team management. The single administrator password is configured server-side. Existing sandbox/demo endpoints are retained for compatibility but are not exposed by this private interface; disable demo creation through configuration.

## Validation

```sh
pip install -r paypilot-ai/paypilot-ai/requirements-dev.txt
cd paypilot-ai/paypilot-ai
python -m pytest -q
node --check app/static/workspace.js
```

Tests cover sessions, workspace isolation, exact decimal totals, date validation, customer-page escaping, expiring/revocable links, reference submission/rejection, explicit confirmation, sentence extraction, HTTPS email payload/idempotency, review gates, rejected/uncertain email states, expired email links, receipt/draft deduplication and duplicate-reference safeguards. `tests/workspace_ui.cjs` adds a DOM integration test using `jsdom`: run it against an isolated local server at `http://127.0.0.1:8765` configured with the test-only password used in `tests/test_app.py`. It checks real UI event handlers and API calls; it is not a visual browser test. Never run it against production.

`TEST_MYSQL_URL`, if used, must point to a **disposable test database**: tests drop namespaced tables. Never point tests at Aiven production. This local release was validated with isolated SQLite and DOM execution; live Aiven/MySQL and visual desktop/mobile verification remain release checks.

## Billing upgrade (3.1)

- Private downloadable A4 invoice PDFs with stable workspace invoice numbers.
- New invoices preserve seller billing details, terms, payment instructions, customer address, tax references and purchase orders as an immutable snapshot. Older invoices are explicitly labeled legacy.
- Manual invoice tracking supports USD, EUR, GBP, CAD, AUD, SGD, PKR, AED and SAR. Currency totals remain separate; no FX conversion is applied.
- Receivables dashboard and CSV register separate paid, not-yet-due and overdue balances by currency. Demo/sandbox invoices are excluded.
- Customer PDF access uses the same expiring, revocable share capability as the invoice page. Administrator exports remain workspace-scoped.

These are portfolio/business-workflow features, not country-specific tax compliance or bank settlement verification. PDF fonts support Latin text; comprehensive multilingual/RTL typesetting is not implemented. No new paid service is required.

Validation: 55 isolated SQLite backend tests passed, including PDF extraction, immutable billing snapshots, access isolation, revoked shares, sequential numbering/idempotency and currency-separated aging. Never point destructive test fixtures at the production database.

## Business workflows (3.2)

Customers can be saved and reused on new invoices. Quotes can be reviewed, cancelled or converted with a stable idempotency key. Monthly templates prepare invoice drafts through the existing automation loop (while enabled and the service is awake) or the **Prepare due drafts** button. Each run prepares at most one due period per template; month-end dates preserve the original billing-day anchor. Review and issue drafts explicitly; no customer email is sent automatically.

The **Payment ledger** records verified installments with exact decimal amounts, workspace-wide unique bank references, duplicate-request handling and overpayment rejection. Reports, PDFs, customer pages and collection balances reflect the remaining amount. Prior reminder drafts become stale after an installment; stale sends are blocked. New reminders use balance-specific deduplication. Older full-payment records remain supported.

Storage changes are additive: `pp_customers`, `pp_installments`, and `pp_business_drafts`. Existing invoice and payment records are preserved. No new paid infrastructure is introduced.

Validation: 61 SQLite backend tests, including customer isolation, quote retries/cancellation, recurring preparation, partial-payment totals, overpayment rejection and stale reminders. See [portfolio demonstration guide](docs/PORTFOLIO_DEMO.md) and [fictional example data](docs/demo-data.json). Tests use disposable local databases, not the hosted MySQL database.
