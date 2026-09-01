# Spec v3 — Agent-Native Checkout Race: WebMCP Kit on a Real Store, Timed vs Manual (Razorpay Buildathon)
**Tracks:** 01 Agentic Commerce (primary) · 03 Revenue Recovery (in-session recovery) | **Buildathon:** https://razorpay.com/buildathon/

**One-liner:** We drop one `<script>` tag (W3C WebMCP) into a real open-source e-commerce store wired to Razorpay test-mode, add an in-browser agent that drives the store end-to-end, and race it against manual shopping on the same store — live-timed, discovery-to-payment — reproducing the mechanism behind *Fewer Clicks, More Purchases* (Management Science, 2023): compress the funnel, and spend follows.

**We do NOT build the storefront.** Store = cloned from GitHub. Our work: (1) Razorpay sidecar, (2) WebMCP integration (webmcpify for store-native tools + our money layer), (3) the comparative timing study.

**Standing decisions:** no security-product/red-team framing · item-agnostic wow moments · store UI is a hard criterion · webmcpify owns store-native tools, our kit owns money tools only · free tier only.

---

## 1. Thesis & Evidence

**Economics (cited):** Colak, Jung & Park, *Fewer Clicks, More Purchases*, **Management Science 69(12):7317–7334 (2023)** — compressing discovery-to-order: **total spend +28.5%, purchase frequency +43%, item volume +36%, visits +7%, pages +9.3%, exploration +7.8%** (15 months post-launch, causal-forest + quasi-experimental, 35 months of data). Supporting: *Spendception* (Behav. Sci./MDPI 2025) — low-effort digital flows → "emotional detachment" from money; Deloitte/IMRG — 0.1s lag ≈ −10% conversion, forced account creation ≈ 25% finish-line abandonment.

**Mechanism (measured live):** same store, same catalog, same payment rail; only discovery differs.

| Arm | Path | Events |
|---|---|---|
| **Manual** | human browses/filters/opens/adds/pays | `task_start → results_viewed → product_viewed → cart_updated → checkout_opened → payment_paid` |
| **Agent** | one natural-language sentence | same events, emitted by tool calls + agent loop |

**Honesty line (scripted):** "n is small — we demonstrate the *mechanism* live; Colak et al. proved the *economics* at scale. We claim the delta we measure, nothing more."

## 2. Goals

*   **G1 — Clone, don't build:** existing open-source store, seeded catalog; criteria §4 (UI trumps everything).
*   **G2 — Razorpay sidecar:** both arms settle on the identical test-mode Payment Link rail; server-authoritative timers; HMAC-verified webhooks where reachable, poll-primary on localhost.
*   **G3 — WebMCP integration:** webmcpify integrates 4 store-native tools from the clone's own code (verified in-browser); our kit registers 2 money tools (`checkout`, `resume-checkout`). 6 tools total.
*   **G4 — Agent wow:** in-browser agent drives the store — page visibly filters/scrolls/highlights; **hands-off until payment** (one scripted "Open payment" click).
*   **G5 — Timing study:** per-task + median deltas from hash-chained audit; `/compare` renders them; one-take tiled recording proves simultaneity.
*   **G6 — Free tier:** Gemini free, Razorpay test keys, localhost.
*   **G7 — Track 03 evidence (recovery):** decline card → pending detected → agent offers `resume-checkout` → expired link mints a fresh one → paid. Audit shows the whole ladder.

## 3. Non-Goals (YAGNI)

No storefront building/retheming, no auth beyond clone defaults, no guardrail product/red-team harness, no backend agentic protocols (AP2/UAP/x402), no voice/WhatsApp, no production deploy (OT token on a deployed URL = future-work line), no statistical claims beyond measured medians.

## 4. The Clone

