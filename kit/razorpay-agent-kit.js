// kit/razorpay-agent-kit.js — money layer: 2 WebMCP tools (checkout, resume-checkout),
// money cap enforced server-side, hash-chained audit via sidecar /event (spec §6).
(function () {
  var SIDE = window.__RZP_SIDECAR__ || 'http://localhost:9000';

  function getSessionId() {
    var k = 'rzp_session_id';
    var v = sessionStorage.getItem(k);
    if (!v) {
      v = 'sess-' + Math.random().toString(36).slice(2, 10);
      sessionStorage.setItem(k, v);
    }
    return v;
  }
  function getTaskId() {
    var k = 'rzp_task_id';
    var v = sessionStorage.getItem(k);
    if (!v) {
      v = 'task-' + Math.random().toString(36).slice(2, 10);
      sessionStorage.setItem(k, v);
    }
    return v;
  }

  function emit(event, payload, opts) {
    opts = opts || {};
    return fetch(SIDE + '/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: opts.sessionId || getSessionId(),
        arm: opts.arm || 'agent',
        task_id: opts.taskId || getTaskId(),
        event: event,
        payload: payload || null,
      }),
    }).catch(function () {});
  }

  function readCart() {
    // EverShop v2 has no /api/cart REST route — the cart lives on GraphQL
    // (schema field is productSku; plain `sku` does not resolve)
    return fetch('/api/graphql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        query: '{ myCart { totalQty items { productSku productName qty } } }',
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var cart = ((d.data || {}).myCart) || {};
        return (cart.items || []).map(function (it) {
          return { sku: String(it.productSku || it.sku || it.productId || ''), qty: it.qty || 1 };
        });
      });
  }

  function createCheckout(arm) {
    return readCart().then(function (items) {
      return fetch(SIDE + '/checkout/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          session_id: getSessionId(),
          arm: arm,
          task_id: getTaskId(),
          items: items,
        }),
      }).then(function (r) {
        return r.json().then(function (body) {
          if (!r.ok) throw body;
          return body; // {linkId, shortUrl, amountPaise}
        });
      });
    });
  }

  // R2: a tool-fired window.open without fresh user activation dies to the popup blocker.
  // Designed fix: render an "Open payment →" chip — one scripted human click opens the link.
  function openPaymentChip(shortUrl, label) {
    var chip = document.getElementById('rzp-pay-chip') || document.createElement('div');
    chip.id = 'rzp-pay-chip';
    chip.innerHTML = '';
    var btn = document.createElement('button');
    btn.textContent = label || 'Open payment →';
    btn.style.cssText = 'padding:10px 16px;border-radius:999px;border:0;background:#0b6bcb;' +
      'color:#fff;font-size:14px;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.2)';
    btn.onclick = function () {
      window.open(shortUrl, '_blank');
      emit('payment_opened', { shortUrl: shortUrl });
    };
    chip.appendChild(btn);
    chip.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:2147483100';
    document.body.appendChild(chip);
  }

  function checkoutTool() {
    return createCheckout('agent').then(function (res) {
      // checkout_opened is written server-side on /checkout/create — no client emit (was duplicated)
      openPaymentChip(res.shortUrl);
      return { linkId: res.linkId, shortUrl: res.shortUrl, amountPaise: res.amountPaise };
    });
  }

  function resumeCheckout(args) {
    var linkId = args && args.linkId;
    return fetch(SIDE + '/checkout/resume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ linkId: linkId }),
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (res.shortUrl) openPaymentChip(res.shortUrl, res.status === 'expired' ? 'New payment link →' : 'Resume payment →');
        return { shortUrl: res.shortUrl, status: res.status };
      });
  }

  function getModelContext() {
    return document.modelContext || navigator.modelContext || null;
  }

  var TOOL_DEFS = [
    {
      name: 'checkout',
      description: 'Create a Razorpay payment link for the current cart. Returns a shortUrl — render an "Open payment →" chip and tell the user to click it.',
      parameters: { type: 'object', properties: {}, required: [] },
      execute: function () { return checkoutTool(); },
    },
    {
      name: 'resume-checkout',
      description: 'Resume a pending or expired payment link. pending → same link; expired → fresh link at snapshot price.',
      parameters: { type: 'object', properties: { linkId: { type: 'string' } }, required: ['linkId'] },
      execute: function (args) { return resumeCheckout(args); },
    },
  ];

  var registered = [];
  function registerTools() {
    // webmcpify runtime (loaded before kit by the loader) owns registration:
    // AbortSignal lifecycle, exposedTo, validation, rollback on failure
    var rt = window.webmcpify;
    if (rt) {
      var handle = rt.createToolScope('razorpay-money', TOOL_DEFS, {
        exposedTo: [window.__RZP_AGENT__ || 'http://localhost:8001'],
        validate: true,
      });
      handle.ready.then(function (ok) {
        if (ok) registered.length = 0, registered.push.apply(registered, TOOL_DEFS);
      });
      return;
    }
    // flag-less fallback: direct registration if a raw modelContext exists
    var ctx = getModelContext();
    TOOL_DEFS.forEach(function (tool) {
      var ok = false;
      if (ctx && typeof ctx.addTool === 'function') {
        try { ctx.addTool(tool); ok = true; } catch (e) { /* retry after runtime loads */ }
      }
      if (ok) registered.push(tool);
    });
  }

  registerTools();

  window.RazorpayAgentKit = {
    emit: emit,
    readCart: readCart,
    createCheckout: createCheckout,
    openPaymentChip: openPaymentChip,
    checkoutTool: checkoutTool,
    resumeCheckout: resumeCheckout,
    tools: TOOL_DEFS,
    registered: registered,
    retryRegistration: registerTools,
    newTask: function () {
      sessionStorage.removeItem('rzp_task_id');
      return getTaskId();
    },
  };

  // agent panel bridge: the iframe (different origin) can't reach our sessionStorage,
  // so it asks us to newTask/emit — keeps session/task ids shared for the audit chain
  window.addEventListener('message', function (e) {
    if (e.origin !== (window.__RZP_AGENT__ || 'http://localhost:8001')) return;
    var d = e.data || {};
    if (!window.RazorpayAgentKit) return;
    if (d.rzpKit === 'newTask') window.RazorpayAgentKit.newTask();
    else if (d.rzpKit === 'emit' && d.event) window.RazorpayAgentKit.emit(d.event, d.payload);
  });
})();
