<p align="center">
  <img src="https://img.shields.io/badge/build-make%20test-brightgreen?style=flat-square" alt="build">
  <img src="https://img.shields.io/badge/version-0.1.0-blue?style=flat-square" alt="version">
  <img src="https://img.shields.io/badge/license-GPL--3.0%20(store)%20%2F%20MIT%20(ours)-lightgrey?style=flat-square" alt="license">
  <img src="https://img.shields.io/badge/Razorpay-test%20mode-0b6bcb?style=flat-square" alt="razorpay">
  <img src="https://img.shields.io/badge/LLM-Groq%20gpt--oss--120b-f55036?style=flat-square" alt="llm">
  <img src="https://img.shields.io/badge/W3C-WebMCP-8a2be2?style=flat-square" alt="webmcp">
</p>

# Agent-Native Checkout Race

WebMCP kit on a real store, timed vs manual — for the Razorpay Buildathon (Tracks 01 Agentic Commerce + 03 Revenue Recovery).

One `<script>` tag into a real open-source store (EverShop, in-repo) wired to Razorpay **test-mode** Payment Links. An in-browser agent drives the store end-to-end and races manual shopping on the same catalog — live-timed, discovery-to-payment. Spec: [`docs/spec.md`](docs/spec.md).

## Architecture

```
Chrome (tiled, one take) ── both arms on the same store :8000
  L: manual arm (overlay + capture listeners)   R: agent arm (WebMCP + iframe agent)
        │                                              │
        ▼                                              ▼
  Sidecar :9000 (FastAPI)                    Agent backend :8001 (FastAPI)
  checkout/create · event · webhook(HMAC)    /agent/turn → Groq gpt-oss-120b (stateless)
  poll/{id} · compare · audit                loader.js · agent panel
        ▼
  Razorpay test-mode Payment Links
```

## Quickstart

```bash
make db        # postgres container
make setup     # deps (store npm + uv sync) + .env
make seed      # fashion catalog (22 products, INR)
make store     # store on :8000 (prod mode)
make dev       # sidecar :9000 + agent :8001
make snapshot  # canonical prices -> sidecar/snapshot.json
```

Fill `.env` with Razorpay **test** keys + Groq key (see `.env.example`).

## Store credits (GPL-3.0)

Store is [EverShop](https://github.com/evershopcommerce/evershop) v2.2.1 (commit `79ee0d0`), © The Nguyen / EverShop contributors, GPL-3.0 — see [`store/LICENSE`](store/LICENSE) and [`store/CREDITS.md`](store/CREDITS.md). Product photos: [Unsplash](https://unsplash.com) (Unsplash License), URLs listed in `store/CREDITS.md`.

**Store touch list (audit per spec §4 budget):**
| # | Change | Lines |
|---|--------|-------|
| 1 | `store/config/local.json` (port/currency/session config) | config only |
| 2 | `store/media/fashion/` (25 local product images) | data only |
| 3 | `store/extensions/session-shim/` — 6-line extension, upstream bug workaround (`/images` route crashes customer auth middleware; still broken upstream) | +6 (sanctioned extension hook, zero EverShop source touched) |
| 4 | Kit `<script>` tag + checkout hookup | ≤2 (pending UI integration) |

## Repo layout

`sidecar/` (FastAPI :9000 — payments, events, audit, compare) · `agent/` (FastAPI :8001 — Groq proxy + panel) · `kit/` (money tools + manual arm, injected) · `scripts/seed_fashion.js` (catalog seed) · `tests/` (pytest + JS smoke) · `docs/` (spec, runbook, features).

## Commands

See `make help` — `store`, `dev`, `db`, `seed`, `snapshot`, `reset`, `test`, `verify-audit`, `style`, `clean`, `setup`.

Demo is localhost + Razorpay test mode + Groq free tier only. No production deploy (spec §3).
