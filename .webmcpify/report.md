# webmcpify report — EverShop store-native tools

## Coverage target
`curated` per spec G3 (exactly 4 store-native tools; payment excluded by webmcpify policy).

## Tools (verified via playwright stub simulating the flag)

| id | mutating | verified | description |
|---|---|---|---|
| search_catalog | false | yes | `GET /search?keyword=` + same GraphQL `keyword` filter the UI uses; navigates so user sees grid |
| show_product | false | yes | resolves `sku`→`url` via categories GraphQL (same endpoint UI uses), navigates |
| add_to_cart | server | yes | clicks the store's own `AddToCart` button (`#productForm`, `input[name=qty]`); polls `myCart.totalQty` for visible badge; requires being on product page (agent uses `show-product` first) |
| read_cart | false | yes | `myCart { items { sku productName qty } totalQty grandTotal { value } }` (the query the cart UI uses) |

`checkout` / `resume-checkout` are kit money tools, not webmcpify's (policy; registered via the same vendored runtime + `exposedTo`).

## Skipped / rejected
None. `delete`, `Auth`, `payment` surfaces excluded by the four inventory gates (recorded in the manifest).

## Vendored runtime
`kit/webmcp-runtime.js` — classic-script IIFE from `templates/webmcpify.js` (MIT, Jonas Tüchler). Feature-detected (`document.modelContext`); app unchanged without WebMCP. Spec churn isolated to this file (`navigator`→`document`).

## How to test manually (per runbook step 0)
1. `chrome://version` pinned build screenshot
2. `chrome://flags/#enable-webmcp-testing` → Enabled
3. Throwaway `await document.modelContext.getTools({fromOrigins:[store]})` in DevTools on the store tab → 6 tools (4 above + `checkout`, `resume-checkout`)

## Blockers
Verification uses a stubbed `document.modelContext` in playwright (flag-on Chrome is the human camera check). No terminal blockers.

## Mapping of hunks
- `kit/webmcp-runtime.js` — `pipeline.setup.runtimeVendored`
- `kit/webmcp-store-tools.js` — `pipeline.setup.toolsRegistered`
- `sidecar/static/loader.js` (order: runtime→store-tools→kit→manual-arm→iframe) — `pipeline.setup.injection`
- `store/packages/evershop/src/components/common/react/server/Server.tsx` — 1 script tag (spec §4 budget line 1; `store/.evershop/build` + `dist/components` rebuilt)
