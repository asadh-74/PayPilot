# PayPilot 2.2 delivery

Implemented: exact decimal-string API amounts; optional line items with server-validated totals; expiring customer links with hashed tokens and revocation; private customer invoice/receipt page with browser print-to-PDF; owner-scoped invoice timeline; checkout recovery preserving invoice identity; return-path reconciliation; reminder drafts; zero-output automation run visibility; expired demo cleanup; mobile session control; blocking webhook verification moved off the event loop.

Schema upgrade: additive pp_invoice_items, pp_share_links and pp_automation_runs tables, created using existing metadata startup. No existing financial columns or tables are dropped or renamed. Keep one Uvicorn worker. Existing invoices remain valid and simply have no items. This release does not introduce Alembic or claim a complete migration framework.

Validation: 36 pytest tests locally; JavaScript syntax validation; GitHub Actions repeats against SQLite and isolated MySQL. Browser and live-deploy verification are recorded separately after deployment.

Operational limits: messages remain previews; free-host sleep pauses scheduled checks; automation operates on active sessions; no real funds, refunds, subscriptions, tax calculation or team accounts. Public sharing is a bearer link lasting 24 hours; the owner can revoke it or rotate it. Demo workspaces older than eight hours without an active session are deleted in bounded batches.

Aiven setup: use a dedicated paypilot database and least-privilege user. Privately configure DATABASE_URL, MYSQL_SSL_CA, REQUIRE_MYSQL=true, COOKIE_SECURE=true and APP_BASE_URL on Render. Never commit credentials. Validate /health reports mysql, then test persistence after restart. Do not use TEST_MYSQL_URL with app data: tests drop tables.

PayPal setup: privately supply sandbox client ID/secret and webhook ID; configure PAYMENT.CAPTURE.COMPLETED at APP_BASE_URL/webhooks/paypal; verify a sandbox buyer approval and capture, amount/currency matching, duplicate-webhook behavior and failure recovery before claiming sandbox checkout is configured.
