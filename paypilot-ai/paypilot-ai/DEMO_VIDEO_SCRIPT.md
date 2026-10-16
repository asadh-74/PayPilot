# Demo Video Script — PayPilot AI (< 3 minutes)

## Shot list / narration

**0:00–0:15 — Hook**
(Show Devpost title card + app homepage)
"Meet PayPilot AI — type a sentence, get a PayPal payment link, and let AI run
your receipts and analytics. Built on the PayPal sandbox, so every transaction
you'll see is real API traffic with zero real money."

**0:15–0:40 — PayPal sandbox setup (fast cuts)**
(Developer dashboard → Apps & Credentials → show Client ID/Secret being copied;
.env being filled)
"Two sandbox credentials are all you need. Paste them in, run one command —
`python run.py` — and the copilot is live."

**0:40–1:20 — Core demo: natural language → captured payment**
(Type: "Charge $25.00 USD for a custom logo design" → click Create)
"The AI parses amount, currency and description instantly. PayPilot creates a
PayPal Order through the Orders v2 API…" (show approve link)
"…and opens sandbox checkout. I'll approve as a sandbox buyer…"
(approve in PayPal popup, return to dashboard, hit Sync — status flips to CAPTURED)
"…sync captures the funds server-side. Payment complete."

**1:20–1:50 — AI receipts + webhooks**
(Open Receipt modal; show outbox entry; show webhook log with PAYMENT.CAPTURE.COMPLETED)
"The moment money moves, PayPal's webhook hits our endpoint, the payment status
updates automatically, and an LLM writes the receipt — delivered to the outbox
or via real SMTP."

**1:50–2:20 — AI insights + provider flexibility**
(Click Analyze; show generated insights. Show config badge switching AI providers)
"One click turns raw transactions into insights — totals, pipeline, anomalies.
And the AI layer is swappable: OpenAI, Claude, or fully-local Ollama… or nothing
at all, thanks to the offline fallback."

**2:20–2:45 — Wrap-up**
(Dashboard wide shot)
"PayPilot AI: sentence in, payment out, insights on top — PayPal sandbox plus
the AI provider of your choice. Open source, five-minute setup. Try it yourself."

**End card:** repo URL + "PayPal AI Hackathon 2026"
