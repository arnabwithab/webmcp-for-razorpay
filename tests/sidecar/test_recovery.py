import json

import pytest

from sidecar.core.checkout import LinkStore
from sidecar.core.recovery import close_as_paid, poll_and_close, resume_checkout

SNAPSHOT = [
    {
        "sku": "NJ-01",
        "name": "Nike Jersey",
        "priceSource": {"value": 10.0, "currency": "USD"},
        "pricePaise": 83000,
        "priceInrLabel": "₹830.00",
    }
]


def _seed_link(tmp_path, status="created"):
    links = LinkStore(tmp_path / "links.json")
    links.put(
        "plink_1",
        {
            "link_id": "plink_1",
            "short_url": "https://rzp.io/i/1",
            "amount_paise": 83000,
            "items": [{"sku": "NJ-01", "qty": 1}],
            "session_id": "s1",
            "arm": "agent",
            "task_id": "t1",
            "status": status,
            "created_ts": 0,
        },
    )
    return links


def _audit_events(tmp_path):
    path = tmp_path / "audit.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_poll_marks_paid_once(tmp_path):
    links = _seed_link(tmp_path)
    audit = tmp_path / "audit.jsonl"

    class FakeRzp:
        def __init__(self):
            self.fetches = 0

        def fetch_payment_link(self, link_id):
            self.fetches += 1
            return {"id": link_id, "status": "paid"}

    rzp = FakeRzp()
    r1 = poll_and_close(links, rzp, audit, "plink_1")
    r2 = poll_and_close(links, rzp, audit, "plink_1")

    assert r1["status"] == "paid"
    assert r2["status"] == "paid"
    paid_events = [e for e in _audit_events(tmp_path) if e["event"] == "payment_paid"]
    assert len(paid_events) == 1  # poll-vs-webhook double close collapses to one
    assert links.get("plink_1")["status"] == "paid"


def test_close_as_paid_idempotent_for_webhook(tmp_path):
    links = _seed_link(tmp_path)
    audit = tmp_path / "audit.jsonl"
    close_as_paid(links, audit, "plink_1")
    close_as_paid(links, audit, "plink_1")
    paid_events = [e for e in _audit_events(tmp_path) if e["event"] == "payment_paid"]
    assert len(paid_events) == 1


def test_poll_unknown_link_404(tmp_path):
    links = LinkStore(tmp_path / "links.json")

    with pytest.raises(LookupError):
        poll_and_close(links, None, tmp_path / "audit.jsonl", "plink_missing")


def test_resume_pending_returns_same_short_url(tmp_path):
    links = _seed_link(tmp_path)
    audit = tmp_path / "audit.jsonl"

    class FakeRzp:
        def fetch_payment_link(self, link_id):
            return {"id": link_id, "status": "created"}  # created = pending

    result = resume_checkout(links, FakeRzp(), tmp_path / "snapshot.json", audit, "plink_1")
    assert result["status"] == "pending"
    assert result["shortUrl"] == "https://rzp.io/i/1"


def test_resume_expired_mints_fresh_link_and_logs_recovered(tmp_path):
    links = _seed_link(tmp_path, status="created")
    audit = tmp_path / "audit.jsonl"
    snap = tmp_path / "snapshot.json"
    snap.write_text(json.dumps(SNAPSHOT))
    fresh = {
        "id": "plink_2",
        "short_url": "https://rzp.io/i/2",
        "status": "created",
        "amount": 83000,
    }

    class FakeRzp:
        def fetch_payment_link(self, link_id):
            return {"id": link_id, "status": "expired"}

        def create_payment_link(self, **kwargs):
            return fresh

    result = resume_checkout(links, FakeRzp(), snap, audit, "plink_1")
    assert result["status"] == "expired"
    assert result["shortUrl"] == "https://rzp.io/i/2"
    assert result["linkId"] == "plink_2"

    events = _audit_events(tmp_path)
    recovered = [e for e in events if e["event"] == "recovered"]
    assert len(recovered) == 1
    assert recovered[0]["task_id"] == "t1"
    assert links.get("plink_2")["task_id"] == "t1"


def test_resume_paid_reports_paid(tmp_path):
    links = _seed_link(tmp_path)
    audit = tmp_path / "audit.jsonl"

    class FakeRzp:
        def fetch_payment_link(self, link_id):
            return {"id": link_id, "status": "paid"}

    result = resume_checkout(links, FakeRzp(), tmp_path / "snapshot.json", audit, "plink_1")
    assert result["status"] == "paid"
