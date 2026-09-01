import json

from sidecar.snapshot import build_snapshot

# EverShop /api/graphql shape: price.regular.value on product
PRODUCTS = [
    {
        "product_id": 1,
        "name": "Nike Jersey",
        "sku": "NJ-01",
        "price": {"regular": {"value": 10.0, "currency": "USD"}},
        "variants": [],
    },
    {
        "product_id": 2,
        "name": "Sneakers",
        "sku": "SK-02",
        "price": None,
        "variants": [{"sku": "SK-02-M", "price": 50.0}, {"sku": "SK-02-L", "price": 55.0}],
    },
]


def test_build_snapshot_relabels_inr_fixed_rate():
    items = build_snapshot(PRODUCTS, usd_to_inr=83.0)
    by_sku = {i["sku"]: i for i in items}
    assert by_sku["NJ-01"]["pricePaise"] == 83000  # 10 USD * 83 * 100
    assert by_sku["NJ-01"]["priceInrLabel"] == "₹830.00"
    assert by_sku["NJ-01"]["priceSource"] == {"value": 10.0, "currency": "USD"}


def test_build_snapshot_uses_min_variant_price_when_product_price_missing():
    items = build_snapshot(PRODUCTS, usd_to_inr=83.0)
    by_sku = {i["sku"]: i for i in items}
    assert by_sku["SK-02"]["pricePaise"] == 415000  # min(50, 55) USD


def test_build_snapshot_is_stable_json():
    items1 = build_snapshot(PRODUCTS, usd_to_inr=83.0)
    items2 = build_snapshot(PRODUCTS, usd_to_inr=83.0)
    assert json.dumps(items1) == json.dumps(items2)
