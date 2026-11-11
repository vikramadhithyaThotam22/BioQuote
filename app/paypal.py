"""PayPal Orders v2 (sandbox) client."""
import os, time, httpx

BASE = lambda: os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
_tok = {"v": None, "exp": 0.0}

def _token() -> str:
    if _tok["v"] and time.time() < _tok["exp"] - 60:
        return _tok["v"]
    r = httpx.post(f"{BASE()}/v1/oauth2/token", data={"grant_type": "client_credentials"},
                   auth=(os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_CLIENT_SECRET"]), timeout=20)
    r.raise_for_status()
    j = r.json()
    _tok.update(v=j["access_token"], exp=time.time() + j["expires_in"])
    return _tok["v"]

def _h(extra=None):
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json", **(extra or {})}

def create_order(job_id: str, amount_usd: float, description: str, return_url: str, cancel_url: str) -> dict:
    body = {"intent": "CAPTURE",
            "purchase_units": [{"reference_id": job_id, "custom_id": job_id,
                                "description": description[:127],
                                "amount": {"currency_code": "USD", "value": f"{amount_usd:.2f}"}}],
            "payment_source": {"paypal": {"experience_context": {
                "return_url": return_url, "cancel_url": cancel_url,
                "user_action": "PAY_NOW", "brand_name": "BioQuote Agent"}}}}
    r = httpx.post(f"{BASE()}/v2/checkout/orders", json=body, timeout=20,
                   headers=_h({"PayPal-Request-Id": f"order-{job_id}"}))
    r.raise_for_status()
    j = r.json()
    approve = next(l["href"] for l in j["links"] if l["rel"] in ("payer-action", "approve"))
    return {"order_id": j["id"], "status": j["status"], "approve_url": approve}

def get_order(order_id: str) -> dict:
    r = httpx.get(f"{BASE()}/v2/checkout/orders/{order_id}", headers=_h(), timeout=20)
    r.raise_for_status()
    return r.json()

def capture_order(order_id: str) -> dict:
    r = httpx.post(f"{BASE()}/v2/checkout/orders/{order_id}/capture", headers=_h(
        {"PayPal-Request-Id": f"cap-{order_id}"}), timeout=20)
    r.raise_for_status()
    return r.json()

def verify_webhook(headers: dict, event: dict) -> bool:
    """Verify a webhook signature via PayPal's verify-webhook-signature API."""
    body = {"auth_algo": headers.get("paypal-auth-algo"), "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "webhook_id": os.environ["PAYPAL_WEBHOOK_ID"], "webhook_event": event}
    r = httpx.post(f"{BASE()}/v1/notifications/verify-webhook-signature", json=body, headers=_h(), timeout=20)
    return r.status_code == 200 and r.json().get("verification_status") == "SUCCESS"
