import base64
import hashlib
import hmac as hmac_mod
import json

import pytest
from fastapi.testclient import TestClient

import sidecar.app as app_module
from sidecar.app import app
from sidecar.core.checkout import LinkStore

SNAPSHOT = [
    {"sku": "NJ-01", "name": "Nike Jersey", "priceSource": {"value": 10.0, "currency": "USD"},
     "pricePaise": 83000, "priceInrLabel": "₹830.00"},
    {"sku": "SK-02", "name": "Sneakers", "priceSource": {"value": 50.0, "currency": "USD"},
     "pricePaise": 415000, "priceInrLabel": "₹4,150.00"},
]

SECRET = "whsec_dummy"


class FakeRzp:
    def __init__(self):
        self.created = []
        self.remote_status = "created"

    def create_payment_link(self, **kwargs):
        link = {
            "id": f"plink_{len(self.created) + 1}",
            "short_url": f"https://rzp.io/i/{len(self.created) + 1}",
            "status": "created",
            "amount": kwargs["amount"],
        }
        self.created.append(link)
        return link

    def fetch_payment_link(self, link_id):
        return {"id": link_id, "status": self.remote_status}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    snap = tmp_path / "snapshot.json"
    snap.write_text(json.dumps(SNAPSHOT))
    monkeypatch.setattr(app_module, "SNAPSHOT_PATH", snap)
    monkeypatch.setattr(app_module, "AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(app_module, "LINKS", LinkStore(tmp_path / "links.json"))
    monkeypatch.setattr(app_module, "rzp", FakeRzp())
    return TestClient(app)


def _event(arm="agent", task_id="t1", event="task_start"):
    return {"session_id": "s1", "arm": arm, "task_id": task_id, "event": event}


def test_event_server_ts_and_audit(client):
    resp = client.post("/event", json=_event())
    assert resp.status_code == 200
    body = resp.json()
    assert body["ts"] > 0

    audit = client.get("/audit").json()
    assert audit[0]["event"] == "task_start"
    assert audit[0]["prev_hash"] == "0" * 64


def test_checkout_create_ignores_client_amount(client):
    resp = client.post(
        "/checkout/create",
        json={"session_id": "s1", "arm": "agent", "task_id": "t1",
              "items": [{"sku": "NJ-01", "qty": 1}], "amount_paise": 1},
    )
    assert resp.status_code == 200
    assert resp.json()["amountPaise"] == 83000  # snapshot price, not client-sent


def test_checkout_create_cap_rejected_no_link(client):
    resp = client.post(
        "/checkout/create",
        json={"session_id": "s1", "arm": "agent", "task_id": "t1",
              "items": [{"sku": "SK-02", "qty": 2}]},  # 830000 > 500000
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "cap_exceeded"
    assert app_module.rzp.created == []  # no link created


def test_webhook_hmac_valid_marks_paid(client):
    created = client.post(
        "/checkout/create",
        json={"session_id": "s1", "arm": "agent", "task_id": "t1",
              "items": [{"sku": "NJ-01", "qty": 1}]},
    ).json()
    payload = {
        "event": "payment_link.paid",
        "payload": {"payment_link": {"entity": {"id": created["linkId"], "status": "paid"}}},
    }
    raw = json.dumps(payload).encode()
    sig = hmac_mod.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    resp = client.post(
        "/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert resp.status_code == 200

    audit = client.get("/audit").json()
    assert any(e["event"] == "payment_paid" for e in audit)


def test_webhook_forged_signature_rejected(client):
    payload = {"event": "payment_link.paid", "payload": {"payment_link": {"entity": {"id": "plink_1"}}}}
    raw = json.dumps(payload).encode()
    sig = hmac_mod.new(b"wrong_secret", raw, hashlib.sha256).hexdigest()
    resp = client.post(
        "/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert resp.status_code == 400
    audit = client.get("/audit").json()
    assert not any(e["event"] == "payment_paid" for e in audit)


def test_webhook_and_poll_double_close_collapses(client):
    created = client.post(
        "/checkout/create",
        json={"session_id": "s1", "arm": "agent", "task_id": "t1",
              "items": [{"sku": "NJ-01", "qty": 1}]},
    ).json()

    # webhook closes it
    payload = {"event": "payment_link.paid", "payload": {"payment_link": {"entity": {"id": created["linkId"]}}}}
    raw = json.dumps(payload).encode()
    sig = hmac_mod.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    client.post("/webhook", content=raw, headers={"X-Razorpay-Signature": sig})

    # poll then sees paid; must not duplicate the event
    app_module.rzp.remote_status = "paid"
    client.get(f"/poll/{created['linkId']}")
    client.get(f"/poll/{created['linkId']}")

    audit = client.get("/audit").json()
    assert len([e for e in audit if e["event"] == "payment_paid"]) == 1


def test_resume_pending_vs_expired(client):
    created = client.post(
        "/checkout/create",
        json={"session_id": "s1", "arm": "agent", "task_id": "t1",
              "items": [{"sku": "NJ-01", "qty": 1}]},
    ).json()

    # pending -> same shortUrl
    app_module.rzp.remote_status = "created"
    r1 = client.post("/checkout/resume", json={"linkId": created["linkId"]}).json()
    assert r1["status"] == "pending"
    assert r1["shortUrl"] == created["shortUrl"]

    # expired -> fresh link minted + recovered event
    app_module.rzp.remote_status = "expired"
    r2 = client.post("/checkout/resume", json={"linkId": created["linkId"]}).json()
    assert r2["status"] == "expired"
    assert r2["shortUrl"] != created["shortUrl"]

    audit = client.get("/audit").json()
    assert any(e["event"] == "recovered" for e in audit)


def test_compare_renders_html_with_data(client):
    client.post("/event", json=_event(event="task_start"))
    client.post("/event", json=_event(event="product_viewed"))
    client.post("/event", json=_event(event="cart_updated"))
    client.post("/event", json=_event(event="payment_paid"))

    resp = client.get("/compare")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    # data block parseable as JSON
    body = resp.text
    assert '<script id="compare-data" type="application/json">' in body


def test_cors_store_origin_only(client):
    resp = client.options(
        "/event",
        headers={"Origin": "http://localhost:8000", "Access-Control-Request-Method": "POST"},
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:8000"

    resp = client.options(
        "/event",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert resp.headers.get("access-control-allow-origin") != "http://evil.example"


def test_static_loader_served(client):
    resp = client.get("/static/loader.js")
    assert resp.status_code == 200
    assert "razorpay-agent-kit" in resp.text
