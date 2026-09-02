import pytest
from fastapi.testclient import TestClient

from agent.app import app


@pytest.fixture()
def client():
    return TestClient(app)


def _tools(*names):
    return [
        {"name": n, "description": f"{n} desc", "parameters": {"type": "object"}} for n in names
    ]


def _resp(name, result):
    """A user message carrying one functionResponse part."""
    return {
        "role": "user",
        "parts": [{"functionResponse": {"name": name, "response": {"result": result}}}],
    }  # noqa: E501


def _call(name, args):
    """A model message carrying one functionCall part."""
    return {"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}


ITEMS = {"ok": True, "count": 1, "items": [{"sku": "NJ-01", "name": "Red Jersey", "url": "/x"}]}


def test_fresh_turn_emits_search_call(client):
    """Fresh utterance → the funnel emits exactly one search-catalog call."""
    resp = client.post(
        "/agent/turn",
        json={
            "messages": [{"role": "user", "parts": [{"text": "find a red jersey"}]}],
            "tools": _tools("search-catalog", "show-product", "add-to-cart"),
        },
    )
    assert resp.status_code == 200
    parts = resp.json()["parts"]
    assert len(parts) == 1
    call = parts[0]["functionCall"]
    assert call["name"] == "search-catalog"
    assert "jersey" in call["args"]["query"]


def test_after_search_emits_show_call(client):
    """search-catalog done → next turn emits show-product with the found sku."""
    messages = [
        {"role": "user", "parts": [{"text": "find a red jersey"}]},
        _call("search-catalog", {"query": "red jersey"}),
        _resp("search-catalog", ITEMS),
    ]
    resp = client.post(
        "/agent/turn",
        json={"messages": messages, "tools": _tools("search-catalog", "show-product")},
    )
    assert resp.status_code == 200
    parts = resp.json()["parts"]
    assert len(parts) == 1
    call = parts[0]["functionCall"]
    assert call["name"] == "show-product"
    assert call["args"]["sku"] == "NJ-01"


def test_after_show_emits_add(client):
    """search+show done → the funnel adds the shown sku to the cart."""
    messages = [
        {"role": "user", "parts": [{"text": "find a red jersey"}]},
        _call("search-catalog", {"query": "red jersey"}),
        _resp("search-catalog", ITEMS),
        _call("show-product", {"sku": "NJ-01"}),
        _resp("show-product", {"ok": True, "sku": "NJ-01"}),
    ]
    resp = client.post(
        "/agent/turn",
        json={
            "messages": messages,
            "tools": _tools("search-catalog", "show-product", "add-to-cart"),
        },
    )
    assert resp.status_code == 200
    call = resp.json()["parts"][0]["functionCall"]
    assert call["name"] == "add-to-cart"
    assert call["args"] == {"sku": "NJ-01", "qty": 1}


def test_after_add_emits_read_cart(client):
    messages = [
        {"role": "user", "parts": [{"text": "find a red jersey"}]},
        _call("search-catalog", {"query": "red jersey"}),
        _resp("search-catalog", ITEMS),
        _call("show-product", {"sku": "NJ-01"}),
        _resp("show-product", {"ok": True, "sku": "NJ-01"}),
        _call("add-to-cart", {"sku": "NJ-01", "qty": 1}),
        _resp("add-to-cart", {"ok": True, "cartCount": 1}),
    ]
    resp = client.post(
        "/agent/turn",
        json={"messages": messages, "tools": _tools("search-catalog", "read-cart")},
    )
    assert resp.status_code == 200
    assert resp.json()["parts"][0]["functionCall"]["name"] == "read-cart"


def test_after_read_emits_checkout(client):
    messages = [
        {"role": "user", "parts": [{"text": "find a red jersey"}]},
        _call("search-catalog", {"query": "red jersey"}),
        _resp("search-catalog", ITEMS),
        _call("show-product", {"sku": "NJ-01"}),
        _resp("show-product", {"ok": True, "sku": "NJ-01"}),
        _call("add-to-cart", {"sku": "NJ-01", "qty": 1}),
        _resp("add-to-cart", {"ok": True, "cartCount": 1}),
        _call("read-cart", {}),
        _resp("read-cart", {"ok": True, "totalQty": 1, "grandTotal": 2499}),
    ]
    resp = client.post(
        "/agent/turn",
        json={"messages": messages, "tools": _tools("search-catalog", "checkout")},
    )
    assert resp.status_code == 200
    assert resp.json()["parts"][0]["functionCall"]["name"] == "checkout"


def test_checkout_hard_ends(client):
    """Q2: after checkout runs, the funnel is closed — payment text, no further calls."""
    messages = [
        {"role": "user", "parts": [{"text": "checkout"}]},
        _call("search-catalog", {"query": "checkout"}),
        _resp("search-catalog", {"ok": True, "count": 0, "items": []}),
        _call("checkout", {}),
        _resp("checkout", {"ok": True, "linkId": "plink_1", "shortUrl": "https://rzp.io/i/1"}),
    ]
    resp = client.post(
        "/agent/turn",
        json={"messages": messages, "tools": _tools("search-catalog", "checkout")},
    )
    assert resp.status_code == 200
    parts = resp.json()["parts"]
    assert not any("functionCall" in p for p in parts)
    assert "Payment link is ready" in parts[0]["text"]


def test_empty_search_ends_without_calls(client):
    """Search found nothing → funnel passes through, no calls, generic fallback text."""
    messages = [
        {"role": "user", "parts": [{"text": "find a red jersey"}]},
        _call("search-catalog", {"query": "red jersey"}),
        _resp("search-catalog", {"ok": True, "count": 0, "items": []}),
    ]
    resp = client.post(
        "/agent/turn",
        json={"messages": messages, "tools": _tools("search-catalog", "show-product")},
    )
    assert resp.status_code == 200
    parts = resp.json()["parts"]
    assert not any("functionCall" in p for p in parts)
    assert "couldn't take that further" in parts[0]["text"]


def test_no_tools_halts_with_loading_text(client):
    """tools=[] (stale iframe) → visible loading text, never a crash."""
    resp = client.post(
        "/agent/turn",
        json={"messages": [{"role": "user", "parts": [{"text": "hi"}]}], "tools": []},
    )
    assert resp.status_code == 200
    assert "still loading" in resp.json()["parts"][0]["text"]


def test_search_query_strips_command_filler(client):
    """Raw utterances make bad EverShop keyword queries — strip 'find me a' etc."""
    resp = client.post(
        "/agent/turn",
        json={
            "messages": [{"role": "user", "parts": [{"text": "find me a rust bomber jacket"}]}],
            "tools": _tools("search-catalog"),
        },
    )
    call = resp.json()["parts"][0]["functionCall"]
    assert call["args"]["query"] == "rust bomber jacket"


def test_never_leaks_key(client):
    resp = client.post(
        "/agent/turn",
        json={"messages": [{"role": "user", "parts": [{"text": "hi"}]}], "tools": []},
    )
    assert "gsk_" not in resp.text


def test_agent_panel_served(client):
    resp = client.get("/agent")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "/static/agent.js" in resp.text


def test_agent_js_and_loader_served(client):
    js = client.get("/static/agent.js")
    assert js.status_code == 200
    assert "getTools" in js.text
    loader = client.get("/static/loader.js")
    assert loader.status_code == 200  # spec §5: agent backend serves the loader
    assert "razorpay-agent-kit" in loader.text


def test_cors_store_origin_only(client):
    resp = client.options(
        "/agent/turn",
        headers={"Origin": "http://localhost:8000", "Access-Control-Request-Method": "POST"},
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:8000"
