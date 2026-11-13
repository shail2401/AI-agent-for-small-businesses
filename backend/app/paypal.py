import time
import uuid

import httpx

from .config import settings


class PayPalError(Exception):
    pass


class PayPalClient:
    def __init__(self):
        self._token, self._exp = "", 0.0

    @property
    def configured(self) -> bool:
        return bool(settings.paypal_client_id and settings.paypal_client_secret)

    def _auth(self) -> dict:
        if not self.configured:
            raise PayPalError("PayPal sandbox credentials are not set (PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET).")
        if time.time() > self._exp - 30:
            r = httpx.post(f"{settings.paypal_base_url}/v1/oauth2/token", data={"grant_type": "client_credentials"},
                           auth=(settings.paypal_client_id, settings.paypal_client_secret), timeout=20)
            if r.status_code != 200:
                raise PayPalError(f"PayPal auth failed: {r.text}")
            j = r.json()
            self._token, self._exp = j["access_token"], time.time() + j["expires_in"]
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def create_order(self, order_id: int, total: str, items: list[dict], currency: str = "USD") -> dict:
        body = {"intent": "CAPTURE", "purchase_units": [{
            "reference_id": str(order_id), "custom_id": str(order_id),  # custom_id round-trips into webhooks
            "description": "Luke's Diner order",
            "amount": {"currency_code": currency, "value": total,
                       "breakdown": {"item_total": {"currency_code": currency, "value": total}}},
            "items": [{"name": i["name"], "quantity": str(i["qty"]),
                       "unit_amount": {"currency_code": currency, "value": i["price"]}} for i in items]}]}
        r = httpx.post(f"{settings.paypal_base_url}/v2/checkout/orders", json=body, timeout=20,
                       headers={**self._auth(), "PayPal-Request-Id": f"order-{order_id}-{uuid.uuid4().hex[:8]}"})
        if r.status_code not in (200, 201):
            raise PayPalError(f"Create order failed: {r.text}")
        return r.json()

    def capture(self, paypal_order_id: str) -> dict:
        r = httpx.post(f"{settings.paypal_base_url}/v2/checkout/orders/{paypal_order_id}/capture", timeout=20,
                       headers={**self._auth(), "PayPal-Request-Id": f"cap-{paypal_order_id}"}, content=b"{}")
        if r.status_code not in (200, 201):
            raise PayPalError(f"Capture failed: {r.text}")
        return r.json()

    def verify_webhook(self, headers: dict, event: dict) -> bool:
        body = {"auth_algo": headers.get("paypal-auth-algo"), "cert_url": headers.get("paypal-cert-url"),
                "transmission_id": headers.get("paypal-transmission-id"),
                "transmission_sig": headers.get("paypal-transmission-sig"),
                "transmission_time": headers.get("paypal-transmission-time"),
                "webhook_id": settings.paypal_webhook_id, "webhook_event": event}
        r = httpx.post(f"{settings.paypal_base_url}/v1/notifications/verify-webhook-signature",
                       json=body, headers=self._auth(), timeout=20)
        return r.status_code == 200 and r.json().get("verification_status") == "SUCCESS"


paypal = PayPalClient()
