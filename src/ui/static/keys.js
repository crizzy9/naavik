/* Naavik keys.js — page-scoped keyboard shortcut registry.
 *
 * Plan 08 ships an empty registry skeleton. Plan 09 adds the Discover and
 * Discover · review handler maps when those pages land.
 *
 * Page is keyed by `<body data-template="...">`, set from the FastAPI route
 * name (parameterized — e.g. `/discover/:id` not `/discover/123`) so shortcuts
 * remain consistent across param-bearing routes.
 *
 * Plan 09a follow-up — IDEMPOTENT GUARD. hx-boost re-executes this script on
 * every navigation; without the guard, the keydown listener stacks and pointer
 * handlers attach repeatedly to the same #discover-card.
 */
(function () {
  'use strict';
  if (window._naavikKeysLoaded) {
    // Re-execution path (after hx-boost swap). The keydown listener on `window`
    // and the htmx:afterSwap listener on `document.body` are still attached
    // from the first run — they handle the new page DOM automatically.
    return;
  }
  window._naavikKeysLoaded = true;

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
    "ArrowLeft":  function () { click("discover-skip-btn"); },
    "ArrowRight": function () { click("discover-auto-apply-btn"); },
    "ArrowUp":    function () { click("discover-save-btn"); },
    "Enter":      function () { click("discover-review-btn"); },
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

  // ---------------------------------------------------------------- //
  // Plan 09a · Issue 3 — Touch swipe on Discover.                    //
  // Pointer-event-based gesture handler. No library dep. Wires the   //
  // existing `swipe_card.html` `swiping_dir` stamp visual via         //
  // .is-swipe-{left,right,up} classes during the drag.                //
  // ---------------------------------------------------------------- //
  var SWIPE_STAMP_THRESHOLD = 30;   // when the stamp shows
  var SWIPE_ACTION_THRESHOLD = 80;  // when the action commits

  function attachDiscoverSwipe() {
    var card = document.getElementById('discover-card');
    if (!card || card._swipeAttached) return;
    if (document.body.dataset.template !== '/discover') return;
    card._swipeAttached = true;

    var startX = 0, startY = 0, dx = 0, dy = 0;
    var dragging = false;
    var lastTouchTapAt = 0;  // suppress the synthetic click that fires ~300ms after a touch tap

    function clearStamps() {
      card.classList.remove('is-swipe-left', 'is-swipe-right', 'is-swipe-up');
    }
    function reset() {
      card.style.transform = '';
      clearStamps();
      dx = 0; dy = 0;
    }

    card.addEventListener('pointerdown', function (e) {
      // Reserved for touch / pen — leave mouse to keyboard + buttons.
      if (e.pointerType === 'mouse') return;
      // Ignore drags that start on a button (they have their own handler).
      if (e.target.closest('button, a')) return;
      dragging = true;
      startX = e.clientX; startY = e.clientY;
      dx = 0; dy = 0;
      try { card.setPointerCapture(e.pointerId); } catch (_) {}
    });

    card.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      dx = e.clientX - startX;
      dy = e.clientY - startY;
      card.style.transform = 'translate(' + dx + 'px, ' + dy + 'px) rotate(' + (dx * 0.05) + 'deg)';
      clearStamps();
      if (dx <= -SWIPE_STAMP_THRESHOLD && dx < dy && Math.abs(dx) > Math.abs(dy)) {
        card.classList.add('is-swipe-left');
      } else if (dx >= SWIPE_STAMP_THRESHOLD && Math.abs(dx) > Math.abs(dy)) {
        card.classList.add('is-swipe-right');
      } else if (dy <= -SWIPE_STAMP_THRESHOLD && Math.abs(dy) > Math.abs(dx)) {
        card.classList.add('is-swipe-up');
      }
    });

    var TAP_THRESHOLD = 8;  // anything below this counts as a tap (not a swipe)

    function commit() {
      if (!dragging) return;
      dragging = false;
      var absX = Math.abs(dx), absY = Math.abs(dy);
      if (absX > absY && absX >= SWIPE_ACTION_THRESHOLD) {
        if (dx < 0) {
          click('discover-skip-btn');
        } else {
          click('discover-auto-apply-btn');
        }
      } else if (absY >= SWIPE_ACTION_THRESHOLD && dy < 0) {
        click('discover-save-btn');
      } else if (absX < TAP_THRESHOLD && absY < TAP_THRESHOLD) {
        // Tap — open Review & apply (in-place expand). Mobile has no buttons,
        // so the user-reachable action is "tap the card". Suppress the
        // synthetic click that browsers fire ~300ms after touchend.
        lastTouchTapAt = Date.now();
        click('discover-review-btn');
      } else {
        // Below threshold — snap back.
        reset();
        return;
      }
      // Action fired. The stub swap will replace the card; clear visuals first.
      reset();
    }
    card.addEventListener('pointerup', commit);
    // Mouse "tap" on card body (anywhere not a button / link) — also opens
    // Review & apply. Touch path goes through the pointer handlers above; this
    // covers desktop click-on-card UX (matches the SCREENS.md `tap` keycap).
    // Suppress synthetic click that browsers fire after a touch tap.
    card.addEventListener('click', function (e) {
      if (Date.now() - lastTouchTapAt < 600) return;  // synthetic post-touch click
      if (e.pointerType === 'touch' || e.pointerType === 'pen') return;
      if (e.target.closest('button, a')) return;
      click('discover-review-btn');
    });
    card.addEventListener('pointercancel', function () {
      dragging = false;
      reset();
    });
  }
  if (document.readyState !== 'loading') {
    attachDiscoverSwipe();
  } else {
    document.addEventListener('DOMContentLoaded', attachDiscoverSwipe);
  }
  document.body.addEventListener('htmx:afterSwap', attachDiscoverSwipe);
})();
