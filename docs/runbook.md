# Runbook — one-take recording (spec §8, §11)

## Step 0 — before hitting record (spec R8)
1. `chrome://version` → screenshot + note pinned build; flag `chrome://flags/#enable-webmcp-testing` ON.
2. Throwaway `getTools({fromOrigins:[STORE_ORIGIN]})` in DevTools on the store tab → shows 6 tools.
3. `make db` up, `make store` (:8000), `make dev` (:9000, :8001), `make reset` (fresh catalog, empty audit).
4. `curl :9000/audit` → `[]`. Razorpay dashboard open on test mode. OBS: display capture, tiled windows (L manual / R agent), two Chrome profiles.

## The take (5 min, spec §11)
- 0:00 thesis + citation card.
- 0:25 store walk-by + `getTools()` shows 6 tools (webmcpify 4 + kit 2).
- 1:00 RACE — paste same intent in agent iframe; manual arm clicks Start then shops. Page self-filters/scrolls; chips narrate.
- 2:30 both arms click their "Open payment →" chip → test checkout → paid → server timers close (symmetry: identical click mechanics).
- 3:15 recovery — decline card → pending chip → resume-checkout → expired → fresh link → paid (SC6).
- 3:45 `/compare` deltas + `make verify-audit` on camera + cap rejection replay.
- 4:15 close + distribution line.

## Between takes
`make reset` — re-seeds catalog (scripts/seed_fashion.js), clears carts + audit + links. Repeat step 0 flag check. Submitted take = the one that completes both arms.

## If something breaks live
- Chip did not appear → check `/static/loader.js` reached the page (Network tab), MutationObserver re-inject after SPA nav (R3).
- Payment stuck pending → `GET /poll/{linkId}` (poll-primary; webhooks unreachable on localhost, R4).
- Groq slow/erroring → chips narrate latency; 8-turn/60s cap aborts (R5).