**Criteria, ranked — (1) trumps (2):** **(1) Pretty, modern UI — non-negotiable** (on camera ~3 of 5 minutes; grid cards, hover states, real images). (2) single self-contained service (SQLite/zero-external-DB preferred; **one Mongo service is accepted** as the cost of (1)) · (3) stable DOM for filter/scroll-to-product · (4) seeded demo catalog · (5) cart POST endpoint · (6) license allows clone+modify for a demo (verify in spike) · (7) `install && run` ≤ 30 min.

| Candidate | Stack | Status |
|---|---|---|
| **EverShop** | Node + Mongo | **Default pick** — best-looking OSS storefront. License + Mongo cost verified in spike. |
| Medusa Next.js starter | Node + Postgres | backup |
| Django Oscar | Django, SQLite | **eliminated by criterion (1)** (dated UI); reference only. Never retheme. |

**Budget rule (corrected):** **≤2 lines of store *source*** (kit script tag + checkout-button hookup). Everything else is **injected at runtime** by one sidecar-served loader (`/loader.js` → kit + manual-arm overlay, MutationObserver re-injects after SPA route changes). webmcpify's edits are its own line-item (vendored runtime file + registrations), counted and listed in the repo README. Total touch list appears in README — auditable, not hand-waved.

**Spike (½ day, ordered):** ① clone + seed → ② **camera test** (screenshot; ugly → swap candidate now) → ③ `npx skills add TueJon/webmcpify` → `/webmcpify inventory` (zero code changes; proves selectors/cart endpoint discoverable) → ④ license + Mongo check → ⑤ flag-on Chrome: `chrome://version` pinned build, one throwaway `getTools()` → ⑥ confirm webmcpify runtime + our kit can both register without collision (namespaced tool names if needed). Kill-switch: >30 min or weak UI.

## 5. Architecture

```
┌── Demo machine: Chrome (pinned, flag on) · one monitor, two tiled windows ────┐
│  Window L (manual arm, profile A)        Window R (agent arm, profile B)      │
│  clone :8000 + manual-arm overlay        clone :8000 + kit + agent iframe     │
│   overlay infers events via               agent.js (client loop):             │
│   capture listeners; Pay button            getTools({fromOrigins:[STORE]})    │
│   opens same sidecar link                  → /agent/turn → executeTool()      │
└───────────────┬──────────────────────────────────────────┬───────────────────┘
                ▼                                          ▼
   Sidecar :9000 (FastAPI)                     Agent backend :8001 (FastAPI)
   POST /checkout/create → Razorpay link       POST /agent/turn — stateless
   POST /event ← {arm, task_id, …}             per-turn Gemini proxy (owns key)
   POST /webhook (HMAC-verified, if tunnel)    GET /static/loader.js
   GET  /poll/{id}  GET /compare  GET /audit
                ▼
   Razorpay test-mode Payment Links
```

**Profiles:** two Chrome profiles = separate cookie jars — carts don't collide; both windows recorded in **one take** (simultaneity proven on camera). Tab-focus stealing rehearsed; new payment tabs opened identically in both arms (**symmetry rule: identical payment-opening mechanics; tab-switch time counts in both**).

### 5.1 Tooling

**webmcpify** (`npx skills add TueJon/webmcpify`; MIT; opencode-compatible) = **single authority on tool ownership for store-native tools**: DETECT → INVENTORY → approve manifest → INTEGRATE → VERIFY → HEAL → AUDIT, resumable via `.webmcpify/manifest.json`. Owns `search-catalog`, `show-product`, `add-to-cart`, `read-cart`. Its guarantees (unrelated UI untouched, vendored feature-detected runtime = free shim, spec churn isolated — `navigator`→`document`) retire our adapter risk.

**Our kit** owns money tools only (`checkout`, `resume-checkout`) — webmcpify excludes payment tools by policy; money stays ours, capped + audited per the track bar. Registration collision with webmcpify's runtime checked in spike (namespaced names if needed).

