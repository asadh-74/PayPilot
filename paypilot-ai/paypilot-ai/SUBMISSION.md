# Devpost Submission — PayPilot AI

## 🧭 Elevator Pitch (tagline)
"Stripe for sentences." Type what you want to charge in plain English — PayPilot AI
parses it with an LLM, spins up a real PayPal payment link in the sandbox, captures
the money, writes the receipt with AI, and explains your sales back to you.

## 📝 About the project
PayPilot AI is a payments copilot for freelancers and micro-merchants. Instead of
fiddling with invoice forms, a seller types "Charge €49.99 for two hours of
consulting to jane@example.com" — the AI extracts the structured payment intent,
the app creates a PayPal Order via the Orders v2 API, and the seller gets an
approval link to send to their client. When the sandbox buyer approves, the app
captures the payment, generates a personalized AI-written receipt, logs the
PayPal webhook, and surfaces AI-generated insights (totals, pipeline, anomalies)
across all transactions on the dashboard.

### Key features (all live against the PayPal sandbox)
1. **NL → payment link** — LLM intent extraction (amount, currency, description,
   recipient email) with a fully offline regex fallback so the demo never breaks.
2. **Full checkout lifecycle** — create → buyer approval in the sandbox popup →
   server-side capture → status sync (CREATED / APPROVED / CAPTURED).
3. **AI receipts** — a receipt body is generated per captured payment and stored;
   delivered through a built-in outbox or real SMTP.
4. **AI insights** — one-click LLM analysis over real sandbox transaction history.
5. **PayPal webhooks** — `PAYMENT.CAPTURE.COMPLETED` events update state and
   trigger receipts automatically, even for approvals made outside the app.
6. **Provider-agnostic AI** — OpenAI, Anthropic Claude, or 100% local Ollama;
   auto-detected, hot-swappable, with a zero-key offline mode.

## 🛠️ How we built it
- **PayPal Developer Platform (Sandbox):** OAuth2 client-credentials, Orders v2
  create/get/capture, application_context approval links, and webhooks.
- **AI:** OpenAI gpt-4o-mini by default; Anthropic and Ollama adapters; structured
  JSON extraction prompts; a regex/heuristic fallback for offline judging.
- **Backend:** FastAPI + SQLite (single-file DB, zero setup).
- **Frontend:** dependency-free HTML/CSS/JS dashboard with live status polling.
- **DevEx:** one-command launch (`python run.py`), `.env.example`, README with
  exact sandbox setup steps and a webhook simulator walkthrough.

## 🚧 Challenges
- PayPal's approval/capture split means state can change outside our app, so the
  dashboard syncs with the Orders API and reconciles via webhooks for a
  single source of truth.
- Keeping the demo runnable for judges with *zero* AI keys meant designing the
  extraction and insights features with graceful degradation.

## 🏆 Accomplishments
A genuinely working PayPal sandbox commerce loop — parsed intent → order → buyer
approval → capture → AI receipt → webhook → insights — in a repo that runs in
under five minutes with only two environment variables.

## 📚 What we learned
PayPal's Orders v2 flow, webhook reconciliation patterns, LLM structured-output
extraction with deterministic fallbacks, and building demo-grade reliability
into a weekend hack.

## 🔮 What's next
- Voice-first payment creation
- Multi-item carts and recurring billing (subscriptions API)
- Full webhook-signature verification and live-mode toggle
- Hosted demo + PayPal "merchant onboarding" via partner referrals
