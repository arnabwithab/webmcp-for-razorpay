# AGENT.md

> **Sole truth: `docs/spec.md` (Spec v3 - Agent-Native Checkout Race).** Every decision, scope boundary, and interface in this file derives from spec.md. If any other doc or comment conflicts with spec.md, spec.md wins. Read it before any change.
> **Razorpay authority: Razorpay Test Mode API docs are the sole truth for all payment integration** (Payment Links, webhooks/HMAC, amounts). Strictly refer to https://razorpay.com/docs/api/payment-links/ and https://razorpay.com/docs/webhooks/ — test-mode only, never live, never invented payloads.

## Project Overview

Agent-Native Checkout Race for Razorpay Buildathon (Tracks 01 Agentic Commerce + 03 Revenue Recovery). We clone a real open-source store (EverShop default, Node+Mongo), wire both a manual-shopping arm and a WebMCP agent arm to the same Razorpay test-mode Payment Links rail, and race them live - discovery-to-payment on the same catalog. The store is not built; our work is the Razorpay sidecar, the WebMCP kit (webmcpify for 4 store-native tools + our 2 money tools = 6 total), and the timed comparative study. See spec.md §1-2 for thesis and goals G1-G7.

## Development Philosophy

- TDD first: write the test, then the implementation. Never skip.
- Tests mirror the structure of the module they test.
- No function ships without a test (spec §9 test list is the minimum).
- API routes are thin - logic lives in `core/` (sidecar) or isolated modules.
- Explicit over clever - readable beats smart.
- If it isn't runnable via `make`, it isn't done.

## Tech Stack

- **Store (cloned, not built):** EverShop (Node + Mongo) - single service, seeded catalog, pretty UI per spec §4. Fallbacks: Medusa Next.js starter. Django Oscar eliminated (dated UI). `store/` is a clone with <=2 source lines touched (kit script tag + checkout hookup); runtime injection via `loader.js`.
- **Sidecar :9000:** FastAPI (Python) - `POST /checkout/create`, `POST /event`, `POST /webhook` (HMAC), `GET /poll/{id}`, `GET /compare`, `GET /audit`. Server-authoritative timers, hash-chained audit (`audit.jsonl`), snapshot re-pricing.
- **Agent backend :8001:** FastAPI (Python) - `POST /agent/turn` (stateless Gemini `gemini-2.5-flash` proxy, key never in browser), `GET /static/loader.js`, serves `agent` iframe.
- **Kit / Frontend injected:** Vanilla JS - `kit/razorpay-agent-kit.js` (money tools `checkout`/`resume-checkout`), `kit/manual-arm.js` (capture listeners, overlay), `agent/static/agent.js` (client loop `getTools` -> `/agent/turn` -> `executeTool`). WebMCP via `webmcpify` (vendored runtime, `/.webmcpify/manifest.json`).
- **Database:** Mongo (store) + SQLite/file for sidecar audit + `sidecar/snapshot.json` (canonical prices). No external DB for sidecar.
- **Package Manager:** `uv` (Python), `npm` (store). Never `pip` directly.
- **Build/Task Runner:** **Make** - root `Makefile` is the single entry point.
- **Styling:** Store's own UI (criterion #1, non-negotiable per spec §4) - never retheme.
- **State/LLM:** Gemini free tier only; Razorpay test keys only; localhost only (spec G6).

## Key Commands

All commands runnable via `make <target>` from project root. Tools (`uvicorn`, `npm`, etc.) are Makefile internals only.

```bash
make store        # run cloned store on :8000
make dev          # run sidecar :9000 + agent backend :8001 concurrently
make snapshot     # catalog snapshot -> sidecar/snapshot.json (canonical pricing)
make reset        # re-seed catalog + clear carts between takes
make test         # pytest + 1 JS smoke (cap, HMAC, hash-chain, poll, re-pricing, resume, 6 tools)
make verify-audit # recompute hash chain: prev_hash = sha256(prev_line)
make style        # black + ruff (format + lint + import sort)
make build        # production build (if any)
make clean        # remove artifacts, caches, __pycache__, audit.jsonl (gitignored)
make setup        # idempotent install/sync for store + sidecar + agent
```

