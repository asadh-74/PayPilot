"""AI provider abstraction for PayPilot AI.

Supports (in priority order):
  1. OpenAI            (OPENAI_API_KEY)
  2. Anthropic         (ANTHROPIC_API_KEY)
  3. Local Ollama      (OLLAMA_HOST, e.g. http://localhost:11434)
  4. Offline fallback  (regex extraction + rule-based insights - always works)

This means the app runs end-to-end even with zero AI keys.
"""
import json
import os
import re
from statistics import mean

import requests

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

CURRENCIES = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "INR", "BRL", "MXN", "SGD"}


# ---------------------------------------------------------------- providers
def _call_openai(system: str, user: str) -> str:
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": OPENAI_MODEL,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}]},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _call_anthropic(system: str, user: str) -> str:
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
        json={"model": ANTHROPIC_MODEL, "max_tokens": 1024,
              "system": system, "messages": [{"role": "user", "content": user}]},
        timeout=60,
    )
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"])


def _call_ollama(system: str, user: str) -> str:
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    r = requests.post(
        f"{host}/api/chat",
        json={"model": OLLAMA_MODEL, "stream": False,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}]},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def ai_chat(system: str, user: str) -> str | None:
    """Route to the first available provider; return None if none configured."""
    try:
        if os.getenv("OPENAI_API_KEY"):
            return _call_openai(system, user)
        if os.getenv("ANTHROPIC_API_KEY"):
            return _call_anthropic(system, user)
        if os.getenv("OLLAMA_HOST") or _ollama_alive():
            return _call_ollama(system, user)
    except Exception:
        return None
    return None


def _ollama_alive() -> bool:
    try:
        return requests.get(
            f"{os.getenv('OLLAMA_HOST', 'http://localhost:11434')}/api/tags",
            timeout=2).ok
    except Exception:
        return False


def active_provider() -> str:
    if os.getenv("OPENAI_API_KEY"):
        return f"OpenAI ({OPENAI_MODEL})"
    if os.getenv("ANTHROPIC_API_KEY"):
        return f"Anthropic ({ANTHROPIC_MODEL})"
    if os.getenv("OLLAMA_HOST") or _ollama_alive():
        return f"Ollama ({OLLAMA_MODEL}, local)"
    return "Offline fallback (regex + heuristics)"


# ------------------------------------------------------ feature 1: NL -> payment
EXTRACTION_SYSTEM = """You are a payment-order parser. Extract payment details from the
user's message and reply with ONLY a JSON object (no markdown):
{"amount": <number>, "currency": "<ISO 4217, default USD>", "description": "<short product/service description>",
 "recipient_email": "<email or null>"}
Rules: amount is required - convert written numbers; currency default USD;
description max 120 chars; recipient_email only if an email address appears."""


def parse_payment_prompt(text: str) -> dict:
    """Turn natural language into a structured payment request."""
    raw = ai_chat(EXTRACTION_SYSTEM, text)
    if raw:
        try:
            cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.M).strip()
            data = json.loads(cleaned)
            if isinstance(data.get("amount"), (int, float)) and data["amount"] > 0:
                return {
                    "amount": round(float(data["amount"]), 2),
                    "currency": str(data.get("currency", "USD")).upper()[:3],
                    "description": str(data.get("description", "Payment"))[:120],
                    "recipient_email": data.get("recipient_email"),
                }
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return _regex_extract(text)


def _regex_extract(text: str) -> dict:
    """Always-available fallback parser (offline mode)."""
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    curr = next((c for c in CURRENCIES if re.search(rf"\b{c}\b", text, re.I)), "USD")
    amount = None
    m = re.search(r"(?:[$€£]\s?)(\d+(?:[.,]\d{1,2})?)", text)
    if m:
        amount = float(m.group(1).replace(",", ""))
    else:
        m = re.search(r"(\d+(?:[.,]\d{1,2})?)\s*(?:dollars?|usd|eur|gbp)", text, re.I)
        if m:
            amount = float(m.group(1).replace(",", ""))
    words = {"ten": 10, "twenty": 20, "twenty five": 25, "thirty": 30,
             "fifty": 50, "seventy five": 75, "hundred": 100}
    if amount is None:
        low = text.lower()
        for w, v in words.items():
            if f"${w}" in low or f"{w} dollars" in low:
                amount = float(v)
                break
    if amount is None:
        raise ValueError(
            "Could not determine an amount. Try: 'Charge $25.00 USD for a logo design'")
    desc = re.sub(r"\s+", " ", text).strip()[:120]
    return {"amount": round(amount, 2), "currency": curr, "description": desc,
            "recipient_email": email.group(0) if email else None}


# ------------------------------------------------------ feature 2: AI receipts
RECEIPT_SYSTEM = """You write short, warm payment receipts for small businesses.
Given payment details, output ONLY the receipt body text (max 90 words, no subject line)."""


def generate_receipt(payment: dict) -> str:
    user = (f"Business: PayPilot AI Demo Store\nAmount: {payment['amount']:.2f} "
            f"{payment['currency']}\nFor: {payment['description']}\n"
            f"Buyer: {payment.get('payer_email') or 'sandbox buyer'}")
    out = ai_chat(RECEIPT_SYSTEM, user)
    if out:
        return out.strip()
    return (f"Thank you for your payment of {payment['amount']:.2f} "
            f"{payment['currency']} for \"{payment['description']}\". "
            f"A receipt from PayPilot AI Demo Store.")


# ------------------------------------------------------ feature 3: AI insights
def generate_insights(payments: list[dict]) -> str:
    if not payments:
        return "No payments yet - create your first AI payment link above!"
    total = sum(p["amount"] for p in payments if p["status"] == "CAPTURED")
    captured = [p for p in payments if p["status"] == "CAPTURED"]
    lines = [
        f"Total captured: {total:.2f} across {len(captured)} payment(s).",
        f"Pipeline: {len(payments)} order(s), "
        f"{len([p for p in payments if p['status'] == 'CREATED'])} awaiting approval.",
    ]
    big = [p for p in captured if p["amount"] > 2 * (mean([q["amount"] for q in captured]) if captured else 0)]
    if big:
        lines.append("Above-average transactions: " + "; ".join(
            f"{p['description'][:40]} ({p['amount']:.2f} {p['currency']})" for p in big[:3]))
    payload = json.dumps(payments[-20:], default=str)
    out = ai_chat(
        "You are a payments analyst. Give 3 concise, actionable insights about these "
        "PayPal transactions (trends, anomalies, next steps). Plain text, under 120 words.",
        payload)
    if out:
        lines.append("\n" + out.strip())
    return "\n".join(lines)
