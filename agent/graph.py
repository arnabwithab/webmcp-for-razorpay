"""LangGraph orchestration — deterministic blocks per tool, router for fresh queries.

Replaces the single-shot Groq loop that let the model re-search forever.
Each tool gets its own block (exactly one tool in the Groq request), and a
lightweight router picks the block for a fresh user turn. The browser still
executes the store tools via WebMCP; this graph only decides *which* tool to
call next and returns that single tool_call/text to the frontend loop.
"""

from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, StateGraph

from agent.groq import _from_groq, _to_groq_messages
from agent.groq import generate_turn as _generate_turn
from agent.utils.config import settings
from agent.utils.logger import logger


class AgentState(TypedDict):
    messages: List[Dict[str, Any]]  # internal parts-based messages from the frontend
    tools: List[Dict[str, Any]]  # all 6 tool defs from the frontend
    history: List[str]  # tool names already called with same args (for loop guard)
    next: str  # router decision
    result: Dict[str, Any]  # final {parts: [...]}


def _tool_available(tools: List[Dict[str, Any]], name: str) -> bool:
    return any(
        t["name"] == name or t["name"].replace("-", "_") == name.replace("-", "_") for t in tools
    )


def router_node(state: AgentState) -> Dict[str, Any]:
    """Deterministic router for fresh user queries + simple history guard.

    Priority for a fresh user turn:
      find/search/show/bomber/jacket/dress/kurti/saree → search-catalog
      add to cart / add → add-to-cart (requires prior show, but we let the tool
        itself return 'call show-product first' if needed — visible, not a loop)
      cart / what.*cart → read-cart
      checkout / pay / buy → checkout
      resume / pending / expired → resume-checkout
    If the last turn was a search with same query, force show-product instead
    of re-searching (loop guard).
    """
    msgs = state["messages"]
    tools = state["tools"]
    history = state.get("history", [])

    # find last user text
    last_user = ""
    for m in reversed(msgs):
        if m.get("role") == "user":
            for p in m.get("parts", []):
                if "text" in p:
                    last_user = p["text"].lower()
                    break
            if last_user:
                break

    # loop guard: if we just did search-catalog with same query, don't search again
    # history is list of "tool:arg_hash" — for now just tool names
    last_tool = history[-1] if history else None
    if last_tool == "search-catalog" and any(
        k in last_user for k in ["bomber", "jacket", "dress", "kurti", "saree", "palazzo"]
    ):
        # we already searched, next should be show — but router only runs on
        # fresh user turns; the LLM block itself will decide. For fresh turns,
        # prefer search only if no search in history for this query.
        pass

    # fresh query routing
    text = last_user
    if any(k in text for k in ["checkout", "pay", "buy now", "place order"]):
        nxt = "checkout" if _tool_available(tools, "checkout") else "search-catalog"
    elif any(k in text for k in ["resume", "pending", "expired"]):
        nxt = "resume-checkout"
    elif any(k in text for k in ["cart", "what.*in.*cart", "show cart"]):
        nxt = "read-cart"
    elif any(
        k in text
        for k in [
            "find",
            "search",
            "show",
            "bomber",
            "jacket",
            "dress",
            "kurti",
            "saree",
            "palazzo",
            "tee",
            "shirt",
            "sunglasses",
        ]
    ):
        nxt = "search-catalog"
    elif len(msgs) == 1:  # first turn, no history
        nxt = "search-catalog"
    else:
        nxt = "search-catalog"  # default

    # if the chosen tool just ran last turn, advance one step (search→show, show→add)
    if history and history[-1] == nxt:
        order = ["search-catalog", "show-product", "add-to-cart", "read-cart", "checkout"]
        try:
            idx = order.index(nxt)
            if idx + 1 < len(order) and _tool_available(tools, order[idx + 1]):
                nxt = order[idx + 1]
        except ValueError:
            pass

    logger.info(f"router → {nxt} for query '{last_user[:60]}' history={history}")
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
        return {"result": {"parts": [{"text": f"Tool {tool_name} not available."}]}}

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
    body = {
        "model": settings.groq_model,
        "messages": _to_groq_messages(state["messages"]),
        "temperature": 0.2,
        "tools": groq_tools,
        "tool_choice": {"type": "function", "function": {"name": canonical["name"]}},
        "disable_tool_validation": True,
    }
    # use the existing generate_turn helper (with retry) but with single-tool body
    raw = _generate_turn({"request_body": body})
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
    """No tool matched — let Groq answer with text, no tools."""
    body = {
        "model": settings.groq_model,
        "messages": _to_groq_messages(state["messages"]),
        "temperature": 0.2,
        "disable_tool_validation": True,
    }
    raw = _generate_turn({"request_body": body})
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
    # if router picks an unknown next, fallback
    g.add_edge("router", "fallback")
    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