`make setup` is idempotent and safe to re-run. `make store` + `make dev` together boot the full stack (spec §5 architecture).

## Directory Structure

From spec §9 (authoritative):

```
.
├── store/                       # cloned EverShop - <=2 source lines + counted webmcpify edits
├── sidecar/
│   ├── app.py                   # :9000 checkout, /event, /webhook(HMAC), /poll, /compare, /audit
│   ├── compare.py               # groups audit by (task_id, arm); medians
│   ├── snapshot.json            # make snapshot output - canonical prices
│   └── static/loader.js         # injects kit + manual-arm overlay; MutationObserver re-inject
├── kit/
│   ├── razorpay-agent-kit.js    # money tools + cap + audit
│   └── manual-arm.js            # capture-listener event inference + Start/Pay overlay
├── agent/
│   ├── app.py                   # :8001 /agent panel + stateless /agent/turn (Gemini proxy)
│   └── static/agent.js          # discover -> loop -> executeTool -> chips
├── audit.jsonl                  # hash-chained (gitignored)
├── tests/                       # pytest + JS smoke; mirrors sidecar/ + agent/
├── .env.example                 # RAZORPAY_KEY_ID/SECRET/WEBHOOK_SECRET, GEMINI_API_KEY, MAX_AMOUNT_PAISE, STORE_ORIGIN, AGENT_ORIGIN, SIDECAR_PORT, AGENT_PORT
├── Makefile
├── docs/
│   ├── spec.md                  # sole truth (Spec v3)
│   ├── runbook.md               # one-take recording runbook
│   └── features.json            # canonical feature tracker
├── .gitignore
├── README.md
└── AGENTS.md
```

Ports/CORS per spec §9: store :8000, sidecar :9000, agent :8001. Sidecar + agent accept store origin only; iframe `allow="tools"`; `STORE_ORIGIN=http://localhost:8000`, `AGENT_ORIGIN=http://localhost:8001`.

## Conventions

### Makefile (required)

- Root `Makefile` is mandatory and is the canonical control surface. No step exists only as "remember to run manually".
- Required targets: `setup`, `dev`, `test`, `style`, `build`, `clean` plus spec targets `store`, `snapshot`, `reset`, `verify-audit`. Never remove the required set.
- Each target is a thin wrapper shelling into `store/`, `sidecar/`, or `agent/` and calling the underlying tool.
- Every target has a `## short description` on the same line for `make help` / `grep`.

### Python (Sidecar + Agent Backend)

- **Package manager: `uv`** - `uv add`, `uv run`, `uv sync`. Never `pip`.
- Formatter: `black`, Linter: `ruff` (includes import sorting).
- Naming: snake_case for everything - files, variables, functions.
- API routes are thin: validate input -> call core -> return output. `core/` has zero HTTP/FastAPI knowledge.
- Env vars exclusively via `from utils.config import settings` (Pydantic `BaseSettings`, `pydantic-settings`). Never `os.environ` directly. Config instantiated once in `sidecar/utils/config.py` / `agent/utils/config.py`.
- Logging exclusively via `from utils.logger import logger`. Never `print` or stdlib `logging` directly.
- Config example (`sidecar/utils/config.py`):

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    port: int = 9000
    store_origin: str = "http://localhost:8000"
    agent_origin: str = "http://localhost:8001"
    razorpay_key_id: str
    razorpay_key_secret: str
    razorpay_webhook_secret: str
    gemini_api_key: str
    max_amount_paise: int = 500000

