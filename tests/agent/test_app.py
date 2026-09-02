"""Agent /agent/turn tests — LLM-driven WebMCP checkout loop (spec §5-§7).

The backend is stateless: one /agent/turn = one Groq tool-use decision that the
browser executes via WebMCP, then posts the functionResponse and asks for the next
call. Groq is mocked here; the tests assert the *driving* logic (keyword passing,
sku injection from result.items[0].sku, ordering guardrails, checkout hard-end,
recovery) and the Groq request shape (disable_tool_validation, real tools, no
forced tool_choice).
"""

import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from agent.app import app


@pytest.fixture()
def client():
    return TestClient(app)


def _tools(*names):
    return [
        {
            "name": n,
            "description": f"{n} desc",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        }
        for n in names
    ]


def _resp(name, result):
    """A user message carrying one functionResponse part."""
    return {
        "role": "user",
        "parts": [{"functionResponse": {"name": name, "response": {"result": result}}}],
    }


def _call(name, args):
    """A model message carrying one functionCall part."""
    return {"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}


def _groq_tool(name, args):
    """A canned Groq response asking the model to call one tool."""
    return {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)},
                        }
                    ],
                }
            }
        ]
    }


def _groq_text(text):
    """A canned Groq response that is text-only (no tool call)."""
    return {"choices": [{"message": {"content": text, "tool_calls": None}}]}


ITEMS = {"ok": True, "count": 1, "items": [{"sku": "NJ-01", "name": "Red Jersey", "url": "/x"}]}


# ---------------------------------------------------------------- LLM-driven search


@mock.patch("agent.graph.generate_turn")
def test_fresh_utterance_emits_llm_extracted_search(gen, client):
    """A fresh utterance → the LLM decides search-catalog with extracted keywords,
    not the raw utterance (this is the 'dress under 2000' fix)."""
    gen.return_value = _groq_tool("search-catalog", {"query": "rust bomber jacket"})
    resp = client.post(
        "/agent/turn",
        json={
            "messages": [
                {"role": "user", "parts": [{"text": "find me a rust bomber jacket under 2000"}]}
            ],
            "tools": _tools("search-catalog", "show-product", "add-to-cart", "checkout"),
        },
    )
    assert resp.status_code == 200
    call = resp.json()["parts"][0]["functionCall"]
    assert call["name"] == "search-catalog"
    assert call["args"]["query"] == "rust bomber jacket"


@mock.patch("agent.graph.generate_turn")
def test_short_budget_utterance_passes_llm_keywords(gen, client):
    """'dress under 2000' → LLM extracts 'dress' (no regex strip on the search path)."""
    gen.return_value = _groq_tool("search-catalog", {"query": "dress"})
    resp = client.post(
        "/agent/turn",
        json={
            "messages": [{"role": "user", "parts": [{"text": "dress under 2000"}]}],
            "tools": _tools("search-catalog"),
        },
    )
    call = resp.json()["parts"][0]["functionCall"]
    assert call["args"]["query"] == "dress"


# ---------------------------------------------------------------- Groq request shape


@mock.patch("agent.graph.generate_turn")
def test_groq_body_has_tools_and_disables_validation(gen, client):
    """The Groq request carries the real tool list + disable_tool_validation, and
    never forces a tool_choice (a forced tool_choice 400s on Groq, HANDOFF §6b)."""
    captured = {}

    def fake(payload):
        captured.update(payload["request_body"])
        return _groq_tool("search-catalog", {"query": "dress"})

    gen.side_effect = fake
    client.post(
        "/agent/turn",
        json={
            "messages": [{"role": "user", "parts": [{"text": "dress under 2000"}]}],
            "tools": _tools("search-catalog", "checkout"),
        },
    )
    assert captured["disable_tool_validation"] is True
    assert "tool_choice" not in captured
    assert [t["function"]["name"] for t in captured["tools"]] == ["search-catalog", "checkout"]
    # OpenAI function schema from the frontend's `parameters`
    assert captured["tools"][0]["function"]["parameters"]["type"] == "object"