**Enablement ladder (demo path):** `chrome://flags/#enable-webmcp-testing` on pinned Chrome → webmcpify vendored runtime (app behaviorally unchanged without WebMCP). OT-token-on-deployed-URL: future work, not on the demo path.

**Fallback:** `webmaxru/web-ai-agent-skills/skills/webmcp` if webmcpify stalls on a clone.

## 6. The Kit — money layer (`razorpay-agent-kit.js`)

Config: `{ maxAmountPaise, agentOrigins, storeName }`. Loader injects kit + overlay; MutationObserver re-injects after SPA navigation.

| Tool | Args | Behavior | Returns |
|---|---|---|---|
| `checkout` | `{}` | over cap → bounded error (no link); else `POST /checkout/create`; **returns `shortUrl` — the agent renders an "Open payment →" chip/button** (one scripted human click; a tool-fired `window.open` without fresh user activation dies to the popup blocker — this is the designed fix, disclosed on camera) | `{linkId, shortUrl, amountPaise}` |
| `resume-checkout` | `{linkId}` | pending → re-open same `shortUrl`; expired → mint fresh link (snapshot price) + log `recovered`; decline → chip offers resume | `{shortUrl, status}` |

*   **Catalog snapshot (canonical pricing):** `make snapshot` → `sidecar/snapshot.json` = `[{sku, name, priceSource: {"value": 9.99, "currency": "USD"}, pricePaise, priceInrLabel}]`, fixed conversion rate recorded. **Currency decision (default): relabel to INR at snapshot time** (number preserved, `₹` shown) with one scripted disclosure line: "test-mode catalog relabeled to INR; production kit reads the store's native currency." Sidecar re-prices from snapshot — never a client-sent amount.
*   **Audit event schema (single source for /compare):** every `POST /event` = `{ts (server-received = authoritative), session_id, arm: "manual"|"agent", task_id, event, tool?, payload?, prev_hash}`. Hash chain: `prev_hash = sha256(prev_line)`; `make verify-audit` recomputes on camera.
*   **Timer authority:** server timestamps. Client timers (overlay chips, agent chips) are cosmetic, fed by `/poll`. `payment_paid` closes the task wherever the client is; store-page navigation cannot kill the clock.

## 7. In-Browser Agent (iframe :8001) — full contract (no dangling references)

**Wiring:** store page gets `<iframe src="http://localhost:8001/agent" allow="tools">` via loader. Agent iframe calls `document.modelContext.getTools({fromOrigins: [STORE_ORIGIN]})`; store tools registered by webmcpify carry `exposedTo: [AGENT_ORIGIN]`.

**Loop (client-held):** user sentence → for each turn: `POST /agent/turn {messages, tools}` → Gemini (stateless backend; `gemini-2.5-flash`; key never in browser) → functionCall → `executeTool(tool, args)` → functionResponse appended → repeat. **Caps:** 8 turns / 60s / AbortController on STOP (logged `agent_aborted`).

**System prompt (inline):** "You drive a demo storefront for the user. Use only the provided tools; narrate one short line per action. Never invent SKUs or prices — trust tool results. After `checkout`, tell the user to click 'Open payment'. If payment is pending or declined, offer `resume-checkout`. If asked anything else: 'I can only help you shop on this store.'"

**Chips (narration filler — scripted, kills dead air while Gemini thinks):** `searching… → found — bringing it to you → added to cart → opening checkout → payment pending — say resume when done`. Latency disclosure on the delta card: **"agent time includes model latency"**.

## 8. The Race Protocol

