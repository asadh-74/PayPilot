# PayPilot — PayPal AI Hackathon Submission Readiness

> Status: **not ready to submit**. This document distinguishes implemented code from verified behavior. Do not assert PayPal checkout or LLM extraction works until the acceptance checks pass.

## Project
PayPilot — invoice drafting, manual transfer review, optional PayPal Sandbox checkout, controlled receipts and reminder drafts.

- App: https://paypilot-6ca4.onrender.com/
- Command Center: https://paypilot-6ca4.onrender.com/static/command-center.html
- No-password design-only preview: https://paypilot-6ca4.onrender.com/static/preview.html
- Repository: https://github.com/asadh-74/PayPilot

## Current limitations
- The production README documents `PAYMENT_MODE=manual`. Manual transfers require an administrator to check the bank statement; they are **not PayPal transactions**.
- `app/paypal_client.py` implements PayPal Sandbox OAuth, Orders v2, order capture and webhook verification. Live sandbox flow is **not proven** merely by the presence of code. `/api/config` exposes whether `sandbox_ready` is true, but not whether a successful checkout occurred.
- `app/ai_service.py` supports OpenAI/Anthropic/Ollama and a deterministic fallback. However, `/api/invoice-drafts/parse` currently uses `invoice_parser.parse` rather than calling a model. It is **not accurate** to demonstrate that endpoint as LLM-powered.
- No actual PayPal webhook replay/production delivery confirmation, email inbox delivery, compliance certification or fraud classifier is proven.
- The authenticated workspace contains user records; demos must use disposable test records and sanitized screenshots.

## Reproducible setup (isolated)
1. Clone repository and install Python 3.12.
2. `pip install -r paypilot-ai/paypilot-ai/requirements-dev.txt`
3. Create `paypilot-ai/paypilot-ai/.env` **locally**, not in Git. Set `DATABASE_URL=sqlite:///./paypilot-test.db`, `REQUIRE_MYSQL=false`, `COOKIE_SECURE=false`, `PAYMENT_MODE=manual`, `DEMO_ENABLED=false`, `AUTOMATION_ENABLED=false`, and a randomly generated 16+ character `ADMIN_PASSWORD`.
4. `cd paypilot-ai/paypilot-ai && python -m pytest -q`
5. `python run.py`; open `http://127.0.0.1:8000`.
6. For MySQL test coverage, run GitHub Actions CI with disposable MySQL 8.4. **Never** set `TEST_MYSQL_URL` to Aiven production because the tests drop tables.

## Acceptance criteria — verify in disposable sandbox
### PayPal
- In a separate test environment only, set server-side `PAYMENT_MODE=sandbox`, HTTPS `APP_BASE_URL`, `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, and `PAYPAL_WEBHOOK_ID`.
- Create a **USD** test invoice (not PKR: PayPal currency support differs); verify a valid PayPal Sandbox order and approval URL are created.
- Complete the checkout with a Sandbox buyer account. Verify a matching order ID, amount, currency, merchant account and captured status before marking paid.
- Send a correctly signed webhook and verify signature succeeds. Reject unsigned/forged, mismatched and replayed events.
- Confirm no duplicated receipt/settlement on webhook replay or status refresh. Inspect audit events and invoice status.
- Preserve the main Render deployment and production database untouched during this run.

### AI
- Integrate a real AI model into a **new validated draft path**, keep deterministic fallback explicitly labeled, and require human confirmation before persistence or sending.
- Test PKR and USD, item quantities × unit prices, email addresses, due dates, ambiguous price, mixed currencies and prompt injection.
- Ensure output is validated by Pydantic and Decimal, not trusted model text. Never return or log API keys.

### End to end
- Login; create invoice; preview and correct totals; issue link; have a sandbox customer report a reference; reject wrong reference; approve only with independent confirmation; create receipt draft; trigger reminder preparation; inspect audit log; logout.
- Test email dispatch only to a controlled test recipient after explicitly reviewing message; verify provider acceptance separately from actual inbox delivery.
- Check desktop, tablet and mobile, keyboard-only navigation, contrast and chart text alternatives (WCAG 2.2 AA **target**, not certification).

## Short public demo video script (target 2:30–2:50)
**0:00–0:20 — Problem**: Small businesses waste time converting messages into invoices, chasing unpaid bills and checking payment references.
**0:20–0:45 — Command Center**: Show actual dashboard with clearly labeled test records and currency-separated balances.
**0:45–1:15 — Invoice Studio**: Enter natural-language request, show parsed items, edit price/due date, verify total before save. Name the **actual** AI provider only after testing the model-backed path.
**1:15–1:55 — PayPal Sandbox**: Show order creation, test-buyer approval, captured transaction and corresponding invoice status. Only record this section **after successful validation**.
**1:55–2:20 — Review + Automations**: Demonstrate reference verification and controlled receipt/reminder drafts.
**2:20–2:40 — Technical stack**: FastAPI, MySQL, provider-backed AI (if verified), PayPal Sandbox (if verified), security controls and GitHub source.
**2:40–2:50 — Closing**: End on the Command Center and one-sentence value proposition.

Do not include real customer addresses, emails, tokens, credentials or actual bank details in recordings.

## Submission checklist
- [ ] Official rules, participation/eligibility and submission category rechecked
- [ ] PayPal Sandbox end-to-end capture verified with a test buyer
- [ ] AI-backed invoice creation demonstrated, not just regex
- [ ] Demo URL works for judges or reproducible test credentials supplied securely
- [ ] LICENSE and clean public source validated (including historical secrets)
- [ ] README accurately describes **current deployed** mode and AI provider
- [ ] Public YouTube demo video recorded and uploaded (<3 minutes, if required by current rules)
- [ ] Screenshots show fictional data only
- [ ] Submitted through Devpost only after project-owner approval
