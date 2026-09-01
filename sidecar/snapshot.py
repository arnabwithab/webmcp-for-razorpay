"""Catalog snapshot: canonical pricing, INR-native (spec §6, amended: store prices INR)."""

import json
from pathlib import Path

import httpx

from sidecar.utils.logger import logger

SNAPSHOT_PATH = Path(__file__).resolve().parent / "snapshot.json"


def build_snapshot(products: list[dict]) -> list[dict]:
    items = []
    for product in products:
        price = (product.get("price") or {}).get("regular", {}) or {}
        price_inr = price.get("value")
        if price_inr is None:
            variant_prices = [v["price"] for v in product.get("variants", []) if v.get("price")]
            if not variant_prices:
                continue
            price_inr = min(variant_prices)
        paise = round(price_inr * 100)
        items.append(
            {
                "sku": str(product.get("sku") or product.get("product_id")),
                "name": product.get("name", ""),
                "priceSource": {"value": price_inr, "currency": price.get("currency", "INR")},
                "pricePaise": paise,
                "priceInrLabel": f"₹{paise / 100:,.2f}",
            }
        )
    return items


def fetch_catalog(base_url: str) -> list[dict]:
    """Fetch seeded catalog from the store's public GraphQL API.

    The top-level `products` query is capped at 20 items with no pagination args,
    so fetch per-category (categories query has no such cap; 4 categories x <=6 products).
    """
    query = """
    {
      categories {
        items {
          name
          products { items { productId name sku price { regular { value currency } } } }
        }
      }
    }
    """
    resp = httpx.post(f"{base_url}/api/graphql", json={"query": query}, timeout=15)
    resp.raise_for_status()
    items = []
    for category in resp.json()["data"]["categories"]["items"]:
        items.extend((category.get("products") or {}).get("items", []))
    return items


def make_snapshot(store_origin: str, out_path: Path = SNAPSHOT_PATH):
    products = fetch_catalog(store_origin)
    items = build_snapshot(products)
    out_path.write_text(json.dumps(items, indent=2))
    logger.info(f"snapshot written items={len(items)} out={out_path}")
    return items


if __name__ == "__main__":
    items = make_snapshot("http://localhost:8000")
    print(f"snapshot: {len(items)} items -> {SNAPSHOT_PATH}")
