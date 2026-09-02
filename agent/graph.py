"""LangGraph orchestration — deterministic blocks per tool, router for fresh queries.

Replaces the single-shot Groq loop that let the model re-search forever.
Each tool gets its own block (exactly one tool in the Groq request), and a
lightweight router picks the block for a fresh user turn. The browser still
executes the store tools via WebMCP; this graph only decides *which* tool to
call next and returns that single tool_call/text to the frontend loop.

Multi-turn note: the frontend sends the FULL message history on every
/agent/turn (one utterance spans several calls). The router therefore looks at
the tools called *since the last user text* to advance the flow
(search-catalog → show-product) instead of re-parsing keywords forever.
"""

import re
from typing import Any, Dict, List, TypedDict

import httpx
from langgraph.graph import END, StateGraph

from agent import groq as groq_mod  # attribute access so tests can monkeypatch
from agent.groq import _from_groq, _to_groq_messages
from agent.utils.config import settings
from agent.utils.logger import logger


class AgentState(TypedDict):
    messages: List[Dict[str, Any]]  # internal parts-based messages from the frontend
    tools: List[Dict[str, Any]]  # all 6 tool defs from the frontend
    history: List[str]  # tool names called so far (logging)
    next: str  # router decision
    result: Dict[str, Any]  # final {parts: [...]}


SEARCH_HINTS = (
    "find",
    "search",
    "show me",
    "looking for",
    "bomber",
    "jacket",
    "dress",
    "kurti",
    "saree",
    "palazzo",
    "tee",
    "shirt",
    "sunglasses",
)


def _tool_available(tools: List[Dict[str, Any]], name: str) -> bool:
    return any(
        t["name"] == name or t["name"].replace("-", "_") == name.replace("-", "_") for t in tools
    )


def _last_user_text(msgs: List[Dict[str, Any]]) -> str:
    """Last user message with a text part (skips functionResponse-only messages)."""
    for m in reversed(msgs):
        if m.get("role") != "user":
            continue
        for p in m.get("parts", []):
            if "text" in p:
                return p["text"].lower()
    return ""


def _segment(msgs: List[Dict[str, Any]]):
    """Tools called since the last user text + whether the last one succeeded.

    Returns (called, last_ok): `called` is a list of tool names in order,
    `last_ok` is True/False from the last functionResponse (None if none yet).
    """
    called: List[str] = []
    last_ok = None
    for m in msgs:
        if m.get("role") == "user" and any("text" in p for p in m.get("parts", [])):
            called, last_ok = [], None  # fresh user utterance restarts the segment
            continue
        for p in m.get("parts", []):
            if "functionCall" in p:
                called.append(p["functionCall"]["name"].replace("_", "-"))
            elif "functionResponse" in p:
                resp = p["functionResponse"].get("response") or {}
                result = resp.get("result") if isinstance(resp.get("result"), dict) else {}
                last_ok = "error" not in resp and result.get("ok") is not False
    return called, last_ok


def router_node(state: AgentState) -> Dict[str, Any]:
    """Deterministic routing for demo intents + follow-up turns.

    Fresh user text:  find/show X → search-catalog; add X (to cart) → add-to-cart;
    what's in my cart → read-cart; checkout/pay → checkout; resume → resume-checkout;
    anything else → fallback text.
    Follow-up (tool already ran this utterance): advance search-catalog → show-product;
    after show-product / add-to-cart / checkout succeeded, stop with a text summary —
    never auto-chain into cart/checkout.
    """
    msgs = state["messages"]
    tools = state["tools"]

    if not tools:
        # kit not loaded in the iframe yet — answer as text, a tool call would be a
        # hallucination (log evidence: tool_use_failed with tools=[])
        nxt = "fallback"
    else:
        called, last_ok = _segment(msgs)
        if called:
            last = called[-1]
            failed = last_ok is False
            if last == "search-catalog":
                nxt = "fallback" if failed else "show-product"
            elif last == "show-product":
                # failed open (bad sku): one retry, then stop
                nxt = "show-product" if failed and called.count("show-product") < 2 else "fallback"
            elif last == "add-to-cart":
                # failure is usually 'not on the product page' — open it, then retry
                nxt = "show-product" if failed else "fallback"
            else:
                nxt = "fallback"
        else:
            text = _last_user_text(msgs)
            if any(k in text for k in ("checkout", "pay", "buy now", "place order")):
                nxt = "checkout"
            elif any(k in text for k in ("resume", "pending", "expired")):
                nxt = "resume-checkout"
            elif re.search(r"\badd\b", text):
                nxt = "add-to-cart"
            elif re.search(r"(what|show|view|read)\b.*\b(cart|bag)\b|\bin my cart\b", text):
                nxt = "read-cart"
            elif any(k in text for k in SEARCH_HINTS):
                nxt = "search-catalog"
            else:
                nxt = "fallback"

    if nxt != "fallback" and not _tool_available(tools, nxt):
        nxt = "fallback"

    logger.info(
        f"router → {nxt} for query '{_last_user_text(msgs)[:60]}' "
        f"history={state.get('history', [])}"
    )
    return {"next": nxt}