@mock.patch("agent.graph.generate_turn")
def test_groq_body_falls_back_to_input_schema(gen, client):
    """Tools that only carry `inputSchema` (native WebMCP) still serialize to LLM tools."""
    captured = {}

    def fake(payload):
        captured.update(payload["request_body"])
        return _groq_tool("search-catalog", {"query": "dress"})

    gen.side_effect = fake
    client.post(
        "/agent/turn",
        json={
            "messages": [{"role": "user", "parts": [{"text": "dress"}]}],
            "tools": [{"name": "search-catalog", "inputSchema": {"type": "object"}}],
        },
    )
    assert captured["tools"][0]["function"]["parameters"]["type"] == "object"


# ---------------------------------------------------------------- sku injection + ordering


@mock.patch("agent.graph.generate_turn")
def test_show_product_sku_injected_from_search_result(gen, client):
    """show-product's sku comes from result.items[0].sku, never a hallucinated one."""
    gen.return_value = _groq_tool("show-product", {"sku": "MADE-UP-SKU"})
    messages = [
        {"role": "user", "parts": [{"text": "find a red jersey"}]},
        _call("search-catalog", {"query": "red jersey"}),
        _resp("search-catalog", ITEMS),
    ]
    resp = client.post("/agent/turn", json={"messages": messages, "tools": _tools("show-product")})
    call = resp.json()["parts"][0]["functionCall"]
    assert call["name"] == "show-product"
    assert call["args"]["sku"] == "NJ-01"


@mock.patch("agent.graph.generate_turn")
def test_add_to_cart_before_search_forces_search_first(gen, client):
    """If the model jumps to add-to-cart before any search ran, the backend emits
    search-catalog first (LLM keywords, regex fallback)."""
    gen.return_value = _groq_tool("add-to-cart", {"sku": "X", "qty": 1})
    resp = client.post(
        "/agent/turn",
        json={
            "messages": [{"role": "user", "parts": [{"text": "find a red jersey"}]}],
            "tools": _tools("search-catalog", "add-to-cart"),
        },
    )
    call = resp.json()["parts"][0]["functionCall"]
    assert call["name"] == "search-catalog"
    assert "jersey" in call["args"]["query"]


@mock.patch("agent.graph.generate_turn")
def test_add_to_cart_uses_shown_sku(gen, client):
    """After show-product, add-to-cart's sku is corrected to the shown product's sku."""
    gen.return_value = _groq_tool("add-to-cart", {"sku": "BAD", "qty": 1})
    messages = [
        {"role": "user", "parts": [{"text": "find a red jersey"}]},
        _call("search-catalog", {"query": "red jersey"}),
        _resp("search-catalog", ITEMS),
        _call("show-product", {"sku": "NJ-01"}),
        _resp("show-product", {"ok": True, "sku": "NJ-01", "name": "Red Jersey"}),
    ]
    resp = client.post("/agent/turn", json={"messages": messages, "tools": _tools("add-to-cart")})
    call = resp.json()["parts"][0]["functionCall"]
    assert call["name"] == "add-to-cart"
    assert call["args"]["sku"] == "NJ-01"


@mock.patch("agent.graph.generate_turn")
def test_stringified_search_result_still_injects_sku(gen, client):
    """Native WebMCP returns the tool result as a JSON string — json.loads handles it."""
    gen.return_value = _groq_tool("show-product", {"sku": "MADE-UP"})
    messages = [
        {"role": "user", "parts": [{"text": "find a red jersey"}]},
        _call("search-catalog", {"query": "red jersey"}),
        _resp("search-catalog", json.dumps(ITEMS)),
    ]
    resp = client.post("/agent/turn", json={"messages": messages, "tools": _tools("show-product")})
    call = resp.json()["parts"][0]["functionCall"]
    assert call["args"]["sku"] == "NJ-01"


# ---------------------------------------------------------------- checkout hard-end + recovery


@mock.patch("agent.graph.generate_turn")
def test_checkout_hard_ends_with_payment_text(gen, client):
    """Spec Q2: after checkout ran, the funnel is closed — payment text, no further calls."""
    gen.return_value = _groq_text("Click Open payment to pay.")
    messages = [
        {"role": "user", "parts": [{"text": "checkout"}]},
        _call("search-catalog", {"query": "jersey"}),
        _resp("search-catalog", ITEMS),
        _call("checkout", {}),
        _resp("checkout", {"ok": True, "linkId": "plink_1", "shortUrl": "https://rzp.io/i/1"}),
    ]
    resp = client.post("/agent/turn", json={"messages": messages, "tools": _tools("checkout")})
    assert resp.status_code == 200
    parts = resp.json()["parts"]
    assert not any("functionCall" in p for p in parts)
    assert "Payment link is ready" in parts[0]["text"]


