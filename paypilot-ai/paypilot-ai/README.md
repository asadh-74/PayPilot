# 🧭 PayPilot AI — PayPal × AI Payments Copilot

**PayPilot AI** turns plain English into PayPal payment links, then puts an AI
assistant on top of your entire payment flow: parsing, receipts, insights and
webhook handling. Built entirely on the **free PayPal Sandbox** — no real money,
no live credentials required.

![stack](https://img.shields.io/badge/PayPal-Sandbox-0070E0) ![ai](https://img.shields.io/badge/AI-OpenAI%20%7C%20Anthropic%20%7C%20Ollama-22c55e) ![license](https://img.shields.io/badge/license-MIT-blue)

---

## ✨ Features

| # | Feature | What it does |
|---|---------|--------------|
| 1 | **Natural-language → payment link** | Type *"Charge $25 for a logo design"* and the AI extracts amount, currency, description and recipient, creates a **PayPal Order** via the Orders v2 API and gives you an approval link instantly. |
| 2 | **Sandbox checkout flow** | Approve as a sandbox **buyer** in the PayPal popup; the app captures the funds server-side and tracks the full lifecycle (CREATED → APPROVED → CAPTURED). |
| 3 | **AI-written receipts** | After capture, an LLM writes a warm, personalized receipt (stored per payment, viewable in one click, delivered to the built-in outbox or via real SMTP). |
| 4 | **AI payments insights** | One click summarises your sales: totals, pipeline, above-average transactions, trends and anomalies from your real transaction data. |
| 5 | **PayPal webhooks** | Receives `PAYMENT.CAPTURE.COMPLETED` (and friends), auto-updates payment state and triggers receipt generation — even for payments approved outside this app. |
| 6 | **Receipt outbox** | Built-in email outbox so receipts work with **zero configuration**; plug in SMTP to send real mail. |
| 7 | **Offline fallback AI** | No AI key? The app still works end-to-end with a built-in regex parser + heuristic insights, so judges can run it with only PayPal sandbox creds. |

## 🧰 Tools Used

- **PayPal Developer Platform (Sandbox)** — Orders v2 REST API (`create / get / capture`), OAuth2 client-credentials, `application_context` approval flow, `PAYMENT.CAPTURE.COMPLETED` webhooks. Live payments are out of scope by design.
- **AI (your choice):** OpenAI (`gpt-4o-mini`), Anthropic Claude, or fully-local **Ollama** (llama3.1) — auto-detected from env vars. Any OpenAI-compatible endpoint works too.
- **FastAPI + Uvicorn** (Python) — REST API and webhook receiver.
- **SQLite** — zero-config persistence (payments, webhook events, outbox).
- **Vanilla HTML/CSS/JS** dashboard — no build step, runs anywhere.
- **ngrok / cloudflared (optional)** — expose webhooks locally.

## 🚀 Quick Start (5 minutes)

### 1. Prerequisites
- Python **3.10+**
- A free **PayPal Developer** account → <https://developer.paypal.com/dashboard>

### 2. PayPal Sandbox setup
1. Dashboard → **Apps & Credentials** → create a new app (environment: **Sandbox**).
2. Copy the **Client ID** and **Secret**.
3. (Optional, for the webhook demo) Sandbox → **Accounts** → note a **buyer** test account (you can generate a password). Add funds are auto-provisioned in sandbox.
4. (Optional) Dashboard → your app → **Webhooks** → add endpoint `http://localhost:8000/webhooks/paypal` (use an ngrok URL locally) and subscribe to `Payment capture completed`.

### 3. Run the app
```bash
git clone https://github.com/YOUR_USERNAME/paypilot-ai.git
cd paypilot-ai
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET
# load the env (or export the vars), then:
python run.py                 # → http://localhost:8000
```

> No `.env` loader dependency: export the variables in your shell, e.g.
> `export PAYPAL_CLIENT_ID=... PAYPAL_CLIENT_SECRET=...`.

### 4. Try the demo flow
1. Type *"Charge $25.00 USD for a custom logo design"* → **Create PayPal link ⚡**
2. Click the approval link → log in with the **sandbox buyer** account → approve.
3. Back in the dashboard press **Sync** on the row → status becomes `CAPTURED`, the AI receipt appears in the **Receipt Outbox**, and the webhook log shows `PAYMENT.CAPTURE.COMPLETED` (if webhooks are configured).
4. Click **🤖 Analyze** for AI-generated insights over your real sandbox transactions.

### 5. Optional extras
- **Ollama (100% local AI):** `ollama pull llama3.1` then set `OLLAMA_HOST=http://localhost:11434`.
- **Real email receipts:** fill in the `SMTP_*` variables.
- **Public webhook URL locally:** `ngrok http 8000` → put the https URL + `/webhooks/paypal` in the PayPal webhook settings and set `APP_BASE_URL` to the same https origin (so buyer redirects also work from a phone).

## 🗂️ Project Structure
```
paypilot-ai/
├── app/
│   ├── main.py            # FastAPI app: payments, insights, webhooks, outbox
│   ├── paypal_client.py   # PayPal Orders v2 + OAuth2 client (sandbox)
│   ├── ai_service.py      # OpenAI / Anthropic / Ollama + offline fallback
│   ├── db.py              # SQLite layer
│   ├── emailer.py         # SMTP receipts with outbox fallback
│   └── static/            # dashboard (index.html, app.js, style.css)
├── run.py                 # convenience launcher
├── requirements.txt
├── .env.example
└── README.md
```

## 🔑 Environment Variables
See [.env.example](.env.example). Only the two PayPal sandbox variables are **required** — everything else is optional.

## ⚠️ Scope Notes
- Sandbox only: the default `PAYPAL_BASE_URL` is `https://api-m.sandbox.paypal.com`.
- Webhook signature verification is intentionally lightweight for the demo
  (relies on the unguessable localhost/ngrok URL). For production, verify with
  `/v1/notifications/verify-webhook-signature` using a webhook ID.
- AI provider keys never leave your server; the offline fallback keeps the app
  fully functional without any AI vendor account.

## 📜 License
MIT — see [LICENSE](LICENSE).
