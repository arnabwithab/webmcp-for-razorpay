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
    s.src = src + '?v=12';
    s.async = false;
    s.dataset.rzpInject = src;
    // R3 + retry: a failed fetch (sidecar restarting) removes the tag so the
    // MutationObserver's next boot() re-injects it
    s.onerror = function () { s.remove(); };
    document.head.appendChild(s);
  }

  function injectAgentIframe() {
    if (document.getElementById('rzp-agent-wrap')) return;
    var wrap = document.createElement('div');
    wrap.id = 'rzp-agent-wrap';
    var pos = null; try { pos = JSON.parse(localStorage.getItem('rzp_agent_pos')||'null'); } catch(e){}
    var minimized = localStorage.getItem('rzp_agent_min') === '1';
    wrap.style.cssText = 'position:fixed;top:12px;right:12px;width:360px;height:520px;display:flex;flex-direction:column;' +
      'border:1px solid #d4d4d8;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.15);' +
      'z-index:2147483000;background:#fff;overflow:hidden;';
    if (pos && typeof pos.left==='number' && typeof pos.top==='number') {
      wrap.style.left = pos.left + 'px'; wrap.style.top = pos.top + 'px';
      wrap.style.right = 'auto'; wrap.style.bottom = 'auto';
    }
    if (minimized) wrap.style.height = '32px';
    var header = document.createElement('div');
    header.id = 'rzp-agent-header';
    header.style.cssText = 'height:32px;flex-shrink:0;display:flex;align-items:center;justify-content:space-between;' +
      'padding:0 8px;background:#f4f4f5;border-bottom:1px solid #e4e4e7;cursor:grab;user-select:none;font:12px system-ui,sans-serif;';
    header.innerHTML = '<span style="font-weight:600">Agent</span><span style="display:flex;gap:4px">' +
      '<button id="rzp-agent-min" title="Minimize" style="width:24px;height:24px;border:0;background:#e4e4e7;border-radius:6px;cursor:pointer">—</button>' +
      '<button id="rzp-agent-close" title="Close" style="width:24px;height:24px;border:0;background:#e4e4e7;border-radius:6px;cursor:pointer">×</button></span>';
    var iframe = document.createElement('iframe');
    iframe.id = 'rzp-agent-iframe';
    iframe.src = AGENT_ORIGIN + '/agent?v=12';
    iframe.allow = 'tools';
    iframe.style.cssText = 'flex:1;width:100%;border:0;background:#fff;';
    if (minimized) iframe.style.display = 'none';
    wrap.appendChild(header); wrap.appendChild(iframe);
    document.body.appendChild(wrap);
    var minBtn = header.querySelector('#rzp-agent-min');
    var closeBtn = header.querySelector('#rzp-agent-close');
    minBtn.onclick = function() {
      var m = iframe.style.display !== 'none';
      iframe.style.display = m ? 'none' : 'block';
      wrap.style.height = m ? '32px' : '520px';
      try { localStorage.setItem('rzp_agent_min', m ? '1' : '0'); } catch(e){}
      minBtn.textContent = m ? '□' : '—';
    };
    if (minimized) minBtn.textContent = '□';
    closeBtn.onclick = function(){ wrap.remove(); try{ localStorage.removeItem('rzp_agent_pos'); localStorage.removeItem('rzp_agent_min'); }catch(e){} };
    // drag
    var sx=0, sy=0, sl=0, st=0, dragging=false;
    header.addEventListener('pointerdown', function(e){
      if (e.target.tagName === 'BUTTON') return;
      dragging=true; header.setPointerCapture(e.pointerId); header.style.cursor='grabbing';
      sx=e.clientX; sy=e.clientY;
      var r=wrap.getBoundingClientRect(); sl=r.left; st=r.top;
      e.preventDefault();
    });
    header.addEventListener('pointermove', function(e){
      if(!dragging) return;
      var nl = sl + (e.clientX - sx), nt = st + (e.clientY - sy);
      nl = Math.max(0, Math.min(nl, window.innerWidth - wrap.offsetWidth));
      nt = Math.max(0, Math.min(nt, window.innerHeight - 32));
      wrap.style.left = nl + 'px'; wrap.style.top = nt + 'px';
      wrap.style.right='auto'; wrap.style.bottom='auto';
    });
    function stopDrag(e){
      if(!dragging) return; dragging=false; header.style.cursor='grab';
      try{ header.releasePointerCapture(e.pointerId); }catch(e){}
      try{ localStorage.setItem('rzp_agent_pos', JSON.stringify({left: wrap.offsetLeft, top: wrap.offsetTop})); }catch(e){}
    }
    header.addEventListener('pointerup', stopDrag);
    header.addEventListener('pointercancel', stopDrag);
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
