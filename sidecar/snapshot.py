"""Catalog snapshot: canonical pricing, INR relabel at fixed rate (spec §6)."""

import json
import time
from pathlib import Path

import httpx

from sidecar.utils.config import settings
from sidecar.utils.logger import logger

# Fixed conversion rate, recorded per item via priceSource/pricePaise (derivable + auditable).
USD_TO_INR = 83.0

SNAPSHOT_PATH = Path(__file__).resolve().parent / "snapshot.json"


def build_snapshot(products: list[dict], usd_to_inr: float = USD_TO_INR) -> list[dict]:
    items = []
    for product in products:
        price_usd = product.get("price")
        if price_usd is None:
            variant_prices = [v["price"] for v in product.get("variants", []) if v.get("price")]
            if not variant_prices:
                continue
            price_usd = min(variant_prices)
        paise = round(price_usd * usd_to_inr * 100)
        items.append(
            {
                "sku": str(product.get("sku") or product.get("product_id")),
                "name": product.get("name", ""),
                "priceSource": {"value": price_usd, "currency": "USD"},
                "pricePaise": paise,
                "priceInrLabel": f"₹{paise / 100:,.2f}",
            }
        )
    return items


def fetch_catalog(base_url: str) -> list[dict]:
    """Fetch seeded catalog from the store's public API (paginated)."""
    products, page = [], 1
    while True:
        resp = httpx.get(f"{base_url}/api/products", params={"page": page, "limit": 100}, timeout=15)
        resp.raise_for_status()
        batch = resp.json().get("data", {}).get("items", [])
        products.extend(batch)
        if len(batch) < 100:
            return products
        page += 1


def make_snapshot(store_origin: str, out_path: Path = SNAPSHOT_PATH):
    products = fetch_catalog(store_origin)
    items = build_snapshot(products)
    out_path.write_text(json.dumps(items, indent=2))
    logger.info(f"snapshot written items={len(items)} out={out_path}")
    return items


if __name__ == "__main__":
    items = make_snapshot(settings.store_origin)
    print(f"snapshot: {len(items)} items -> {SNAPSHOT_PATH}")
