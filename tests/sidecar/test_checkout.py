import json

import pytest

from sidecar.core.checkout import CheckoutError, LinkStore, create_checkout, price_items

SNAPSHOT = [
    {
        "sku": "NJ-01",
        "name": "Nike Jersey",
        "priceSource": {"value": 10.0, "currency": "USD"},
        "pricePaise": 83000,
        "priceInrLabel": "₹830.00",
    },
    {
        "sku": "SK-02",
        "name": "Sneakers",
        "priceSource": {"value": 50.0, "currency": "USD"},
        "pricePaise": 415000,
        "priceInrLabel": "₹4,150.00",
    },
]


def _write_snapshot(tmp_path, items=SNAPSHOT):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(items))
    return path


def test_price_items_uses_snapshot_never_client_amount(tmp_path):
    snap = _write_snapshot(tmp_path)
    total = price_items(snap, [{"sku": "NJ-01", "qty": 2}, {"sku": "SK-02", "qty": 1}])
    assert total == 2 * 83000 + 415000


def test_price_items_unknown_sku_raises(tmp_path):
    snap = _write_snapshot(tmp_path)
    with pytest.raises(CheckoutError):
        price_items(snap, [{"sku": "NOPE", "qty": 1}])


def test_cap_rejection_creates_no_link(tmp_path):
    snap = _write_snapshot(tmp_path)
    links = LinkStore(tmp_path / "links.json")
    calls = []

    class FakeRzp:
        def create_payment_link(self, **kwargs):
            calls.append(kwargs)
            return {"id": "plink_x", "short_url": "https://rzp.io/i/x", "status": "created"}

    # 415000 * 2 = 830000 > 500000 cap
    with pytest.raises(CheckoutError) as err:
        create_checkout(
            snapshot_path=snap,
            links=links,
            rzp=FakeRzp(),
            audit_path=tmp_path / "audit.jsonl",
            max_amount_paise=500000,
            session_id="s1",
            arm="agent",
            task_id="t1",
            items=[{"sku": "SK-02", "qty": 2}],
        )
    assert err.value.code == "cap_exceeded"
    assert calls == []  # no link created
    assert links.all() == {}


def test_create_checkout_mints_link_and_logs_event(tmp_path):
    snap = _write_snapshot(tmp_path)
    links = LinkStore(tmp_path / "links.json")

    class FakeRzp:
        def create_payment_link(self, amount, currency, reference_id, **kwargs):
            assert currency == "INR"
            return {
                "id": "plink_1",
                "short_url": "https://rzp.io/i/1",
                "status": "created",
                "amount": amount,
            }

    result = create_checkout(
        snapshot_path=snap,
        links=links,
        rzp=FakeRzp(),
        audit_path=tmp_path / "audit.jsonl",
        max_amount_paise=500000,
        session_id="s1",
        arm="agent",
        task_id="t1",
        items=[{"sku": "NJ-01", "qty": 1}],
    )
    assert result["linkId"] == "plink_1"
    assert result["shortUrl"] == "https://rzp.io/i/1"
    assert result["amountPaise"] == 83000

    stored = links.get("plink_1")
    assert stored["items"] == [{"sku": "NJ-01", "qty": 1}]
    assert stored["status"] == "created"

    events = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert [e["event"] for e in events] == ["checkout_opened"]
    assert events[0]["arm"] == "agent"
