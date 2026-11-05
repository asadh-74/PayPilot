# PayPilot — 75-second portfolio demo plan

## Current access and truth

Checked 5 November 2026: Render health responded with MySQL and application version 3.2.0. The hosted root requires the administrator password and public demo mode is disabled. The public preview at `/static/preview.html` is design-only. The connected live configuration is manual payment tracking, no email provider, no PayPal Sandbox credentials, and an offline deterministic sentence parser.

Use the repository's isolated local setup and fictional data for a real interaction recording. Do not sign in to the hosted administrator workspace for a public recording, expose the password, or enter genuine customer/bank details. The built-in demo data is an example, not automatically imported into production.

## 75-second recording script

- **0–10 sec — Problem:** “PayPilot organizes customer billing, invoice follow-up and payment records in one reviewable workspace.”
- **10–25 sec — Customer and quote:** Add a fictional customer, create a quote for two consulting sessions at USD 100 each, and show the USD 200 total before saving.
- **25–40 sec — Invoice:** Convert the reviewed quote to an invoice; show the saved line items and due date.
- **40–55 sec — Installment:** In the isolated demo workspace, record a fictional USD 50 installment with reference `DEMO-TRANSFER-001`; show the remaining USD 150 balance. State clearly that it is a simulated record, not a bank transfer.
- **55–66 sec — Reporting and safety:** Show the currency-separated receivables report and audit event. Point out duplicate reference protection and human review.
- **66–75 sec — Close:** “The app tracks manual payment workflows. It does not move money or confirm a bank transfer automatically.” End on the report and GitHub repository.

## Screenshots to capture from the real app

After starting a fresh local app using the README's SQLite/test settings, capture:
1. Overview with fictional customer/invoice rows.
2. Quote review showing line items and the total.
3. Invoice details after quote conversion.
4. Installment ledger showing USD 50 received and USD 150 remaining.
5. Currency-separated report or CSV preview.

The website cards currently use drawn illustrations. The existing `portfolio/cover.png` is a marketing graphic, not evidence of app state. Save screenshots only from the isolated demo workspace; crop out local paths, cookies, credentials and personal data. Include a label such as “Local demo with fictional data.”

## Sample inputs

- Customer: Cedar Studio — `billing@cedar.example`
- Quote: three brand-design sessions at USD 400 each; due in 14 days
- Installment: USD 400; reference `DEMO-TRANSFER-001`

These values are fictional. Reserved `.example` addresses must not be used for sending.

## What is tested and what is not

The repository README reports 61 isolated SQLite tests passed. The live health endpoint was verified on 5 November 2026. The public authenticated app has no guest account; Render Free may sleep between visits. No actual screen recording, live email delivery, PayPal Sandbox capture, bank integration, or model-backed invoice extraction has been verified. Record the video only after the local workflow above succeeds on screen.

## Upwork portfolio entry

**Title:** Invoice & Receivables Workflow — FastAPI, MySQL and Python

**Role:** Full-stack developer · personal portfolio project

**Description:** I built PayPilot, an invoice and receivables workspace for small service businesses. The workflow includes reusable customer records, reviewable quote-to-invoice conversion, monthly invoice drafts, partial-payment tracking, currency-separated reporting, downloadable PDFs and controlled email drafts. The backend uses FastAPI, SQLAlchemy and MySQL, with isolated SQLite tests. Payment records require human review; the app does not move money or confirm bank transfers.

**Demo/access note:** The hosted service is healthy but requires the administrator password. Public demo login is disabled. Share the source and local fictional-data instructions; do not share the admin password. The public preview is design-only. The actual application screenshots and short video are still to be captured from an isolated local workspace.
