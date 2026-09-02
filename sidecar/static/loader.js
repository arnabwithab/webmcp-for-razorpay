// sidecar/static/loader.js — injected via one <script> tag on the store page (spec §4 budget).
// Injects kit + manual-arm overlay; MutationObserver re-injects after SPA navigation (spec R3).
(function () {
  var AGENT_ORIGIN = window.__RZP_AGENT__ || 'http://localhost:8001'; // ponytail: spec-fixed ports, override via window var
  var SIDECAR_ORIGIN = window.__RZP_SIDECAR__ || 'http://localhost:9000';

  function originOf(scriptUrl, fallback) {
    try { return new URL(scriptUrl).origin; } catch (e) { return fallback; }
  }
  // derive sidecar origin from this loader's own URL when not overridden
  if (!window.__RZP_SIDECAR__ && document.currentScript && document.currentScript.src) {
    SIDECAR_ORIGIN = originOf(document.currentScript.src, SIDECAR_ORIGIN);
  }
  window.__RZP_SIDECAR__ = SIDECAR_ORIGIN;
  window.__RZP_AGENT__ = AGENT_ORIGIN;
  window.__RZP_STORE__ = window.__RZP_STORE__ || location.origin; // loader runs in the store page

  var RUNTIME_URL = SIDECAR_ORIGIN + '/kit/webmcp-runtime.js';
  var STORE_TOOLS_URL = SIDECAR_ORIGIN + '/kit/webmcp-store-tools.js';
  var KIT_URL = SIDECAR_ORIGIN + '/kit/razorpay-agent-kit.js';
  var MANUAL_URL = SIDECAR_ORIGIN + '/kit/manual-arm.js';

  function injected(src) {
    return document.querySelector('script[data-rzp-inject="' + src + '"]');
  }

  function inject(src) {
    if (injected(src)) return;
    var s = document.createElement('script');
    s.src = src + '?v=9';
    s.async = false;
    s.dataset.rzpInject = src;
    // R3 + retry: a failed fetch (sidecar restarting) removes the tag so the
    // MutationObserver's next boot() re-injects it
    s.onerror = function () { s.remove(); };
    document.head.appendChild(s);
  }

  function injectAgentIframe() {
    if (document.getElementById('rzp-agent-iframe')) return;
    var iframe = document.createElement('iframe');
    iframe.id = 'rzp-agent-iframe';
    iframe.src = AGENT_ORIGIN + '/agent?v=9';
    iframe.allow = 'tools';
    iframe.style.cssText = 'position:fixed;top:12px;right:12px;width:360px;height:520px;' +
      'border:1px solid #d4d4d8;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.15);' +
      'z-index:2147483000;background:#fff';
    document.body.appendChild(iframe);
  }

  function boot() {
    inject(RUNTIME_URL);
    inject(STORE_TOOLS_URL);
    inject(KIT_URL);
    inject(MANUAL_URL);
    injectAgentIframe();
  }

  // R3: SPA route changes can wipe injected nodes — observe and re-inject.
  var observer = new MutationObserver(function () { boot(); });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  boot();
})();
