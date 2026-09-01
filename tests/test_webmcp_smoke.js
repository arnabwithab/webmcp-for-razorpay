// tests/test_webmcp_smoke.js — spec §9 JS smoke: 6 tools registered via getTools().
// Run: node tests/test_webmcp_smoke.js
// Simulates flag-enabled Chrome: stubbed modelContext + webmcpify-style store tools + our kit.
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

// ---- minimal browser stubs ----
const registered = [];
const storeTools = [
  { name: 'search-catalog', description: 'd', parameters: { type: 'object', properties: {} }, execute: async () => ({}) },
  { name: 'show-product', description: 'd', parameters: { type: 'object', properties: {} }, execute: async () => ({}) },
  { name: 'add-to-cart', description: 'd', parameters: { type: 'object', properties: {} }, execute: async () => ({}) },
  { name: 'read-cart', description: 'd', parameters: { type: 'object', properties: {} }, execute: async () => ({}) },
];

const modelContext = {
  // webmcpify-style store tool registration
  addStoreTool: (t) => storeTools.push(t),
  addTool: (t) => registered.push(t),
  getTools: ({ fromOrigins } = {}) => Promise.resolve([...storeTools, ...registered]),
};

global.document = {
  modelContext,
  currentScript: { src: 'http://localhost:9000/static/loader.js' },
  createElement: () => ({ style: {}, dataset: {}, appendChild() {} }),
  head: { appendChild() {} },
  body: { appendChild() {} },
  addEventListener() {},
  querySelector: () => null,
  querySelectorAll: () => [],
  getElementById: () => null,
};
global.navigator = {};
global.window = global;
global.location = { pathname: '/' };
global.sessionStorage = {
  _m: {},
  getItem(k) { return this._m[k] || null; },
  setItem(k, v) { this._m[k] = v; },
  removeItem(k) { delete this._m[k]; },
};
global.fetch = async () => ({ ok: true, json: async () => ({}) });
global.MutationObserver = class { observe() {} disconnect() {} };

// ---- webmcpify-style: register 4 store-native tools (vendored runtime stand-in) ----
// F004 replaces this stub with the real vendored webmcpify runtime.
storeTools.splice(0, 4).forEach((t) => modelContext.addTool(t));
storeTools.push(...[]);

// ---- load our kit ----
const kitSrc = fs.readFileSync(path.join(ROOT, 'kit/razorpay-agent-kit.js'), 'utf8');
eval(kitSrc);

(async () => {
  const tools = await modelContext.getTools({ fromOrigins: ['http://localhost:8000'] });
  const names = tools.map((t) => t.name).sort();
  const expected = ['add-to-cart', 'checkout', 'read-cart', 'resume-checkout', 'search-catalog', 'show-product'];
  console.log('tools:', names.join(', '));
  if (names.length !== 6) {
    console.error(`FAIL: expected 6 tools, got ${names.length}`);
    process.exit(1);
  }
  if (JSON.stringify(names) !== JSON.stringify(expected)) {
    console.error(`FAIL: tool set mismatch: ${names}`);
    process.exit(1);
  }
  // money tool shapes per spec §6
  const checkout = tools.find((t) => t.name === 'checkout');
  const resume = tools.find((t) => t.name === 'resume-checkout');
  if (!checkout || !resume) { console.error('FAIL: money tools missing'); process.exit(1); }
  if (typeof checkout.execute !== 'function' || typeof resume.execute !== 'function') {
    console.error('FAIL: tools must be executable');
    process.exit(1);
  }
  console.log('SMOKE OK: 6 tools registered via getTools()');
})().catch((e) => { console.error('FAIL:', e); process.exit(1); });
