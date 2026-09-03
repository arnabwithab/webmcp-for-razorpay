// kit/manual-arm.js — manual arm: capture-listener event inference (no extra clicks, spec §8)
// + Start/Pay overlay. Server ts is authoritative; client timers are cosmetic.
(function () {
  if (window.__rzpManualArmLoaded) return;
  window.__rzpManualArmLoaded = true;

  var SIDE = window.__RZP_SIDECAR__ || 'http://localhost:9000';
  var kit = window.RazorpayAgentKit;
  var ARM = 'manual';

  function emit(event, payload) {
    if (!kit) return;
    kit.emit(event, payload, { arm: ARM });
  }

  function taskStarted() {
    return sessionStorage.getItem('rzp_manual_task') != null;
  }

  function startTask() {
    sessionStorage.setItem('rzp_manual_task', '1');
    kit.newTask();
    emit('task_start');
    timerStart = Date.now();
    renderTimer();
  }

  // ---- event inference via capture listeners ----
  var lastPath = location.pathname;
  document.addEventListener(
    'click',
    function (e) {
      if (!taskStarted()) return;
      var card = e.target.closest && e.target.closest('[data-product-id], .product-card, a[href*="/product/"]');
      if (card) emit('product_viewed', { path: location.pathname });
    },
    true
  );

  // SPA route change → results_viewed (spec §8: route change inference)
  setInterval(function () {
    if (location.pathname !== lastPath) {
      lastPath = location.pathname;
      if (taskStarted()) emit('results_viewed', { path: lastPath });
    }
  }, 500);

  // cart POST → cart_updated
  var origFetch = window.fetch;
  window.fetch = function () {
    var url = arguments[0] || '';
    var str = typeof url === 'string' ? url : (url && url.url) || '';
    var method = (arguments[1] && arguments[1].method) || 'GET';
    var p = origFetch.apply(this, arguments);
    if (taskStarted() && method.toUpperCase() === 'POST' && /\/api\/cart/.test(str)) {
      p.then(function () { emit('cart_updated', { path: str }); }).catch(function () {});
    }
    return p;
  };

  // ---- overlay: Start / timer (cosmetic) / Pay ----
  var timerStart = null;
  function renderTimer() {
    var el = document.getElementById('rzp-manual-timer');
    if (!el) return;
    el.textContent = timerStart ? Math.round((Date.now() - timerStart) / 1000) + 's' : '0s';
  }
  setInterval(renderTimer, 1000);

  function mount() {
    if (document.getElementById('rzp-manual-overlay')) return;
    var box = document.createElement('div');
    box.id = 'rzp-manual-overlay';
    box.style.cssText = 'position:fixed;bottom:16px;left:16px;z-index:2147483100;' +
      'background:#fff;border:1px solid #d4d4d8;border-radius:12px;padding:10px 12px;' +
      'box-shadow:0 8px 24px rgba(0,0,0,.15);display:flex;gap:8px;align-items:center;font-family:sans-serif';
    var start = document.createElement('button');
    start.textContent = 'Start';
    start.style.cssText = 'padding:8px 14px;border-radius:999px;border:0;background:#16a34a;color:#fff;cursor:pointer';
    start.onclick = startTask;
    var timer = document.createElement('span');
    timer.id = 'rzp-manual-timer';
    timer.textContent = '0s';
    box.appendChild(start);
    box.appendChild(timer);
    document.body.appendChild(box);
  }

  mount();
})();
