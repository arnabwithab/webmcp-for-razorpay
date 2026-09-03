// agent/static/agent.js — client-held loop: getTools → /agent/turn → executeTool → chips (spec §7).
// Caps: 8 turns / 60s / AbortController on STOP. Server ts authoritative; chips are cosmetic.
// Store navigation (search/show-product) destroys this iframe, so `messages` live in
// sessionStorage and the loop auto-resumes after the page reloads.
(function () {
  var STORE_ORIGIN = 'http://localhost:8000'; // spec §9 fixed
  var MAX_TURNS = 8;
  var MAX_MS = 60000;
  var STORE_KEY = 'rzp_agent_messages';

  var chat = document.getElementById('chat');
  var chips = document.getElementById('chips');
  var q = document.getElementById('q');
  var sendBtn = document.getElementById('send');
  var stopBtn = document.getElementById('stop');

  var messages = [];
  var abort = null;
  var lastChip = null;

  try {
    messages = JSON.parse(sessionStorage.getItem(STORE_KEY) || '[]') || [];
  } catch (e) {
    messages = [];
  }

  function save() {
    try { sessionStorage.setItem(STORE_KEY, JSON.stringify(messages)); } catch (e) {}
  }

  function addMsg(role, text) {
    var div = document.createElement('div');
    div.className = 'msg ' + role;
    div.textContent = text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
  }

  function chip(text) {
    if (lastChip) lastChip.remove();
    lastChip = document.createElement('span');
    lastChip.className = 'chip';
    lastChip.textContent = text;
    chips.appendChild(lastChip);
  }

  // replay a restored conversation (text parts only)
  messages.forEach(function (m) {
    (m.parts || []).forEach(function (p) {
      if (p.text) addMsg(m.role === 'user' ? 'user' : 'model', p.text);
    });
  });

  function kit() {
    return window.RazorpayAgentKit || null;
  }

  // The kit runs in the store page (it owns session/task ids there). From this
  // iframe ask it to newTask/emit on our behalf so audit ids stay shared.
  function kitCall(msg) {
    var k = kit();
    if (k) {
      if (msg.rzpKit === 'newTask') k.newTask();
      else k.emit(msg.event, msg.payload);
      return;
    }
    try {
      if (window.parent && window.parent !== window) parent.postMessage(msg, STORE_ORIGIN);
    } catch (e) {}
  }

  async function getTools() {
    var tools = [];
    // W3C WebMCP discovery (flag-enabled Chrome or vendored runtime)
    var ctx = document.modelContext || navigator.modelContext;
    if (ctx && ctx.getTools) {
      tools = await ctx.getTools({ fromOrigins: [STORE_ORIGIN] });
    }
    // our own kit money tools (kit loads inside this iframe via the panel)
    var k = kit();
    if (k) tools = tools.concat(k.registered.length ? k.registered : k.tools);
    return tools;
  }

  async function waitForTools() {
    var tools = await getTools();
    // first-turn race: kit/store tools register a beat after us — poll ~5s
    for (var i = 0; i < 20 && !tools.length; i++) {
      await new Promise(function (r) { setTimeout(r, 250); });
      tools = await getTools();
    }
    return tools;
  }

  function norm(n) { return String(n).replace(/_/g, '-'); }
  // tools that navigate the store page — after their response the page unloads,
  // so the loop must stop and let the fresh iframe resume on the new page
  var NAVIGATORS = { 'search-catalog': 1, 'show-product': 1 };

  // native WebMCP returns the tool result as a JSON string; the headless stub
  // returns the object directly. Treat either as success unless it says ok:false.
  function resultOk(result) {
    if (result && typeof result === 'object') return result.ok !== false;
    if (typeof result === 'string') {
      try { var o = JSON.parse(result); return !o || o.ok !== false; } catch (e) { return true; }
    }
    return true;
  }

  async function executeTool(name, args) {
    var ctx = document.modelContext || navigator.modelContext;
    var k = kit();
    name = norm(name);
    if (k && k.tools.some(function (t) { return norm(t.name) === name; })) {
      var tool = k.tools.find(function (t) { return norm(t.name) === name; });
      return await tool.execute(args);
    }
    if (ctx && ctx.getTools) {
      var storeTools = await ctx.getTools({ fromOrigins: [STORE_ORIGIN] });
      var match = storeTools.find(function (t) { return norm(t.name) === name; });
      if (match) {
        // native WebMCP (flagged Chrome) expects stringified input when inputSchema
        // is stringified; the headless stub uses match.execute(object)
        if (ctx.executeTool) {
          try { return await ctx.executeTool(match, JSON.stringify(args)); }
          catch (e) {
            if (String(e).includes('Failed to parse input')) {
              return await ctx.executeTool(match, args);
            }
            throw e;
          }
        }
        if (match.execute) return await match.execute(args);
      }
    }
    throw new Error('tool not found: ' + name);
  }

  async function loop() {
    var deadline = Date.now() + MAX_MS;
    for (var turn = 0; turn < MAX_TURNS; turn++) {
      if (abort.signal.aborted) throw new DOMException('aborted', 'AbortError');
      if (Date.now() > deadline) { chip('stopped — 60s cap'); return; }

      chip('thinking…');
      var tools = await waitForTools();
      console.info('[agent] tools=' + tools.length + ' kit=' + (kit() ? 'yes' : 'no'));
      if (!tools.length) {
        // never POST tools=[] — the server graph cannot act without tool defs
        chip('');
        addMsg('model', 'Store tools are still loading — please try again in a moment.');
        return;
      }
      var serializableTools = tools.map(function (t) {
        var schema = t.parameters || t.inputSchema || { type: 'object' };
        if (typeof schema === 'string') { try { schema = JSON.parse(schema); } catch (e) { schema = { type: 'object' }; } }
        return { name: t.name, description: t.description, parameters: schema };
      });
      var resp = await fetch('/agent/turn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abort.signal,
        body: JSON.stringify({ messages: messages, tools: serializableTools }),
      });
      if (!resp.ok) throw new Error('turn failed ' + resp.status);
      var body = await resp.json();
      var parts = body.parts || [];

      var fnCall = parts.find(function (p) { return p.functionCall; });
      var textPart = parts.find(function (p) { return p.text; });

      if (fnCall) {
        var call = fnCall.functionCall;
        if (textPart) addMsg('model', textPart.text); // chat line may travel with the call
        chip(call.name + '…');
        messages.push({
          role: 'model',
          parts: textPart ? [{ text: textPart.text }, { functionCall: call }] : [{ functionCall: call }],
        });
        save();
        var response;
        try {
          response = { result: await executeTool(call.name, call.args) };
        } catch (err) {
          response = { error: String(err) };
        }
        // push + save immediately: search/show-product navigate the store page,
        // destroying this iframe — the functionResponse must hit sessionStorage first
        messages.push({ role: 'user', parts: [{ functionResponse: { name: call.name, response: response } }] });
        save();
        // checkout chip inside the (now draggable) agent panel — stays with the window
        if ((call.name === 'checkout' || call.name === 'resume-checkout') && response.result) {
          var r = response.result; if (typeof r === 'string') { try { r = JSON.parse(r); } catch (e) {} }
          var url = r && (r.shortUrl || r.short_url || r.url);
          if (url) {
            if (lastChip) lastChip.remove();
            lastChip = document.createElement('span');
            lastChip.className = 'chip';
            var a = document.createElement('a');
            a.href = url; a.target = '_blank'; a.rel = 'noopener';
            a.textContent = 'Open payment →';
            a.style.cssText = 'color:#fff;text-decoration:none;';
            lastChip.style.background = '#0b6bcb';
            lastChip.style.color = '#fff';
            lastChip.appendChild(a);
            chips.appendChild(lastChip);
          }
        }
        if (NAVIGATORS[call.name] && resultOk(response.result)) {
          chip('navigating…');
          return; // page is unloading; resume on the fresh iframe continues the funnel
        }
        continue;
      }

      if (textPart) {
        chip('');
        addMsg('model', textPart.text);
        messages.push({ role: 'model', parts: [{ text: textPart.text }] });
        save();
        return;
      }

      // empty turn (no tool call, no text) — say so instead of ending silently
      chip('');
      addMsg('model', 'Sorry — I hit a snag mid-thought. Please try again.');
      return;
    }
    chip('stopped — turn cap');
  }

  function runLoop() {
    abort = new AbortController();
    sendBtn.disabled = true;
    return loop()
      .catch(function (err) {
        if (err.name === 'AbortError') {
          chip('stopped');
          kitCall({ rzpKit: 'emit', event: 'agent_aborted' });
        } else {
          chip('error');
          addMsg('model', 'error: ' + err.message);
        }
      })
      .finally(function () {
        sendBtn.disabled = false;
        save();
      });
  }

  async function send() {
    if (sendBtn.disabled) return;
    var text = q.value.trim();
    if (!text) return;
    q.value = '';
    addMsg('user', text);
    messages.push({ role: 'user', parts: [{ text: text }] });
    save();

    kitCall({ rzpKit: 'newTask' });
    kitCall({ rzpKit: 'emit', event: 'task_start' }); // spec §8: task_start = message send

    await runLoop();
  }

  sendBtn.onclick = send;
  q.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') send();
  });
  stopBtn.onclick = function () {
    if (abort) abort.abort();
  };

  // resume after a store navigation destroyed the iframe mid-loop
  (function resume() {
    if (!messages.length) return;
    var last = messages[messages.length - 1];
    var parts = (last && last.parts) || [];
    if (last && last.role === 'user' && parts[0] && parts[0].functionResponse) {
      chip('resuming…');
      runLoop();
    } else if (last && last.role === 'model' && parts[0] && parts[0].functionCall) {
      // died before the tool response landed — the navigation itself was the effect
      var call = parts[0].functionCall;
      messages.push({
        role: 'user',
        parts: [{ functionResponse: { name: call.name, response: { result: { ok: true, resumed: true } } } }],
      });
      save();
      chip('resuming…');
      runLoop();
    }
  })();
})();
