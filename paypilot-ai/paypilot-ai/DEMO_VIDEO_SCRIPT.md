# PayPilot: three-minute hackathon demo

**0:00 — Problem.** Freelancers lose time creating invoices, tracking unpaid work, and preparing follow-ups. PayPilot puts those tasks in one workspace.

**0:20 — One-click demo.** Launch the interactive demo. Explain that its fictional customers and simulated payments are private to this session. Point out the storage badge accurately.

**0:40 — Natural-language invoice.** Create invoice → type `Charge $250 USD for a logo design to maya@example.com` → fill details. Show amount, currency, email and due date. Review, then confirm.

**1:10 — Payment lifecycle.** Click Simulate capture. Explain that no PayPal request or real transfer is made in this mode. Show Captured, then open the receipt.

**1:35 — Automation.** Open Automations and run the overdue batch. Open Outbox to show the prepared reminders. Run the batch again: zero new messages demonstrates daily deduplication.

**2:00 — Visibility.** Open Activity log to trace invoice creation, capture, and receipt creation. Show search, currency-specific totals, and CSV export.

**2:30 — Architecture.** Explain FastAPI + SQLAlchemy, MySQL on Aiven with verified TLS, Render hosting, isolated sessions, request idempotency and verified PayPal Sandbox webhooks. Only claim Aiven is connected if the live badge/health endpoint reports MySQL.

**2:50 — Close.** “From one sentence to an invoice, a captured payment, and a traceable receipt — with less chasing.”

Optional second recording: use the administrator workspace with configured PayPal Sandbox credentials and a sandbox buyer account to demonstrate real sandbox approval and Sync. Never show credentials, personal mailbox data, or live accounts in the video.