@mock.patch("agent.graph.generate_turn")
def test_checkout_suppresses_duplicate_checkout_after_done(gen, client):
    """After checkout, the model cannot call checkout again — only payment text."""
    gen.return_value = _groq_tool("checkout", {})
    messages = [
        {"role": "user", "parts": [{"text": "checkout"}]},
        _call("search-catalog", {"query": "jersey"}),
        _resp("search-catalog", ITEMS),
        _call("checkout", {}),
        _resp("checkout", {"ok": True, "linkId": "plink_1", "shortUrl": "https://rzp.io/i/1"}),
    ]
    resp = client.post("/agent/turn", json={"messages": messages, "tools": _tools("checkout")})
    parts = resp.json()["parts"]
    assert not any("functionCall" in p for p in parts)
    assert "Payment link is ready" in parts[0]["text"]


@mock.patch("agent.graph.generate_turn")
def test_resume_checkout_for_recovery(gen, client):
    """Track 03: after checkout with a pending/declined payment, the model may call
    resume-checkout for recovery (re-opens or mints a fresh link)."""
    gen.return_value = _groq_tool("resume-checkout", {"linkId": "plink_1"})
    messages = [
        {"role": "user", "parts": [{"text": "payment is pending — resume"}]},
        _call("checkout", {}),
        _resp(
            "checkout",
            {
                "ok": True,
                "linkId": "plink_1",
                "shortUrl": "https://rzp.io/i/1",
                "status": "pending",
            },
        ),
    ]
    resp = client.post(
        "/agent/turn", json={"messages": messages, "tools": _tools("resume-checkout")}
    )
    call = resp.json()["parts"][0]["functionCall"]
    assert call["name"] == "resume-checkout"
    assert call["args"]["linkId"] == "plink_1"


@mock.patch("agent.graph.generate_turn")
def test_recovery_completed_hard_ends(gen, client):
    """Once resume-checkout has run, the funnel is fully closed — payment text, no Groq."""
    messages = [
        {"role": "user", "parts": [{"text": "payment pending, resume"}]},
        _call("checkout", {}),
        _resp(
            "checkout",
            {
                "ok": True,
                "linkId": "plink_1",
                "shortUrl": "https://rzp.io/i/1",
                "status": "pending",
            },
        ),
        _call("resume-checkout", {"linkId": "plink_1"}),
        _resp(
            "resume-checkout", {"ok": True, "shortUrl": "https://rzp.io/i/1", "status": "pending"}
        ),
    ]
    resp = client.post(
        "/agent/turn", json={"messages": messages, "tools": _tools("resume-checkout")}
    )
    parts = resp.json()["parts"]
    assert not any("functionCall" in p for p in parts)
    assert "Payment link is ready" in parts[0]["text"]
    gen.assert_not_called()


# ---------------------------------------------------------------- text / edge cases


@mock.patch("agent.graph.generate_turn")
def test_llm_text_only_returns_text(gen, client):
    gen.return_value = _groq_text("I can only help you shop on this store.")
    resp = client.post(
        "/agent/turn",
        json={
            "messages": [{"role": "user", "parts": [{"text": "what's the weather?"}]}],
            "tools": _tools("search-catalog"),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["parts"][0]["text"] == "I can only help you shop on this store."


def test_no_tools_halts_with_loading_text(client):
    """tools=[] (stale iframe) → visible loading text, never a crash or Groq call."""
    resp = client.post(
        "/agent/turn",
        json={"messages": [{"role": "user", "parts": [{"text": "hi"}]}], "tools": []},
    )
    assert resp.status_code == 200
    assert "still loading" in resp.json()["parts"][0]["text"]


def test_never_leaks_key(client):
    resp = client.post(
        "/agent/turn",
        json={"messages": [{"role": "user", "parts": [{"text": "hi"}]}], "tools": []},
    )
    assert "gsk_" not in resp.text


# ---------------------------------------------------------------- static + CORS


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
