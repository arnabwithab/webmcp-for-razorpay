"""LangGraph orchestration v3 — deterministic checkout funnel (no LLM in the loop).

    START → user_turn → search-catalog → show-product → add-to-cart → read-cart → checkout → END

Each node emits its functionCall at most once per utterance (nodes whose tool already
ran in the ledger pass through), then HALTS the invoke: the browser executes the call
via WebMCP and posts /agent/turn again, advancing the funnel one step. After checkout
the funnel is closed for the utterance (spec Q2 hard end).

No router, no chat node, no Groq calls — every failure observed on 2026-09-02
(8x search loop, tool_choice:none 400s, "json"-tool hallucinations) lived in the
LLM decision layer, while the tools themselves proved flawless when driven directly.
"""

import json
import re
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, StateGraph

from agent.utils.logger import logger

# ponytail: regex filler-strip instead of an LLM call; extend it if the demo script needs more
_QUERY_FILLER = re.compile(
    r"^(please\s+)?(can\s+you\s+)?(find|show|get|search|look\s*for)(\s+(me|for))?\s+((a|an|the)\s+)?",
    re.IGNORECASE,
)


class AgentState(TypedDict):
    messages: List[Dict[str, Any]]  # full frontend history (parts-based)
    tools: List[Dict[str, Any]]  # all tool defs from the frontend
    ran: Dict[str, str]  # tool -> args-json, executed since the last user text
    result: Dict[str, Any]  # {parts: [...]} accumulated this invoke
    pending: bool  # True once a fresh functionCall awaits browser execution
    done: bool  # checkout already finished this utterance (hard end, spec Q2)


# ---------------------------------------------------------------- helpers


def _last_user_text(msgs: List[Dict[str, Any]]) -> str:
    for m in reversed(msgs):
        if m.get("role") != "user":
            continue
        for p in m.get("parts", []):
            if "text" in p:
                return p["text"].lower()
    return ""


def _seed_ran(msgs: List[Dict[str, Any]]) -> Dict[str, str]:
    """Tools already executed since the last user text (name -> args json)."""
    ran: Dict[str, str] = {}
    for m in msgs:
        if m.get("role") == "user" and any("text" in p for p in m.get("parts", [])):
            ran = {}  # fresh utterance restarts the ledger
            continue
        for p in m.get("parts", []):
            if "functionCall" in p:
                call = p["functionCall"]
                ran[call["name"].replace("_", "-")] = json.dumps(
                    call.get("args", {}), sort_keys=True
                )
    return ran


def _last_search_result(msgs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Most recent search-catalog functionResponse payload ({count, items:[...]})."""
    for m in reversed(msgs):
        if m.get("role") != "user":
            continue
        for p in m.get("parts", []):
            if "functionResponse" in p and p["functionResponse"].get("name") == "search-catalog":
                resp = p["functionResponse"].get("response") or {}
                result = resp.get("result") if isinstance(resp.get("result"), dict) else {}
                return result
    return {}


def _first_sku(result: Dict[str, Any]) -> str:
    items = result.get("items") or []
    return str(items[0].get("sku")) if items else ""


def _emit_call(state: AgentState, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    state["result"]["parts"].append({"functionCall": {"name": name, "args": args}})
    state["ran"][name] = json.dumps(args, sort_keys=True)
    state["pending"] = True
    logger.info(f"graph: emit {name} args={args}")
    return state


def _halt(state: AgentState) -> str:
    return "halt" if state.get("pending") or state.get("done") else "continue"


# ---------------------------------------------------------------- nodes


def user_turn_node(state: AgentState) -> Dict[str, Any]:
    utterance = _last_user_text(state["messages"])
    ran = _seed_ran(state["messages"])
    logger.info(f"graph: user_turn utterance={utterance[:60]!r} ran={list(ran)}")
    return {
        "ran": ran,
        "result": {"parts": []},
        "pending": False,
        "done": "checkout" in ran,  # spec Q2: hard end after checkout
    }


def search_node(state: AgentState) -> Dict[str, Any]:
    if not state["tools"]:
        state["result"]["parts"].append(
            {"text": "Store tools are still loading — try again in a moment."}
        )
        state["pending"] = True  # halt; nothing else can run this invoke
        logger.info("graph: search skip — no tools loaded in iframe yet")
        return state
    if "search-catalog" in state["ran"]:
        logger.info(f"graph: search skip — already ran args={state['ran']['search-catalog']}")
        return state
    query = _QUERY_FILLER.sub("", _last_user_text(state["messages"])).strip()
    if not query:
        logger.info("graph: search skip — no utterance text")
        return state
    return _emit_call(state, "search-catalog", {"query": query})


def show_node(state: AgentState) -> Dict[str, Any]:
    if "show-product" in state["ran"]:
        logger.info(f"graph: show skip — already ran args={state['ran']['show-product']}")
        return state
    sku = _first_sku(_last_search_result(state["messages"]))
    if not sku:
        logger.info("graph: show skip — no search result to open")
        return state
    return _emit_call(state, "show-product", {"sku": sku})


def add_node(state: AgentState) -> Dict[str, Any]:
    if "add-to-cart" in state["ran"]:
        return state
    sku = _first_sku(_last_search_result(state["messages"]))
    if not sku:
        return state
    return _emit_call(state, "add-to-cart", {"sku": sku, "qty": 1})


def read_node(state: AgentState) -> Dict[str, Any]:
    if "read-cart" in state["ran"] or "add-to-cart" not in state["ran"]:
        return state
    return _emit_call(state, "read-cart", {})


def checkout_node(state: AgentState) -> Dict[str, Any]:
    if "checkout" in state["ran"] or "add-to-cart" not in state["ran"]:
        return state
    return _emit_call(state, "checkout", {})


# ---------------------------------------------------------------- graph


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("user_turn", user_turn_node)
    g.add_node("search-catalog", search_node)
    g.add_node("show-product", show_node)
    g.add_node("add-to-cart", add_node)
    g.add_node("read-cart", read_node)
    g.add_node("checkout", checkout_node)

    g.set_entry_point("user_turn")
    funnel = [
        ("user_turn", "search-catalog"),
        ("search-catalog", "show-product"),
        ("show-product", "add-to-cart"),
        ("add-to-cart", "read-cart"),
        ("read-cart", "checkout"),
    ]
    for src, dst in funnel:
        g.add_conditional_edges(src, _halt, {"halt": END, "continue": dst})
    g.add_edge("checkout", END)
    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
