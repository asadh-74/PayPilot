# PayPilot — payments, with less chasing

**Builder:** Asad Hussain

**Problem:** Small service businesses spend time translating work into invoices, checking payments, and preparing routine receipts and reminders.

**Solution:** A payment operations dashboard combining natural-language invoice drafts, a PayPal Sandbox checkout lifecycle, and transparent receipt/reminder workflows.

**Demo:** Isolated, no-key demo workspaces with fictional data and simulated captures. Administrator mode integrates PayPal Sandbox credentials. Simulated activity is clearly labelled.

**Stack:** Python/FastAPI, SQLAlchemy, MySQL/PyMySQL, vanilla JavaScript/CSS, Render. Optional OpenAI/Anthropic/Ollama parsing; deterministic offline fallback.

**Technical highlights:** Decimal money, currency-separated totals, tenant-scoped queries, HttpOnly sessions, request idempotency, verified webhooks, deduplicated outbox and activity trace.

**Honest scope:** Sandbox only. Outbox previews are not sent emails. Reminders run on demand; receipt automation runs on capture. Production payment compliance, team roles, automatic recurring billing, and real payouts are outside scope. Verify current live MySQL connection before claiming database deployment is complete.
