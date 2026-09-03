"""LLM-driven WebMCP checkout loop (spec §5-§7).

One /agent/turn = one Groq tool-use decision that the browser executes via WebMCP,
then posts the functionResponse and asks for the next call. The Groq call always
carries the real tool list (disable_tool_validation, no forced tool_choice) so the
model never hallucinates an unregistered tool → 400 (HANDOFF §6b).

The backend guards the data + ordering a stateless model can't be trusted with:
  - checkout already ran → spec Q2 hard end: only recovery (resume-checkout) is
    allowed; anything else collapses to the "Payment link is ready" line.
  - show-product / add-to-cart need a real search result: their sku is injected
    from result.items[0].sku (never a hallucinated one); if no search ran yet, a
    search-catalog call is emitted first (LLM keywords, regex fallback).
  - search-catalog / read-cart / checkout / resume-checkout pass through.
"""

import json
import re
from typing import Any, Dict, List

from agent.groq import _from_groq, _to_groq_messages, generate_turn
from agent.utils.config import settings
from agent.utils.logger import logger

# ponytail: regex filler-strip only as a *fallback* when the model jumps to
# show/add before searching; the primary keyword extraction is the LLM's own.
_QUERY_FILLER = re.compile(
    r"^(please\s+)?(can\s+you\s+)?(find|show|get|search|look\s*for)(\s+(me|for))?\s+((a|an|the)\s+)?",
    re.IGNORECASE,
)

_PAYMENT_LINE = "Payment link is ready — click Open payment to pay."


# ---------------------------------------------------------------- history helpers


def _last_user_text(msgs: List[Dict[str, Any]]) -> str:
    for m in reversed(msgs):
        if m.get("role") != "user":
            continue
        for p in m.get("parts", []):
            if "text" in p:
                return p["text"].lower()
    return ""


