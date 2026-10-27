# PayPilot — client demonstration

## Upwork project title
Invoice & Receivables Automation — FastAPI, MySQL & Python

## Description
PayPilot helps small businesses manage customers, prepare quotes, issue invoices, record verified bank-transfer installments, and monitor outstanding balances. Monthly templates prepare reviewable invoice drafts. The workspace includes nine currencies, downloadable PDF invoices, aging reports and CSV exports. Duplicate transfer references, overpayments and duplicate quote conversions are blocked. Customer emails require explicit review before sending.

Built with Python, FastAPI, SQLAlchemy, MySQL and responsive HTML/CSS/JavaScript. Payment tracking is manual; the app does not process bank transfers or independently verify settlement.

## Three-minute walkthrough
1. **0:00–0:20 — Problem:** “Small businesses lose time copying billing details and chasing balances. PayPilot brings those tasks into one workspace.” Show the Overview.
2. **0:20–0:45 — Customer reuse:** Add fictional Cedar Studio with `billing@cedar.example`, then select it in New invoice. Show address autofill.
3. **0:45–1:10 — Quote:** Add two consulting sessions at USD 100 each. Save as quote, review it, then issue the invoice. Explain that repeated clicks do not create duplicate invoices.
4. **1:10–1:40 — Payment ledger:** In a disposable local demo only, record a fictional USD 50 installment with reference `DEMO-TRANSFER-001`. Show USD 150 remaining and download the PDF. Never pretend this fictional record is a bank transaction.
5. **1:40–2:00 — Reports:** Show outstanding amounts and aging, separated by currency. Export the CSV.
6. **2:00–2:25 — Monthly work:** Save a monthly support template, prepare its due draft, and review before issuing. Explain that scheduled preparation runs only while the server is awake and automation is enabled.
7. **2:25–2:45 — Reliability:** Attempt the same transfer again to show deduplication; demonstrate an overpayment rejection. Explain stale reminders are blocked after balance changes.
8. **2:45–3:00 — Close:** Show the mobile navigation and summarize the workflow. No real email or payment is needed for this demonstration.

## Screenshot checklist
Capture actual app screens using fictional data: Overview, reusable customer directory, quote review, partial-payment ledger, receivables by currency, and an invoice PDF. Exclude credentials, private bank details, real customer information and expiring access tokens. Screenshots are not bundled with this document.

## Demo data
Use `docs/demo-data.json` as a manual entry guide. It is fictional and is not automatically imported into the production account.

## Boundaries
- Bank transfers are recorded after human verification; no bank API settlement integration.
- Quotes are internal reviewable drafts; customer quote acceptance and signed contracts are not implemented.
- Recurring templates create drafts, not automatically sent invoices; free hosting can sleep.
- No tax engine, FX conversion, refunds or accounting reconciliation certification.
- Mobile CSS and DOM workflows are tested; device-specific visual testing remains useful.
