<h1 align="center">WebMCP for Razorpay</h1>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.1.0-blue?style=flat-square" alt="version">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="license">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square" alt="python">
  <img src="https://img.shields.io/badge/node-%3E%3D18-339933?style=flat-square" alt="node">
  <img src="https://img.shields.io/badge/postgres-16-4169E1?style=flat-square" alt="postgres">
  <img src="https://img.shields.io/badge/Razorpay-test%20mode-0b6bcb?style=flat-square" alt="razorpay">
  <img src="https://img.shields.io/badge/W3C-WebMCP-8a2be2?style=flat-square" alt="webmcp">
  <img src="https://img.shields.io/badge/EverShop-2.2.1-FF632B?style=flat-square" alt="evershop">
</p>

<p align="center"><em>"Compressing discovery-to-order lifts total spend +28.5% and purchase frequency +43%"</em></p>

This is what WebMCP implementations could achieve in any and every web-shop. Use in-shop agents, to compress discovery-to-order time.

W3C WebMCP turns any webshop's own features (search, filter, cart) into agent tools via webmcpify; our kit adds the money layer (`checkout`, `resume-checkout`) and Razorpay test-mode Payment Links settle it — raced live, agent vs manual, on the same EverShop catalog. Spec: [`docs/spec.md`](docs/spec.md).

## Architecture

```mermaid
flowchart TB
    subgraph Chrome["Chrome — one take, two profiles, same store :8000"]
        Store["EverShop :8000<br/>+ loader.js injects kit"]
        Manual["Manual arm — profile A<br/>overlay + capture listeners<br/>Start / Pay"]
        AgentUI["Agent arm — profile B<br/>iframe :8001 allow='tools'<br/>agent.js loop: getTools → executeTool"]
        Manual --- Store
        AgentUI --- Store
    end

    subgraph Tools["WebMCP — 6 tools"]
        StoreTools["4 store-native via webmcpify<br/>search-catalog · show-product<br/>add-to-cart · read-cart"]
        MoneyTools["2 money via kit<br/>checkout · resume-checkout"]
    end

    AgentUI -- "getTools fromOrigins STORE" --> Tools
    Tools -- "executeTool" --> Store

    AgentUI -- "POST /agent/turn messages + tools" --> AgentBE["Agent backend :8001<br/>stateless Groq proxy<br/>key never in browser"]
    AgentBE -- "tool call" --> AgentUI
    AgentBE --> Groq["Groq gpt-oss-120b"]

    Manual -- "POST /checkout/create<br/>POST /event · GET /poll" --> Sidecar["Sidecar :9000<br/>checkout · event · webhook HMAC<br/>poll · compare · audit"]
    MoneyTools -- "POST /checkout/create<br/>POST /event" --> Sidecar

    Sidecar -- "Payment Link + HMAC webhook" --> RZP["Razorpay test-mode<br/>Payment Links"]
    Sidecar --> Audit["audit.jsonl hash-chained<br/>server ts authoritative"]

    Store --> PG[(Postgres :5432 store DB)]
```

## Local Setup

1. Initial dependencies and store setup

```
cp .env.example .env  # Fill with Razorpay **test** keys + Groq key
make db               # postgres container
make setup            # deps (store npm + uv sync) + .env
make seed             # grocery catalog (47 products, INR, image-first)
```

2. Launch Store server

```
make store            # store on :8000
```

3. Spin up agent

```
make dev              # sidecar :9000 + agent :8001
```

## Store credits (GPL-3.0)

Store is [EverShop](https://github.com/evershopcommerce/evershop) v2.2.1 (commit `79ee0d0`), © The Nguyen / EverShop contributors, GPL-3.0 — see [`store/LICENSE`](store/LICENSE) and [`store/CREDITS.md`](store/CREDITS.md). 

Product photos: [Unsplash](https://unsplash.com) (Unsplash License), URLs listed in `store/CREDITS.md`.