def _single_tool_call(state: AgentState, tool_name: str) -> Dict[str, Any]:
    """Call Groq with exactly one tool available, return the model's single tool_call or text."""
    tools = state["tools"]
    # find the canonical tool def (handle hyphen/underscore)
    canonical = None
    for t in tools:
        if t["name"] == tool_name or t["name"].replace("-", "_") == tool_name.replace("-", "_"):
            canonical = t
            break
    if not canonical:
        return {
            "result": {"parts": [{"text": f"Tool {tool_name} not available."}]},
            "history": state.get("history", []),
        }

    groq_tools = [
        {
            "type": "function",
            "function": {
                "name": canonical["name"],
                "description": canonical.get("description", ""),
                "parameters": canonical.get("parameters", {"type": "object", "properties": {}}),
            },
        }
    ]
    nudge = {
        "role": "system",
        "content": (
            f"Call the {canonical['name']} tool now with the right arguments from the "
            "conversation above. Use the tool results already present; never invent "
            "SKUs or prices. Use hyphenated tool names exactly as given."
        ),
    }
    body = {
        "model": settings.groq_model,
        "messages": _to_groq_messages(state["messages"]) + [nudge],
        "temperature": 0.2,
        "tools": groq_tools,
        # no tool_choice: gpt-oss-20b on Groq ignores forced choices (logs show it
        # emitting search-catalog under a forced show-product) — a nudge plus a
        # single registered tool is the reliable constraint
    }
    try:
        raw = groq_mod.generate_turn({"request_body": body})
    except httpx.HTTPStatusError as err:  # tool_use_failed 400 — one clean retry
        logger.warning(f"single-tool {tool_name} 400, retrying once: {err.response.text[:200]}")
        raw = groq_mod.generate_turn({"request_body": body})
    msg = raw.get("choices", [{}])[0].get("message", {})
    result = _from_groq(msg)
    # _from_groq returns {parts: [...]}, ensure at least one part
    if not result.get("parts"):
        result = {"parts": [{"text": msg.get("content") or "Done."}]}
    return {"result": result, "history": state.get("history", []) + [tool_name]}


def search_node(state: AgentState) -> Dict[str, Any]:
    return _single_tool_call(state, "search-catalog")


def show_node(state: AgentState) -> Dict[str, Any]:
    return _single_tool_call(state, "show-product")


def add_node(state: AgentState) -> Dict[str, Any]:
    return _single_tool_call(state, "add-to-cart")


def read_node(state: AgentState) -> Dict[str, Any]:
    return _single_tool_call(state, "read-cart")


def checkout_node(state: AgentState) -> Dict[str, Any]:
    return _single_tool_call(state, "checkout")


def resume_node(state: AgentState) -> Dict[str, Any]:
    return _single_tool_call(state, "resume-checkout")


def fallback_node(state: AgentState) -> Dict[str, Any]:
    """No tool next — answer as text. No tools are offered and validation stays on;
    disable_tool_validation with an empty tool list is what let the model emit
    hallucinated tool JSON and 400 the whole turn."""
    body = {
        "model": settings.groq_model,
        "messages": _to_groq_messages(state["messages"])
        + [
            {
                "role": "system",
                "content": "Reply to the user in one short sentence based on the "
                "conversation above. Do not call any tools.",
            }
        ],
        "temperature": 0.2,
    }
    raw = groq_mod.generate_turn({"request_body": body})
    msg = raw.get("choices", [{}])[0].get("message", {})
    result = _from_groq(msg)
    if not result.get("parts"):
        result = {
            "parts": [{"text": msg.get("content") or "I can only help you shop on this store."}]
        }
    return {"result": result}


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("router", router_node)
    g.add_node("search-catalog", search_node)
    g.add_node("show-product", show_node)
    g.add_node("add-to-cart", add_node)
    g.add_node("read-cart", read_node)
    g.add_node("checkout", checkout_node)
    g.add_node("resume-checkout", resume_node)
    g.add_node("fallback", fallback_node)

    g.set_entry_point("router")
    # conditional edges ONLY — an extra unconditional edge made the fallback node
    # run in parallel with every routed block (duplicate Groq calls + 400s)
    g.add_conditional_edges(
        "router",
        lambda s: s["next"],
        {
            "search-catalog": "search-catalog",
            "show-product": "show-product",
            "add-to-cart": "add-to-cart",
            "read-cart": "read-cart",
            "checkout": "checkout",
            "resume-checkout": "resume-checkout",
            "fallback": "fallback",
        },
    )
    for n in [
        "search-catalog",
        "show-product",
        "add-to-cart",
        "read-cart",
        "checkout",
        "resume-checkout",
        "fallback",
    ]:
        g.add_edge(n, END)
    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