settings = Settings()
```

### JS (Kit / Agent Iframe)

- Vanilla JS, no framework for kit/overlay (injected at runtime, MutationObserver re-injects after SPA navigation per spec R3).
- `checkout` returns `shortUrl` rendered as "Open payment ->" chip (popup-blocker fix, spec §6) - one scripted human click.
- `resume-checkout` semantics: pending -> same shortUrl, expired -> mint fresh link (snapshot price) + log `recovered`.
- All timers are cosmetic; server `ts` on `POST /event` is authoritative; `payment_paid` closes task anywhere.

### General

- Commits: conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`) + signoff (see Git section below).
- Env vars never committed; `.env.example` has keys with no values.
- API versioned under `/api/v1/` if versioning is introduced; current spec uses unversioned sidecar/agent paths (`/checkout/create`, `/agent/turn`, etc.) - follow spec.
- README badges: HTML `<img>` shield badges via shields.io (build, version, license, tech stack), not Markdown image syntax.
- Never put API calls directly in injected components without going through the kit/overlay abstraction where spec mandates it.

### Git / GitHub - Regular Push with Signoff

Remote will be added soon. Until then:

```bash
# once, after remote is created (user will provide URL):
git remote add origin <github-url>
# or if origin exists:
git remote set-url origin <github-url>

# work:
git status
git diff
git add <files>

# commit - ALWAYS sign off:
git commit -s -m "feat: short description"
# -s adds Signed-off-by: Name <email> (DCO). Required on every commit.

# push - regular (no force):
git push origin <branch>        # e.g. git push origin main
# for a new branch:
git push -u origin <branch>

# verify:
git log --oneline -5 --show-signature
git remote -v
```

- Every commit must have `-s` / `--signoff`. Amend without signoff is a fixup: `git commit --amend -s --no-edit`.
- Never force-push (`--force`, `--force-with-lease`) without explicit user approval.
- Pull before push if remote is ahead: `git pull --rebase origin <branch>`.

## Deployment Philosophy

Per spec §3 and §12: **no production deploy**. Demo is localhost + Razorpay test-mode + Gemini free tier only. OT token on deployed URL is explicitly future work, not on the demo path. Free-tier hosting notes (Render/Vercel/HF Spaces) do not apply to this project. If spec changes to require deploy, flag it - currently out of scope.

### Go-portability flag

Not applicable. Backend is not pure HTTP plumbing - sidecar owns audit hash chain, snapshot re-pricing, HMAC verification, and comparison medians (spec §6, §8). Store is Node (EverShop). Do not flag for Go rewrite unless spec pivots to plumbing-only.

## Multi-Agent Workflow

When `docs/features.json` contains 3+ independent features (different modules, no shared state), parallelize via builder subagents (max 3 concurrent) per spec.

### Flow

1. Plan: Identify independent features from `features.json`. Same-file features are dependent - batch sequentially.
2. Build: Spawn up to 3 builders via Task tool. When one completes, spawn next pending.
3. E2E (if applicable): After all builders, spawn `playwright-tester` for browser tests.
4. Review: Spawn `ponytail-reviewer` on combined diff for over-engineering.
5. Verify: `make test && make style` + `make verify-audit`.

If <3 independent features, implement directly without subagents.

### Subagents

Defined in `~/.config/opencode/agents/`, model `opencode-go/deepseek-v4-flash`.

| Agent | File | Purpose | Permissions |
|-------|------|---------|-------------|
| builder | `builder.md` | TDD one feature, tests then implementation | edit: allow, bash: allow, task: { *: deny, playwright-tester: allow } |
| playwright-tester | `playwright-tester.md` | E2E browser tests via playwright-cli | edit: deny, bash: allow |
| ponytail-reviewer | `ponytail-reviewer.md` | Bloat audit on combined diff | edit: deny, bash: allow |

### Edge cases

- Dependent features (same files): sequenced in same builder.
- Ponytail finds issues: main agent decides fix-now vs file-as-debt.
- No E2E tests: skip playwright-tester.
- Builder can spawn playwright-tester mid-flight for its own feature.

## Agent Guidelines