1.  **Tasks:** 3–5 fixed intents, pre-registered (worded like real users, chosen from seeded catalog), same list both arms.
2.  **Manual arm:** human shops normally; **events inferred by manual-arm.js capture listeners** (route change → `results_viewed`; product-card click → `product_viewed`; cart POST → `cart_updated`) — no extra button presses (bias-free). Overlay Start sets `task_start`; Pay button opens the same sidecar link.
3.  **Agent arm:** paste the intent; `task_start` = message send; tool calls emit events; same close.
4.  **Metrics (exact pairs):** discovery = `task_start → product_viewed` · decision = `product_viewed → cart_updated` · checkout = `cart_updated → payment_paid` · **total = `task_start → payment_paid`**. Per-task values + **median across tasks** per metric (n tasks per arm), rendered on `/compare`. Delta card states: same rail, same catalog, agent time includes model latency, single take.
5.  **Recording:** OBS display capture, one take, tiled windows (L manual / R agent). Runbook step 0: `chrome://version` + flag check + throwaway `getTools()` before hitting record. `make reset` re-seeds catalog + carts between takes; submitted take = the one that completes both arms.

## 9. Repo Shape & Decisions Annex

```
/store/                       # the clone — ≤2 source lines + counted webmcpify edits
/sidecar/app.py               # :9000 — checkout, /event, /webhook(HMAC), /poll, /compare, /audit
/sidecar/snapshot.json        # make snapshot output — canonical prices
/sidecar/compare.py           # groups audit by (task_id, arm); medians
/sidecar/static/loader.js     # injects kit + manual-arm overlay; MutationObserver re-inject
/kit/razorpay-agent-kit.js    # money tools + cap + audit
/kit/manual-arm.js            # capture-listener event inference + Start/Pay overlay
/agent/app.py                 # :8001 — /agent panel + stateless /agent/turn (Gemini proxy)
/agent/static/agent.js        # discover → loop → executeTool → chips
/audit.jsonl                  # hash-chained (gitignored)
/.env.example  /Makefile  /tests/  /docs/spec.md  /docs/runbook.md
```

**Ports/CORS:** store :8000 (clone) · agent backend :8001 · sidecar :9000. FastAPI CORS: sidecar + agent accept store origin only; agent iframe `allow="tools"`; `STORE_ORIGIN=http://localhost:8000`, `AGENT_ORIGIN=http://localhost:8001`.

