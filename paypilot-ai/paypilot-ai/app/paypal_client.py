"""PayPal REST API client (Sandbox). Docs: https://developer.paypal.com/api/rest/"""
import base64
import os
import time

import requests

PAYPAL_BASE = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")


class PayPalClient:
    def __init__(self, client_id=None, client_secret=None):
        self.client_id = client_id or os.getenv("PAYPAL_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("PAYPAL_CLIENT_SECRET", "")
        self.base = os.getenv("PAYPAL_BASE_URL", PAYPAL_BASE)
        self._token = None
        self._token_exp = 0.0

    # ---- OAuth2 ----
    def get_access_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "PayPal sandbox credentials missing. Set PAYPAL_CLIENT_ID / "
                "PAYPAL_CLIENT_SECRET (see README -> 'PayPal Setup')."
            )
        auth = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        r = requests.post(
            f"{self.base}/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 300))
        return self._token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json",
        }

    # ---- Orders v2 ----
    def create_order(self, amount: float, currency: str, description: str,
                     reference_id: str, return_url: str, cancel_url: str) -> dict:
        """Create a PayPal order and return the API response (incl. approve link)."""
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": reference_id,
                "description": description[:127],
                "custom_id": reference_id,
                "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
            }],
            "application_context": {
                "brand_name": "PayPilot AI",
                "landing_page": "LOGIN",
                "user_action": "PAY_NOW",
                "shipping_preference": "NO_SHIPPING",
                "return_url": return_url,
                "cancel_url": cancel_url,
            },
        }
        r = requests.post(f"{self.base}/v2/checkout/orders",
                          headers=self._headers(), json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_order(self, order_id: str) -> dict:
        r = requests.get(f"{self.base}/v2/checkout/orders/{order_id}",
                         headers=self._headers(), timeout=30)
        r.raise_for_status()
        return r.json()

    def capture_order(self, order_id: str) -> dict:
        r = requests.post(f"{self.base}/v2/checkout/orders/{order_id}/capture",
                          headers=self._headers(), timeout=30)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def approve_link(order: dict) -> str | None:
        for link in order.get("links", []):
            if link.get("rel") == "approve":
                return link["href"]
        return None