- Always run `make style` before considering code done.
- snake_case for Python, kebab-case for injected JS files, camelCase for JS vars/functions, PascalCase for components if any.
- Never modify `docs/spec.md` unless explicitly asked - it is the sole truth. Never modify `docs/features.json` except to update feature status after completing a task.
- Always run `make test` after changes; fix failures before moving on. Also run `make verify-audit` if audit logic changed.
- Never use `os.environ` outside config module; never use `print`/stdlib `logging` outside logger.
- Never add store retheming, auth, guardrail product, or backend agentic protocols (AP2/UAP/x402) - spec §3 YAGNI.
- Always check `docs/spec.md` + `docs/runbook.md` before starting any task - if a design exists, it takes precedence.
- If a design doc is missing but task is significant, flag to user before proceeding.
- Always update `docs/features.json` after completing a task - mark done, update tests, dates.
- Any new setup/run/test/style/build step must be a Makefile target, not just prose.
- If something feels out of scope vs spec, flag it rather than silently doing it.
- If >=3 independent features in `docs/features.json`, spawn builder subagents per Multi-Agent Workflow.
- Budget rule (spec §4): <=2 lines of `store/` source touched; everything else via `loader.js` runtime injection. webmcpify edits are counted separately in README.
- Money cap: `MAX_AMOUNT_PAISE` enforced server-side; client amount is ignored (re-priced from `snapshot.json`).
- Razorpay Test Mode only: for `POST /checkout/create`, webhook HMAC verification, and any Razorpay payload, strictly follow https://razorpay.com/docs/api/payment-links/ and https://razorpay.com/docs/webhooks/ — never invent fields, never use live keys/endpoints, never copy external snippets unverified.

## Project-Specific Notes

- **External APIs:** Razorpay Payment Links **test-mode only** — authoritative docs: https://razorpay.com/docs/api/payment-links/ (link creation) and https://razorpay.com/docs/webhooks/ (HMAC verification). `RAZORPAY_KEY_ID/SECRET/WEBHOOK_SECRET`, Gemini `gemini-2.5-flash` (free tier, `GEMINI_API_KEY`). Keys via `.env`, never committed. Test-mode only, never live.
- **Store choice:** EverShop default (Node+Mongo). Criteria ranked in spec §4: (1) pretty UI non-negotiable, (2) single service, (3) stable DOM, (4) seeded catalog, (5) cart POST, (6) license, (7) install <=30min. Verify license + Mongo cost in spike.
- **webmcpify:** `npx skills add TueJon/webmcpify` (MIT, opencode-compatible). Owns 4 store-native tools (`search-catalog`, `show-product`, `add-to-cart`, `read-cart`). Our kit owns 2 money tools (`checkout`, `resume-checkout`). 6 total, verified via `getTools({fromOrigins:[STORE]})` in flag-enabled Chrome (`chrome://flags/#enable-webmcp-testing`).
- **Ports:** store :8000, agent :8001, sidecar :9000. Two Chrome profiles (separate cookie jars), one OBS take, tiled windows (spec §5, §8).
- **Audit:** `audit.jsonl` hash-chained (`prev_hash = sha256(prev_line)`), server `ts` authoritative, `make verify-audit` recomputes. `POST /event` schema: `{ts, session_id, arm, task_id, event, tool?, payload?, prev_hash}`.
- **Recovery (Track 03):** decline -> pending chip -> `resume-checkout` -> expired mints fresh link -> paid; all in audit (spec G7/SC6).
- **Spike kill-switch:** >30 min or weak UI -> swap candidate immediately (spec §4).
- **Never touch:** `store/` beyond the 2-line budget without listing in README; `audit.jsonl` (gitignored, append-only); pinned Chrome build (document `chrome://version` per spec R8).
- **Known gotchas:** popup blocker (chip-button fix, spec R2), SPA nav kills injection (MutationObserver, R3), webhooks unreachable on localhost (poll-primary, R4), Gemini RPM/latency (8-turn/60s cap, chips narrate latency, R5).
