/* Naavik keys.js — page-scoped keyboard shortcut registry.
 *
 * Plan 08 ships an empty registry skeleton. Plan 09 adds the Discover and
 * Discover · review handler maps when those pages land.
 *
 * Page is keyed by `<body data-template="...">`, set from the FastAPI route
 * name (parameterized — e.g. `/discover/:id` not `/discover/123`) so shortcuts
 * remain consistent across param-bearing routes.
 */
(function () {
  'use strict';

  // Registry: { templatePath → { keyComboString → handlerFn } }
  // Empty during plan 08; plan 09 registers via window.naavikKeys.register.
  var handlers = {};

  function activeTabIs(tab) {
    var el = document.querySelector('[data-active-tab]');
    return el && el.dataset.activeTab === tab;
  }

  function comboFor(e) {
    var prefix = '';
    if (e.metaKey)  prefix += 'meta+';
    if (e.ctrlKey)  prefix += 'ctrl+';
    if (e.altKey)   prefix += 'alt+';
    if (e.shiftKey) prefix += 'shift+';
    return prefix + e.key;
  }

  window.addEventListener('keydown', function (e) {
    // Don't hijack typing surfaces.
    var tag = (e.target && e.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (e.target && e.target.isContentEditable)) {
      return;
    }
    if (e.repeat) return;
    var page = document.body.dataset.template || '';
    var map = handlers[page];
    if (!map) return;
    var combo = comboFor(e);
    var fn = map[combo] || map[e.key];
    if (typeof fn === 'function') {
      e.preventDefault();
      fn(e);
    }
  });

  // Public registration API (used from page templates / plan 09).
  function click(id) {
    var el = document.getElementById(id);
    if (el) el.click();
  }

  window.naavikKeys = {
    register: function (templatePath, keyMap) {
      handlers[templatePath] = Object.assign(handlers[templatePath] || {}, keyMap);
    },
    activeTabIs: activeTabIs,
    click: click,
  };

  // Plan 09 — register Discover + Discover-review handler maps. Page-bound
  // helpers (triggerRewriteSelection etc.) are no-ops here; pages can override
  // via naavikKeys.register if they want richer behavior.
  window.naavikKeys.register("/discover", {
    "ArrowLeft":  function () { click("skip-btn"); },
    "ArrowRight": function () { click("auto-apply-btn"); },
    "ArrowUp":    function () { click("save-btn"); },
    "Enter":      function () { click("review-btn"); },
  });

  window.naavikKeys.register("/discover/:id", {
    "meta+k":     function () {
      if (!activeTabIs("cover-letter")) return;
      click("apply-rewrite-selection");
    },
    "meta+Enter": function () {
      if (!activeTabIs("cover-letter")) return;
      click("apply-cover-regen");
    },
    "meta+c":     function () {
      if (!activeTabIs("cover-letter")) return;
      var ta = document.getElementById("apply-cover-letter-text");
      if (ta && navigator.clipboard) navigator.clipboard.writeText(ta.innerText || "");
    },
  });
})();
