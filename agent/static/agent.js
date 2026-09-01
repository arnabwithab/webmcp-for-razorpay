// agent/static/agent.js — client-held loop: getTools → /agent/turn → executeTool → chips (spec §7).
// Caps: 8 turns / 60s / AbortController on STOP. Server ts authoritative; chips are cosmetic.
(function () {
  var STORE_ORIGIN = 'http://localhost:8000'; // spec §9 fixed
  var MAX_TURNS = 8;
  var MAX_MS = 60000;

  var chat = document.getElementById('chat');
  var chips = document.getElementById('chips');
  var q = document.getElementById('q');
  var sendBtn = document.getElementById('send');
  var stopBtn = document.getElementById('stop');

  var messages = [];
  var abort = null;
  var pendingToolResult = null; // functionResponse waiting to be appended
  var lastChip = null;

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

  function kit() {
    return window.RazorpayAgentKit || null;
  }

  // tool → audit event mapping (spec §8 agent arm)
  var TOOL_EVENT = {
    'search-catalog': 'results_viewed',
    'show-product': 'product_viewed',
    'add-to-cart': 'cart_updated',
    'read-cart': null,
    checkout: null, // kit emits checkout_opened itself
    'resume-checkout': null,
  };

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

  function norm(n) { return String(n).replace(/_/g, '-'); }
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
      if (match && match.execute) return await match.execute(args);
    }
    throw new Error('tool not found: ' + name);
  }

  async function loop() {
    var deadline = Date.now() + MAX_MS;
    for (var turn = 0; turn < MAX_TURNS; turn++) {
      if (abort.signal.aborted) throw new DOMException('aborted', 'AbortError');
      if (Date.now() > deadline) { chip('stopped — 60s cap'); return; }

      if (pendingToolResult) {
        messages.push(pendingToolResult);
        pendingToolResult = null;
      }

      chip('thinking…');
      var tools = await getTools();
      var serializableTools = tools.map(function (t) {
        return { name: t.name, description: t.description, parameters: t.parameters };
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
        chip(call.name + '…');
        messages.push({ role: 'model', parts: [{ functionCall: call }] });
        var evt = TOOL_EVENT[call.name];
        if (evt && kit()) kit().emit(evt, { tool: call.name });
        try {
          var result = await executeTool(call.name, call.args);
          pendingToolResult = {
            role: 'user',
            parts: [{ functionResponse: { name: call.name, response: { result: result } } }],
          };
        } catch (err) {
          pendingToolResult = {
            role: 'user',
            parts: [{ functionResponse: { name: call.name, response: { error: String(err) } } }],
          };
        }
        continue;
      }

      if (textPart) {
        chip('');
        addMsg('model', textPart.text);
        messages.push({ role: 'model', parts: [{ text: textPart.text }] });
      }
      return; // no function call → turn complete
    }
    chip('stopped — turn cap');
  }

  async function send() {
    var text = q.value.trim();
    if (!text) return;
    q.value = '';
    addMsg('user', text);
    messages.push({ role: 'user', parts: [{ text: text }] });

    var k = kit();
    if (k) {
      k.newTask();
      k.emit('task_start'); // spec §8: task_start = message send
    }

    abort = new AbortController();
    sendBtn.disabled = true;
    try {
      await loop();
    } catch (err) {
      if (err.name === 'AbortError') {
        chip('stopped');
        if (k) k.emit('agent_aborted');
      } else {
        chip('error');
        addMsg('model', 'error: ' + err.message);
      }
    } finally {
      sendBtn.disabled = false;
    }
  }

  sendBtn.onclick = send;
  q.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') send();
  });
  stopBtn.onclick = function () {
    if (abort) abort.abort();
  };
})();