**`.env.example`:** `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `GEMINI_API_KEY`, `MAX_AMOUNT_PAISE=500000`, `STORE_ORIGIN`, `AGENT_ORIGIN`, `SIDECAR_PORT=9000`, `AGENT_PORT=8001`.

**Makefile:** `store` (run clone) · `dev` (sidecar + agent) · `snapshot` · `reset` (re-seed catalog/carts) · `test` · `verify-audit` · `style` · `clean`.

**Tests (`make test`, pytest + 1 JS smoke):** cap rejection (no link created) · HMAC webhook verify (forged signature rejected) · hash-chain recompute · poll-vs-webhook close · snapshot re-pricing (client amount ignored) · resume semantics (pending vs expired mints new) · JS smoke: 6 tools registered via `getTools()`.

## 10. Success Criteria

*   **SC1:** clone runs with ≤2 source lines touched; webmcpify harness passes all 4 store-native tools; **native path proven once on camera** (`getTools()` in flag-enabled Chrome shows **6 tools** — webmcpify's harness proves behavior, DevTools proves the native surface).
*   **SC2:** agent completes a task end-to-end; page visibly self-filters/self-scrolls; hands-off until payment (chip-click disclosed).
*   **SC3:** both arms settle on identical Razorpay rail; server timestamps close tasks; cap rejection shown once.
*   **SC4:** `/compare` renders per-task + median deltas from hash-chained audit; `make verify-audit` passes on camera.
*   **SC5:** demo survives: flag → vendored runtime (pinned Chrome; runbook step 0).
*   **SC6 (Track 03):** decline → pending chip → `resume-checkout` → expired-link mint → paid, all present in audit.

## 11. Demo Script (5-min video)

*   0:00 — Thesis: Colak/Jung/Park (Management Science '23): compress discovery-to-order → +28.5% spend, +43% frequency. Mechanism = friction; we race it live.
*   0:25 — "A real store, cloned" + one `<script>` tag + webmcpify inventory screenshot → `getTools()` shows 6 tools.
*   1:00 — **The race (one take, tiled, stated on camera):** left manual (timer), right agent (same intent pasted). Page filters/scrolls/highlights itself; chips narrate through model latency.
*   2:30 — Both click "Open payment" (identical mechanics, disclosed) → Razorpay test checkout → paid → server timers close; delta card: "manual X:XX → agent Y:YY (−Z%) — agent time includes model latency."
*   3:15 — Recovery beat: decline card → pending chip → resume → expired-link mint → paid (SC6).
*   3:45 — `/compare` + `make verify-audit`: timings + hash chain; cap rejection replayed once.
*   4:15 — Close + distribution: "webmcpify is how any store's own features become agent tools; the kit adds the money layer; Razorpay settles. This is the mechanism the paper priced at +28.5% — native to the browser (W3C WebMCP, Chrome 149 OT, ChatGPT Desktop ships it)."

### 11.1 Judge-question script

1.  **"Why WebMCP when Razorpay has APIs/MCP?"** → Compression happens *pre*-checkout — search/filter/cart are store-native UI actions; payment is just the rail. The paper's lift lives in the funnel, not the API.
2.  **"Who pays / what stops runaway buying?"** → Cap (`MAX_AMOUNT_PAISE`) → bounded error, human-initiated sessions, one click to pay, full hash-chained audit, test mode.
3.  **"Isn't the race rigged?"** → Pre-registered tasks, medians, same rail/catalog, inferred manual events (no extra clicks), one take, model latency disclosed.
4.  **"Why an iframe agent, not Chrome's built-in agent?"** → The kit makes *any* WebMCP consumer work; the iframe is the controllable harness; ChatGPT Desktop consumption is the distribution proof, not a dependency.
5.  **"Where's Track 03?"** → SC6 ladder on camera + audit trail.
6.  **"Who installs this in production?"** → webmcpify for a store's own features (one command); kit script tag for the money layer.
7.  **"Your catalog shows ₹ but the clone ships USD."** → Snapshot relabel disclosed at 3:45; kit reads native currency in prod.
8.  **"Same funnel in both arms?"** → Yes: identical payment mechanics, symmetry rule stated (§5).

## 12. Risks

*   **R1 — Clone friction / ugly UI / license:** spike gates (camera test, license check, 30-min cap); UI trumps DB criteria; never retheme.
*   **R2 — Popup blocker on agent-arm payment:** designed fix — chip-button open with real user activation; rehearsed.
*   **R3 — SPA navigation kills injected UI:** MutationObserver re-injection; server-authoritative timers make it cosmetic anyway.
*   **R4 — Webhooks can't reach localhost:** poll-primary; webhook only via tunnel if allowed; HMAC-verified either way.
*   **R5 — Gemini RPM/latency:** 8-turn cap, ~4 turns/task; RPM budget: rehearsal + takes ≤ ~40 turns; cache demo sentences; chips narrate latency.
*   **R6 — webmcpify is young (7★):** benign failure mode — fallback to webmaxru skill or hand adapter; cited as tooling, not a demo dependency.
*   **R7 — Manual-arm fairness:** inferred events + pre-registered tasks + medians + symmetry rule; we report what we measure.
*   **R8 — Chrome/flag drift on demo machine:** pinned build, runbook step 0, `chrome://version` screenshot in repo.

## 13. Open Items (owner: you — defaults applied until overridden)

1.  **Final clone pick** — EverShop default; decided by spike §4.
2.  **Currency relabel** — default applied: relabel INR at snapshot + on-camera disclosure (§6). Veto if you want live conversion.
3.  **One-take simultaneous race** — default applied: yes, tiled windows, OBS, one take (§8). Veto if you want composited.
4.  **Track 03 depth** — default applied: decline → pending → resume → expired-mint ladder (G7/SC6). Sufficient to claim Track 03; say if you want more.
