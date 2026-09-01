/**
 * kit/webmcp-store-tools.js — webmcpify-generated store-native tools (spec G3):
 * search-catalog, show-product, add-to-cart, read-cart. Registered into the store
 * page's model context via the vendored webmcpify runtime; every execute() uses the
 * store's own code paths (same endpoints the UI uses). Payment tools are NOT here —
 * the kit owns money (webmcpify policy, spec §5.1).
 */
(function () {
  'use strict';
  if (window.__rzpStoreToolsLoaded) return;
  window.__rzpStoreToolsLoaded = true;

  var AGENT_ORIGIN = window.__RZP_AGENT__ || 'http://localhost:8001';
  var kit = function () { return window.RazorpayAgentKit; }; // loads after this file

  function gql(query, variables) {
    return fetch('/api/graphql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ query: query, variables: variables || {} }),
    }).then(function (r) { return r.json(); });
  }

  var SEARCH_Q =
    'query($f:[FilterInput]){ products(filters:$f){ items { name sku url ' +
    'price { regular { value currency } } } } }';

  function searchItems(term, limit) {
    return gql(SEARCH_Q, {
      f: [
        { key: 'keyword', operation: 'eq', value: term },
        { key: 'limit', operation: 'eq', value: String(limit || 10) },
      ],
    }).then(function (d) {
      return ((d.data || {}).products || {}).items || [];
    });
  }

  function priceText(p) {
    var reg = ((p || {}).regular || {});
    return reg.currency === 'INR' ? '\u20B9' + reg.value : String(reg.value);
  }

  var CART_Q =
    '{ myCart { uuid totalQty grandTotal { value } ' +
    'items { sku productName qty } } }';

  function findProductBySku(sku) {
    return gql('{ categories { items { products { items { name sku url price { regular { value currency } } } } } } }').then(
      function (d) {
        var all = [];
        var cats = ((d.data || {}).categories || {}).items || [];
        cats.forEach(function (c) {
          var prods = (c.products && c.products.items) || [];
          prods.forEach(function (p) { all.push(p); });
        });
        // categories fallback is capped weirdly; also try the direct products list via search with limit
        for (var i = 0; i < all.length; i++) if (all[i].sku === sku) return all[i];
        return null;
      }
    );
  }

  function buildTools(rt) {
    return [
    {
      name: 'search-catalog',
      description:
        'Search the store catalog. Navigates the page to the search results so the user sees the filtered grid. Returns matching products (sku, name, url, price).',
      parameters: {
        type: 'object',
        properties: { query: { type: 'string', description: 'search text' } },
        required: ['query'],
      },
      execute: rt.singleFlight(function (input) {
        var q = String((input && input.query) || '').trim();
        if (!q) return Promise.resolve({ ok: false, error: 'query is required' });
        return searchItems(q, 10).then(function (items) {
          var out = items.map(function (p) {
            return {
              sku: p.sku,
              name: p.name,
              url: p.url,
              price: priceText(p.price),
            };
          });
          window.location.href = '/search?keyword=' + encodeURIComponent(q);
          if (kit()) kit().emit('results_viewed', { tool: 'search-catalog', query: q });
          return { ok: true, count: out.length, items: out };
        });
      }),
    },
    {
      name: 'show-product',
      description:
        'Open a product page by SKU. Navigates the page to the product so the user sees it. Returns the product summary.',
      parameters: {
        type: 'object',
        properties: { sku: { type: 'string', description: 'product SKU' } },
        required: ['sku'],
      },
      execute: rt.singleFlight(function (input) {
        var sku = String((input && input.sku) || '').trim();
        if (!sku) return Promise.resolve({ ok: false, error: 'sku is required' });
        return findProductBySku(sku).then(function (p) {
          if (!p) {
            return { ok: false, error: 'no product found for sku ' + sku };
          }
          window.location.href = p.url;
          if (kit()) kit().emit('product_viewed', { tool: 'show-product', sku: sku });
          return {
            ok: true,
            sku: p.sku,
            name: p.name,
            url: p.url,
            price: priceText(p.price),
          };
        });
      }),
    },
    {
      name: 'add-to-cart',
      description:
        "Add the currently viewed product to the cart by clicking the store's own Add to cart button. Must be on the product page first (use show-product).",
      parameters: {
        type: 'object',
        properties: { sku: { type: 'string' }, qty: { type: 'integer', minimum: 1 } },
        required: ['sku'],
      },
      execute: rt.singleFlight(function (input) {
        var sku = String((input && input.sku) || '').trim();
        var qty = Math.max(1, parseInt((input && input.qty) || 1, 10) || 1);
        if (!sku) return Promise.resolve({ ok: false, error: 'sku is required' });

        return findProductBySku(sku).then(function (p) {
          if (!p) {
            return { ok: false, error: 'no product found for sku ' + sku };
          }
          var targetPath = new URL(p.url, location.origin).pathname;
          if (location.pathname !== targetPath) {
            return {
              ok: false,
              error:
                'not on the product page for ' + sku + ' — call show-product first, then retry',
            };
          }
          var form = document.getElementById('productForm');
          var qtyInput = form && form.querySelector('input[name="qty"]');
          var btn = form && Array.prototype.find.call(form.querySelectorAll('button'), function (b) {
            return /add to cart/i.test(b.textContent || '');
          });
          if (!form || !qtyInput || !btn) {
            return { ok: false, error: 'add-to-cart form not found on this page' };
          }

          return gql(CART_Q).then(function (before) {
            var beforeCount = (((before.data || {}).myCart || {}).totalQty) || 0;

            var setter = Object.getOwnPropertyDescriptor(
              window.HTMLInputElement.prototype,
              'value'
            ).set;
            setter.call(qtyInput, String(qty));
            qtyInput.dispatchEvent(new Event('input', { bubbles: true }));
            btn.click();

            // wait for the store's own cart sync to reflect the add (visible badge)
            var tries = 0;
            return new Promise(function (resolve) {
              var poll = setInterval(function () {
                tries += 1;
                gql(CART_Q).then(function (after) {
                  var cart = (after.data || {}).myCart;
                  var count = (cart && cart.totalQty) || 0;
                  if (count > beforeCount) {
                    clearInterval(poll);
                    if (kit()) kit().emit('cart_updated', { tool: 'add-to-cart', sku: sku, qty: qty });
                    resolve({ ok: true, cartCount: count, sku: sku });
                  } else if (tries >= 10) {
                    clearInterval(poll);
                    resolve({
                      ok: false,
                      error: 'cart did not update after clicking Add to cart',
                    });
                  }
                });
              }, 500);
            });
          });
        });
      }),
    },
    {
      name: 'read-cart',
      description: 'Read the current cart: items (sku, name, qty) and totals.',
      parameters: { type: 'object', properties: {}, required: [] },
      execute: function () {
        return gql(CART_Q).then(function (d) {
          var cart = (d.data || {}).myCart;
          if (!cart) return { ok: true, totalQty: 0, items: [] };
          return {
            ok: true,
            totalQty: cart.totalQty || 0,
            grandTotal: cart.grandTotal ? cart.grandTotal.value : null,
            items: (cart.items || []).map(function (it) {
              return { sku: it.sku, name: it.productName, qty: it.qty };
            }),
          };
        });
      },
    },
  ];
  }

  function boot(retries) {
    var rt = window.webmcpify;
    if (!rt) {
      // runtime may land after us (injection race); retry instead of bailing
      if (retries > 0) setTimeout(function () { boot(retries - 1); }, 200);
      return;
    }
    var TOOLS = buildTools(rt);
    rt.createToolScope('evershop-store', TOOLS, { exposedTo: [AGENT_ORIGIN], validate: true });
    window.RazorpayStoreTools = { tools: TOOLS }; // flag-less fallback + smoke inspection
  }

  boot(25); // ponytail: ~5s of retries covers sidecar restarts between loads
})();
