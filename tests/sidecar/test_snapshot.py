import json

from sidecar.snapshot import build_snapshot

# EverShop /api/graphql shape: price.regular.value, INR-native catalog
PRODUCTS = [
    {
        "product_id": 1,
        "name": "Kids Printed Tee",
        "sku": "FASH-K01",
        "price": {"regular": {"value": 399, "currency": "INR"}},
        "variants": [],
    },
    {
        "product_id": 2,
        "name": "Art Silk Saree",
        "sku": "FASH-W06",
        "price": None,
        "variants": [
            {"sku": "FASH-W06-RED", "price": 2999},
            {"sku": "FASH-W06-BLUE", "price": 3199},
        ],
    },
]


def test_build_snapshot_inr_paise():
    items = build_snapshot(PRODUCTS)
    by_sku = {i["sku"]: i for i in items}
    assert by_sku["FASH-K01"]["pricePaise"] == 39900
    assert by_sku["FASH-K01"]["priceInrLabel"] == "₹399.00"
    assert by_sku["FASH-K01"]["priceSource"] == {"value": 399, "currency": "INR"}


def test_build_snapshot_uses_min_variant_price_when_product_price_missing():
    items = build_snapshot(PRODUCTS)
    by_sku = {i["sku"]: i for i in items}
    assert by_sku["FASH-W06"]["pricePaise"] == 299900


def test_build_snapshot_is_stable_json():
    items1 = build_snapshot(PRODUCTS)
    items2 = build_snapshot(PRODUCTS)
    assert json.dumps(items1) == json.dumps(items2)
