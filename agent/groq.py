"""Shared Groq helpers — used by both the direct /agent/turn path and the LangGraph blocks."""

import json

import httpx

from agent.utils.config import settings
from agent.utils.logger import logger

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = (
    "You drive a demo storefront for the user. Use only the provided tools — "
    "tool names use hyphens (search-catalog, show-product, add-to-cart, "  # noqa: E501
    "read-cart, checkout, resume-checkout), "  # noqa: E501
    "never underscores. Never invent SKUs or prices — trust tool results. "
    "You have NO other tools: never use code execution, browsing, or any tool not listed. "
    "Flow: search-catalog with the user's keywords → pick the best sku from the "
    "returned items → show-product for that sku → add-to-cart. "  # noqa: E501
    "If the user wants multiple items (e.g., carrots, onions, eggs), handle them "
    "one by one: search for the first item, add it, then search for the next item, "
    "add it, and so on until all are in the cart, then checkout. "  # noqa: E501
    "Do not call the same tool twice with the same arguments; if a search returns "
    "items, proceed immediately to show-product. "  # noqa: E501
    "After checkout, tell the user to click 'Open payment'. If payment is pending or "
    "declined, offer resume-checkout. "
    "If asked anything else: 'I can only help you shop on this store.'"
)


def _to_groq_messages(internal: list[dict]) -> list[dict]:
    """Internal parts-based messages -> OpenAI-style messages with tool_call id pairing."""
    out: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    n = 0
    call_id = None
    for msg in internal:
        for part in msg.get("parts", []):
            if "text" in part:
                out.append(
                    {
                        "role": "user" if msg["role"] == "user" else "assistant",
                        "content": part["text"],
                    }
                )
            elif "functionCall" in part:
                call = part["functionCall"]
                n += 1
                call_id = f"call_{n}"
                out.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": call["name"],
                                    "arguments": json.dumps(call.get("args", {})),
                                },
                            }
                        ],
                    }
                )
            elif "functionResponse" in part:
                resp_part = part["functionResponse"]
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id or "call_0",
                        "name": resp_part["name"],
                        "content": json.dumps(resp_part.get("response", {})),
                    }
                )
    return out


def _from_groq(message: dict) -> dict:
    """OpenAI-style assistant message -> internal parts shape."""
    parts: list[dict] = []
    for call in message.get("tool_calls") or []:
        fn = call["function"]
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        parts.append({"functionCall": {"name": fn["name"], "args": args}})
    if message.get("content"):
        parts.append({"text": message["content"]})
    return {"parts": parts}


def generate_turn(payload: dict) -> dict:
    """One stateless Groq call (OpenAI-compatible). Returns the raw Groq response."""
    import time as _time

    body = payload["request_body"]
    logger.info(
        f"groq turn → model={body.get('model')} msgs={len(body.get('messages', []))} "
        f"tools={[t['function']['name'] for t in body.get('tools', [])]}"
    )
    for attempt in range(3):
        resp = httpx.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json=body,
            timeout=30,
        )
        if resp.status_code == 429 or (resp.status_code >= 500 and resp.status_code < 600):
            wait = 2**attempt
            try:
                retry_after = float(resp.headers.get("retry-after", wait))
                wait = min(retry_after, 8)
            except ValueError:
                pass
            logger.warning(
                f"groq {resp.status_code} retry={wait}s attempt={attempt + 1}/3 "
                f"model={body.get('model')} err={resp.text[:200]}"
            )
            _time.sleep(wait)
            continue
        if resp.status_code >= 400:
            logger.error(
                f"groq error {resp.status_code} body={resp.text[:500]} model={body.get('model')}"
            )
        resp.raise_for_status()
        data = resp.json()
        msg = data.get("choices", [{}])[0].get("message", {})
        tc = msg.get("tool_calls") or []
        logger.info(
            f"groq turn ← {len(tc)} tool_calls {[c['function']['name'] for c in tc]} "
            f"text_len={len(msg.get('content') or '')} model={body.get('model')}"
        )
        return data
    resp.raise_for_status()
    return resp.json()
