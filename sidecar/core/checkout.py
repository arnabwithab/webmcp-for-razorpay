import json
import time
from pathlib import Path

from sidecar.utils.logger import logger


class LinkStore:
    """File-backed dict of payment links: link_id -> record. Single-process demo."""

    def __init__(self, path: Path):
        self.path = path
        self._data: dict = {}
        if path.exists():
            self._data = json.loads(path.read_text())

    def _flush(self):
        self.path.write_text(json.dumps(self._data, indent=2))

    def put(self, link_id: str, record: dict):
        self._data[link_id] = record
        self._flush()

    def get(self, link_id: str) -> dict | None:
        return self._data.get(link_id)

    def update_status(self, link_id: str, status: str):
        if link_id in self._data:
            self._data[link_id]["status"] = status
            self._flush()

    def all(self) -> dict:
        return dict(self._data)


def price_items(snapshot_path: Path, items: list[dict]) -> int:
    """Server-authoritative re-pricing from snapshot.json. Client amounts are ignored."""
    snapshot = json.loads(snapshot_path.read_text())
    prices = {item["sku"]: item["pricePaise"] for item in snapshot}
    total = 0
    for line in items:
        sku = line["sku"]
        if sku not in prices:
            raise CheckoutError("unknown_sku", f"unknown sku {sku!r}; price from snapshot failed")
        total += prices[sku] * int(line.get("qty", 1))
    return total


class CheckoutError(Exception):
    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


def create_checkout(
    snapshot_path: Path,
    links: LinkStore,
    rzp,
    audit_path: Path,
    max_amount_paise: int,
    session_id: str,
    arm: str,
    task_id: str,
    items: list[dict],
) -> dict:
    from sidecar.core.audit import append_event

    total = price_items(snapshot_path, items)

    if not items or total <= 0:
        raise CheckoutError("empty_cart", "cart is empty; add items before checkout")

    if total > max_amount_paise:
        raise CheckoutError(
            "cap_exceeded",
            f"total {total} paise exceeds cap {max_amount_paise}; no link created",
            total_paise=total,
        )

    link = rzp.create_payment_link(
        amount=total,
        currency="INR",
        reference_id=f"{task_id}:{session_id}",
        description=f"order {task_id}",
        notify={"sms": False, "email": False},
        reminder_enable=False,
    )
    links.put(
        link["id"],
        {
            "link_id": link["id"],
            "short_url": link["short_url"],
            "amount_paise": total,
            "items": items,
            "session_id": session_id,
            "arm": arm,
            "task_id": task_id,
            "status": link.get("status", "created"),
            "created_ts": int(time.time() * 1000),
        },
    )
    append_event(
        audit_path,
        session_id=session_id,
        arm=arm,
        task_id=task_id,
        event="checkout_opened",
        payload={"link_id": link["id"], "amount_paise": total},
    )
    logger.info(f"checkout link={link['id']} amount={total} arm={arm}")
    return {
        "linkId": link["id"],
        "shortUrl": link["short_url"],
        "amountPaise": total,
    }