def _latest_response(msgs: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    """Latest functionResponse payload ({result}) for a tool, json.loads-ing
    stringified results (native WebMCP returns the tool result as a string)."""
    for m in reversed(msgs):
        for p in m.get("parts", []):
            if "functionResponse" in p and p["functionResponse"].get("name") == name:
                resp = p["functionResponse"].get("response") or {}
                result = resp.get("result")
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except json.JSONDecodeError:
                        result = {}
                return result if isinstance(result, dict) else {}
    return {}


def _first_sku(result: Dict[str, Any]) -> str:
    items = result.get("items") or []
    return str(items[0].get("sku")) if items else ""


def _all_search_items(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """All items from all search-catalog responses in order."""
    out: List[Dict[str, Any]] = []
    for m in messages:
        for p in m.get("parts", []):
            if "functionResponse" in p and p["functionResponse"].get("name") == "search-catalog":
                resp = p["functionResponse"].get("response") or {}
                result = resp.get("result")
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except json.JSONDecodeError:
                        result = {}
                if isinstance(result, dict):
                    out.extend(result.get("items") or [])
    return out


def _added_skus(messages: List[Dict[str, Any]]) -> set:
    return {
        p["functionCall"]["args"].get("sku")
        for m in messages
        for p in m.get("parts", [])
        if "functionCall" in p and p["functionCall"].get("name") == "add-to-cart"
    }


def _next_sku(messages: List[Dict[str, Any]]) -> str:
    """First SKU from search results not yet added."""
    added = _added_skus(messages)
    for it in _all_search_items(messages):
        sku = str(it.get("sku") or "")
        if sku and sku not in added:
            return sku
    return _first_sku(_latest_response(messages, "search-catalog"))


def _has_call(msgs: List[Dict[str, Any]], name: str) -> bool:
    return any(
        p.get("functionCall", {}).get("name") == name
        for m in msgs
        for p in m.get("parts", [])
        if "functionCall" in p
    )


# ---------------------------------------------------------------- Groq request build


def _tools_to_groq(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Frontend {name, description, parameters|inputSchema} -> OpenAI tools list."""
    out = []
    for t in tools:
        schema = t.get("parameters") or t.get("inputSchema") or {"type": "object"}
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except json.JSONDecodeError:
                schema = {"type": "object"}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": schema,
                },
            }
        )
    return out


def _call_groq(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One Groq call → the internal parts list for this turn."""
    body = {
        "model": settings.groq_model,
        "messages": _to_groq_messages(messages),
        "tools": _tools_to_groq(tools),
        "disable_tool_validation": True,  # no forced tool_choice — that 400s on Groq
    }
    logger.info(
        f"graph: groq msgs={len(body['messages'])} "
        f"tools={[t['function']['name'] for t in body['tools']]}"
    )
    data = generate_turn({"request_body": body})
    return _from_groq(data["choices"][0]["message"])["parts"]


# ---------------------------------------------------------------- recovery (Track 03)


def _maybe_resume(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    """After checkout: the funnel is closed (spec Q2). The only action still allowed
    is recovery — resume-checkout for a pending/declined payment. Anything else
    (including a duplicate checkout) collapses to the payment line."""
    parts = _call_groq(messages, tools)
    call = parts[0].get("functionCall") if parts else None
    if call and call["name"] == "resume-checkout":
        logger.info("graph: recovery → resume-checkout")
        return {
            "parts": [{"functionCall": {"name": "resume-checkout", "args": call.get("args") or {}}}]
        }
    return {"parts": [{"text": _PAYMENT_LINE}]}


# ---------------------------------------------------------------- main decision


def decide_turn(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One LLM tool-use decision for /agent/turn. Returns {"parts": [...]}."""
    if not tools:
        logger.info("graph: no tools loaded in iframe")
        return {"parts": [{"text": "Store tools are still loading — try again in a moment."}]}

    # Spec Q2 hard end: after a payment tool the funnel is closed. resume-checkout
    # (recovery) is allowed once; after that, only the payment line.
    if _has_call(messages, "resume-checkout"):
        logger.info("graph: recovery completed — hard end")
        return {"parts": [{"text": _PAYMENT_LINE}]}
    if _has_call(messages, "checkout"):
        return _maybe_resume(messages, tools)

    parts = _call_groq(messages, tools)
    call = parts[0].get("functionCall") if parts else None
    if not call:
        return {"parts": parts}  # text-only reply

    name = call["name"]
    args = dict(call.get("args") or {})
    search = _latest_response(messages, "search-catalog")
    sku = _first_sku(search)

    # Ordering guardrail: show/add need a real search result first.
    if name in ("show-product", "add-to-cart") and not sku:
        query = _QUERY_FILLER.sub("", _last_user_text(messages)).strip() or args.get("query") or ""
        logger.info(f"graph: force search-first for {name}")
        return {"parts": [{"functionCall": {"name": "search-catalog", "args": {"query": query}}}]}

    if name == "checkout":
        # never checkout before the cart has items — force the missing step
        has_add = _has_call(messages, "add-to-cart")
        cart = _latest_response(messages, "read-cart")
        cart_qty = cart.get("totalQty", 0) if isinstance(cart, dict) else 0
        if not has_add and cart_qty == 0:
            if not sku:
                query = (
                    _QUERY_FILLER.sub("", _last_user_text(messages)).strip()
                    or args.get("query")
                    or ""
                )
                logger.info("graph: force search-first for checkout (no cart)")
                return {
                    "parts": [
                        {"functionCall": {"name": "search-catalog", "args": {"query": query}}}
                    ]
                }
            nxt = _next_sku(messages)
            if nxt:
                logger.info("graph: force add-first for checkout")
                return {
                    "parts": [
                        {"functionCall": {"name": "add-to-cart", "args": {"sku": nxt, "qty": 1}}}
                    ]
                }
            logger.info("graph: force add-first for checkout (fallback)")
            return {
                "parts": [{"functionCall": {"name": "add-to-cart", "args": {"sku": sku, "qty": 1}}}]
            }

    if name == "show-product":
        # for multi-item carts, pick the next SKU not yet shown
        shown_skus = {
            p["functionCall"]["args"].get("sku")
            for m in messages
            for p in m.get("parts", [])
            if "functionCall" in p and p["functionCall"].get("name") == "show-product"
        }
        nxt = _next_sku(messages)
        if nxt and nxt not in shown_skus:
            args["sku"] = nxt
        else:
            args["sku"] = sku  # fallback to first
    elif name == "add-to-cart":
        nxt = _next_sku(messages)
        if nxt:
            args["sku"] = nxt
        else:
            shown = _latest_response(messages, "show-product")
            args["sku"] = str(shown.get("sku")) or sku
        args.setdefault("qty", 1)

    parts[0] = {"functionCall": {"name": name, "args": args}}
    logger.info(f"graph: emit {name} args={args}")
    return {"parts": parts}
