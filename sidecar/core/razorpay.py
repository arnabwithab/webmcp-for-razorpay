import base64

import httpx

from sidecar.utils.config import settings
from sidecar.utils.logger import logger

API_BASE = "https://api.razorpay.com/v1"


class RazorpayClient:
    """Razorpay Payment Links API, test mode only.

    Docs: https://razorpay.com/docs/api/payment-links/
    """

    def __init__(self, timeout: float = 10.0):
        auth = base64.b64encode(
            f"{settings.razorpay_key_id}:{settings.razorpay_key_secret}".encode()
        ).decode()
        self._client = httpx.Client(
            base_url=API_BASE,
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
            timeout=timeout,
        )

    def create_payment_link(self, amount: int, currency: str, reference_id: str, **kwargs) -> dict:
        payload = {
            "amount": amount,
            "currency": currency,
            "accept_partial": False,
            "reference_id": reference_id,
            **kwargs,
        }
        resp = self._client.post("/payment_links", json=payload)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"razorpay link created id={data.get('id')}")
        return data

    def fetch_payment_link(self, link_id: str) -> dict:
        resp = self._client.get(f"/payment_links/{link_id}")
        resp.raise_for_status()
        return resp.json()
