/* Naavik base.js — six cross-cutting handlers per INTERACTIONS.md § I.1
 * + the mobile sidebar drawer toggle (DaisyUI was removed in plan 08).
 *
 * No bundlers. Loaded once from base.html after Lucide / HTMX / Sortable.
 *
 * Plan 09a follow-up — IDEMPOTENT GUARD. With `hx-boost="true"` on <body>,
 * HTMX re-executes <script src="/static/base.js"> on every navigation. Without
 * this guard, every listener attaches N times after N navigations — the
 * sidebar click handler in particular ends up toggling twice (net no change),
 * which is how the user reproduced "toggle works on first page, dies after
 * navigation". Guard makes the IIFE a no-op on re-execution.
 */
(function () {
  'use strict';
  if (window._naavikBaseLoaded) {
    // Re-execution path (after hx-boost swap). The global listeners attached on
    // the first run are still active, so they handle the new page DOM. Just
    // paint icons immediately for the new content and exit before re-attaching.
    if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
    return;
  }
  window._naavikBaseLoaded = true;

  // ---------------------------------------------------------------- //
  // 1. Lucide reinit                                                 //
  // Paint icons after every HTMX swap. Initial paint runs on         //
  // DOMContentLoaded.                                                //
  // ---------------------------------------------------------------- //
  var _lucideMissingLogged = false;
  function reinitLucide() {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    } else if (!_lucideMissingLogged) {
      _lucideMissingLogged = true;
      console.warn('[naavik] window.lucide missing — Lucide CDN failed to load or expose its global. Icons will not render.');
    }
  }
  // If DOMContentLoaded already fired before this script ran, the listener
  // never fires. Cover both paths so initial paint always happens.
  if (document.readyState !== 'loading') {
    reinitLucide();
  } else {
    document.addEventListener('DOMContentLoaded', reinitLucide);
  }
  document.body.addEventListener('htmx:afterSwap', reinitLucide);
  document.body.addEventListener('htmx:oobAfterSwap', reinitLucide);

  // ---------------------------------------------------------------- //
  // 2. Sortable.js auto-init                                         //
  // Initialize every `[data-sortable="true"]` after settle. Marker   //
  // `el._sortable` prevents double-init.                             //
  // ---------------------------------------------------------------- //
  function initSortables() {
    if (!window.Sortable) return;
    document.querySelectorAll('[data-sortable="true"]').forEach(function (el) {
      if (el._sortable) return;
      el._sortable = window.Sortable.create(el, {
        handle: '.drag-handle',
        animation: 150,
        ghostClass: 'opacity-40',
      });
    });
  }
  document.addEventListener('DOMContentLoaded', initSortables);
  document.body.addEventListener('htmx:afterSettle', initSortables);

  // ---------------------------------------------------------------- //
  // 3. Modal-close listener                                          //
  // Server returns `HX-Trigger: closeModal` on save; HTMX dispatches //
  // a `closeModal` event on body.                                    //
  // ---------------------------------------------------------------- //
  document.body.addEventListener('closeModal', function () {
    document.querySelectorAll('dialog[open]').forEach(function (d) { d.close(); });
  });

  // ---------------------------------------------------------------- //
  // 3a. Native <dialog> backdrop click (Issue 14)                    //
  // Clicks that land on the <dialog> element itself (not its inner   //
  // content) must close it — this is the canonical "click outside"   //
  // pattern for the native element. The custom `.modal-backdrop` div //
  // pattern in INTERACTIONS.md § E.1 doesn't reliably bubble through //
  // the dialog's stacking context.                                   //
  // ---------------------------------------------------------------- //
  document.body.addEventListener('click', function (e) {
    // Only close truly-modal dialogs (shown via showModal(); clicks on the
    // ::backdrop report the dialog itself as target). For `<dialog open>`
    // (non-modal — how our HTMX modals render), a click reporting the
    // DIALOG element is INSIDE the dialog (its own padding/gaps), and
    // closing there made modals vanish under the user's cursor (the
    // "+ Add by URL shows no input" bug).
    if (e.target.tagName === 'DIALOG' && e.target.hasAttribute('open') && e.target.matches(':modal')) {
      e.target.close();
    }
  });

  // ---------------------------------------------------------------- //
  // 4. Toast auto-dismiss                                            //
  // success / info → remove after 4s. warning / danger persist.      //
  // ---------------------------------------------------------------- //
  function autoDismissToasts(target) {
    if (!target) return;
    var toasts = target.querySelectorAll('.toast.toast-success, .toast.toast-info');
    toasts.forEach(function (t) {
      if (t._dismissArmed) return;
      t._dismissArmed = true;
      setTimeout(function () {
        if (!t.isConnected) return;
        t.style.transition = 'opacity 200ms ease';
        t.style.opacity = '0';
        setTimeout(function () { t.remove(); }, 220);
      }, 4000);
    });
  }
  document.body.addEventListener('htmx:oobAfterSwap', function (e) { autoDismissToasts(e.target); });
  document.body.addEventListener('htmx:afterSwap', function (e) { autoDismissToasts(e.detail.target); });
  // Also catch toasts that landed via direct insertion before any swap fires.
  document.addEventListener('DOMContentLoaded', function () { autoDismissToasts(document.body); });

  // ---------------------------------------------------------------- //
  // 5. Optimistic rollback                                           //
  // Per INTERACTIONS.md § H.4. Pre-action stash lives in             //
  // `el.dataset.rollback` (URI-encoded outerHTML). On error: restore.//
  // ---------------------------------------------------------------- //
  function rollback(e) {
    var el = e.detail && e.detail.target;
    var stash = el && el.dataset && el.dataset.rollback;
    if (!stash) return;
    el.outerHTML = decodeURIComponent(stash);
    showToast('danger', "Couldn't save — restored. Try again?");
  }
  document.body.addEventListener('htmx:responseError', rollback);
  document.body.addEventListener('htmx:sendError', rollback);

  // Settings saves: htmx never swaps error responses, so a failed PUT used
  // to leave #settings-save-result blank ("Save did nothing"). Surface the
  // status + server detail honestly. textContent assembly avoids injecting
  // server-controlled strings as HTML.
  function settingsSaveError(e) {
    var slot = document.getElementById('settings-save-result');
    if (!slot) return;
    var xhr = e.detail && e.detail.xhr;
    var detail = '';
    if (xhr && xhr.responseText) {
      try { detail = JSON.parse(xhr.responseText).detail || ''; } catch (err) { detail = ''; }
    }
    var span = document.createElement('span');
    span.className = 'text-rose-300';
    span.textContent = 'Save failed' + (xhr ? ' (' + xhr.status + ')' : '') +
      (detail ? ' - ' + detail : '');
    slot.replaceChildren(span);
  }
  document.body.addEventListener('htmx:responseError', settingsSaveError);
  document.body.addEventListener('htmx:sendError', settingsSaveError);

  // ---------------------------------------------------------------- //
  // 6. Upload progress                                               //
  // ---------------------------------------------------------------- //
  document.body.addEventListener('htmx:xhr:progress', function (e) {
    var bar = document.getElementById('upload-progress');
    if (bar && e.detail && e.detail.lengthComputable) {
      bar.value = (e.detail.loaded / e.detail.total) * 100;
    }
  });

  // ---------------------------------------------------------------- //
  // 7. Anchor scroll-spy (Issue 9)                                   //
  // Right-rail [data-anchor-nav] receives a [data-active-anchor]     //
  // attribute as the user scrolls past each <section id="...">.      //
  // CSS in styles.css scopes the active link styling off that.       //
  // ---------------------------------------------------------------- //
  function attachScrollSpy() {
    var nav = document.querySelector('[data-anchor-nav]');
    if (!nav || nav._scrollSpyAttached) return;
    // Section IDs are listed by the nav itself via [data-anchor-targets].
    var ids = (nav.getAttribute('data-anchor-targets') || '').split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    if (!ids.length) return;
    var sections = ids
      .map(function (id) { return document.getElementById(id); })
      .filter(Boolean);
    if (!sections.length) return;
    nav._scrollSpyAttached = true;

    function setActive(id) {
      if (!id) return;
      nav.setAttribute('data-active-anchor', id);
      nav.querySelectorAll('[data-anchor-link]').forEach(function (a) {
        if (a.getAttribute('data-anchor-link') === id) {
          a.classList.add('is-active');
        } else {
          a.classList.remove('is-active');
        }
      });
    }
    setActive(nav.getAttribute('data-active-anchor'));

    var observer = new IntersectionObserver(function (entries) {
      // Pick the entry closest to the top of the active band.
      var top = entries
        .filter(function (e) { return e.isIntersecting; })
        .sort(function (a, b) { return a.boundingClientRect.top - b.boundingClientRect.top; })[0];
      if (top && top.target.id) setActive(top.target.id);
    }, {
      // Active section = the one near the top of the viewport.
      rootMargin: '-20% 0% -60% 0%',
      threshold: 0,
    });

    sections.forEach(function (s) { observer.observe(s); });

    // Click on anchor link → set active immediately, don't wait for scroll-end.
    nav.addEventListener('click', function (e) {
      var link = e.target.closest('a[href^="#"]');
      if (!link) return;
      var targetId = link.getAttribute('href').slice(1);
      setActive(targetId);
    });
  }
  if (document.readyState !== 'loading') {
    attachScrollSpy();
  } else {
    document.addEventListener('DOMContentLoaded', attachScrollSpy);
  }
  document.body.addEventListener('htmx:afterSettle', attachScrollSpy);

  // ---------------------------------------------------------------- //
  // Mobile sidebar drawer toggle                                     //
  // [data-sidebar-toggle] flips `data-sidebar-open` on <body>.       //
  // CSS in styles.css translates to slide-in.                        //
  // ---------------------------------------------------------------- //
  function syncSidebarAria() {
    var open = document.body.dataset.sidebarOpen === 'true';
    document.querySelectorAll('[data-sidebar-toggle]').forEach(function (btn) {
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }
  document.body.addEventListener('click', function (e) {
    if (e.target.closest('[data-sidebar-toggle]')) {
      var open = document.body.dataset.sidebarOpen === 'true';
      document.body.dataset.sidebarOpen = open ? 'false' : 'true';
      syncSidebarAria();
      return;
    }
    if (e.target.closest('[data-sidebar-backdrop]')) {
      document.body.dataset.sidebarOpen = 'false';
      syncSidebarAria();
      return;
    }
    // Close drawer when navigating via sidebar link on mobile.
    var sidebarLink = e.target.closest('aside.sidebar a[href]');
    if (sidebarLink && window.innerWidth < 1024) {
      document.body.dataset.sidebarOpen = 'false';
      syncSidebarAria();
    }
  });
  // Keep aria-expanded in sync when no click fires (history pop, back-button
  // restore, hx-boost swap).
  if (document.readyState !== 'loading') {
    syncSidebarAria();
  } else {
    document.addEventListener('DOMContentLoaded', syncSidebarAria);
  }
  document.body.addEventListener('htmx:afterSwap', syncSidebarAria);

  // ---------------------------------------------------------------- //
  // showToast helper — used by rollback handler. Kept tiny.          //
  // ---------------------------------------------------------------- //
  function showToast(tone, message) {
    var region = document.getElementById('toast-region');
    if (!region) return;
    var toneClass = ({
      success: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-200',
      info:    'bg-sky-500/10 border-sky-500/30 text-sky-200',
      warning: 'bg-amber-500/10 border-amber-500/30 text-amber-200',
      danger:  'bg-rose-500/10 border-rose-500/30 text-rose-200',
    })[tone] || 'bg-slate-800/90 border-slate-700 text-slate-200';
    var t = document.createElement('div');
    t.className = 'toast toast-' + tone + ' flex items-start gap-2.5 px-3 py-2.5 rounded-lg shadow-lg max-w-md border ' + toneClass;
    t.setAttribute('role', tone === 'danger' || tone === 'warning' ? 'alert' : 'status');
    t.innerHTML =
      '<span class="text-sm flex-1">' + escapeHtml(message) + '</span>' +
      '<button type="button" class="text-current opacity-70 hover:opacity-100" aria-label="Dismiss">&times;</button>';
    t.querySelector('button').addEventListener('click', function () { t.remove(); });
    region.insertBefore(t, region.firstChild);
    autoDismissToasts(region);
  }
  window.naavikShowToast = showToast;

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  // ---------------------------------------------------------------- //
  // HX-Trigger { showToast: { text, tone? } } → naavikShowToast.     //
  // Routes can emit toasts by setting                                //
  //   response.headers["HX-Trigger"] = json.dumps({                  //
  //     "showToast": {"text": "...", "tone": "info"}                 //
  //   })                                                             //
  // ---------------------------------------------------------------- //
  document.body.addEventListener('showToast', function (e) {
    var detail = e.detail || {};
    var text = typeof detail === 'string' ? detail : (detail.text || detail.value || '');
    if (!text) return;
    var tone = detail.tone || 'info';
    showToast(tone, text);
  });

  // ---------------------------------------------------------------- //
  // 8a. Server-event toasts (P5 universal feedback).                 //
  // These HX-Trigger events used to fire into the void — no listener //
  // existed, so degraded bundles / retries / deletions were silent.  //
  // ---------------------------------------------------------------- //
  var _eventToasts = {
    'bundle-generated': ['success', 'Documents generated.'],
    'bundle-degraded': ['warning', 'Bundle generated with degradations — check the review workspace.'],
    'parse-fidelity-warning': ['info', 'Generated resume parses below the comfort tier — worth a manual look.'],
    'applicationRetried': ['success', 'Retry queued.'],
    'bulletDeleted': ['info', 'Bullet deleted.'],
  };
  Object.keys(_eventToasts).forEach(function (name) {
    document.body.addEventListener(name, function () {
      showToast(_eventToasts[name][0], _eventToasts[name][1]);
    });
  });

  // ---------------------------------------------------------------- //
  // 8b. Generic error toast — no failed operation is ever silent.    //
  // Skipped when the trigger declares hx-target-error (it renders    //
  // its own inline error), when optimistic rollback owns the toast,  //
  // or when the settings-save handler owns the slot.                 //
  // ---------------------------------------------------------------- //
  function genericErrorToast(e) {
    var elt = e.detail && e.detail.elt;
    if (elt && elt.closest && elt.closest('[hx-target-error]')) return;
    var tgt = e.detail && e.detail.target;
    if (tgt && tgt.dataset && tgt.dataset.rollback) return;
    if (tgt && tgt.id === 'settings-save-result') return;
    if (document.getElementById('settings-save-result')) return; // settingsSaveError owns it
    var xhr = e.detail && e.detail.xhr;
    var status = xhr ? xhr.status : 0;
    var detail = '';
    if (xhr && xhr.responseText && xhr.responseText.length < 300) {
      try { detail = JSON.parse(xhr.responseText).detail || ''; } catch (err) { detail = ''; }
    }
    if (typeof detail !== 'string') detail = '';
    showToast('danger', 'Request failed' + (status ? ' (' + status + ')' : '') + (detail ? ' — ' + detail : '.'));
  }
  document.body.addEventListener('htmx:responseError', genericErrorToast);
  document.body.addEventListener('htmx:sendError', function () {
    showToast('danger', 'Network error — the app could not be reached.');
  });

  // ---------------------------------------------------------------- //
  // 8. Tracking list — bulk-action selection helpers (plan 80).      //
  // Per-row checkboxes mark a paired hidden `application_ids` input  //
  // active so hx-include picks it up on toolbar submit. Bar          //
  // visibility tracks the live count.                                //
  // ---------------------------------------------------------------- //
  function _trackingPairHiddenInput(checkbox) {
    var appId = checkbox.getAttribute('data-application-id');
    if (!appId) return null;
    return document.querySelector('input[type=hidden][data-application-id-input="' + appId + '"]');
  }
  function trackingBulkSelectionChange() {
    var checks = document.querySelectorAll('[data-tracking-row-select]');
    var checked = 0;
    checks.forEach(function (c) {
      var hidden = _trackingPairHiddenInput(c);
      if (hidden) hidden.disabled = !c.checked;
      if (c.checked) checked += 1;
    });
    var bar = document.getElementById('tracking-bulk-action-bar');
    if (bar) {
      var active = checked > 0;
      bar.setAttribute('data-bulk-active', active ? 'true' : 'false');
      bar.hidden = !active;
      bar.setAttribute('data-bulk-count-current', String(checked));
      var label = bar.querySelector('[data-bulk-count]');
      if (label) label.textContent = checked + ' selected';
    }
    var sel = document.querySelector('[data-bulk-move-select]');
    var moveBtn = document.querySelector('[data-bulk-move-btn]');
    if (moveBtn) moveBtn.disabled = checked === 0 || !sel || !sel.value;
    // Sync header "select-all" checkbox indeterminate state.
    var all = document.querySelector('[data-tracking-row-select-all]');
    if (all) {
      var total = checks.length;
      all.checked = total > 0 && checked === total;
      all.indeterminate = checked > 0 && checked < total;
    }
  }
  function trackingBulkSelectAllToggle(headerCheckbox) {
    var checked = !!headerCheckbox.checked;
    document.querySelectorAll('[data-tracking-row-select]').forEach(function (c) {
      c.checked = checked;
    });
    trackingBulkSelectionChange();
  }
  function trackingBulkClearSelection() {
    document.querySelectorAll('[data-tracking-row-select]:checked').forEach(function (c) {
      c.checked = false;
    });
    var all = document.querySelector('[data-tracking-row-select-all]');
    if (all) { all.checked = false; all.indeterminate = false; }
    trackingBulkSelectionChange();
  }
  function trackingBulkSubmitMove(event) {
    var sel = document.querySelector('[data-bulk-move-select]');
    if (!sel || !sel.value) {
      showToast('warning', 'Pick a stage to move to first.');
      return;
    }
    var form = document.getElementById('tracking-bulk-move-form');
    if (form && window.htmx) {
      window.htmx.trigger(form, 'submit');
    }
  }
  function trackingBulkExportCsv() {
    var checks = document.querySelectorAll('[data-tracking-row-select]:checked');
    var ids = Array.from(checks).map(function (c) { return c.value; }).filter(Boolean);
    if (!ids.length) {
      showToast('warning', 'Select rows to export first.');
      return;
    }
    var qs = ids.map(function (id) { return 'application_ids=' + encodeURIComponent(id); }).join('&');
    window.location.href = '/api/v1/applications/export.csv?' + qs;
  }
  // Re-sync after every HTMX swap so a fresh list fragment keeps state right.
  document.body.addEventListener('htmx:afterSwap', trackingBulkSelectionChange);
  document.body.addEventListener('change', function (e) {
    if (e.target && e.target.matches && e.target.matches('[data-bulk-move-select]')) {
      trackingBulkSelectionChange();
    }
  });
  if (document.readyState !== 'loading') {
    trackingBulkSelectionChange();
  } else {
    document.addEventListener('DOMContentLoaded', trackingBulkSelectionChange);
  }
  window.trackingBulkSelectionChange = trackingBulkSelectionChange;
  window.trackingBulkSelectAllToggle = trackingBulkSelectAllToggle;
  window.trackingBulkClearSelection = trackingBulkClearSelection;
  window.trackingBulkSubmitMove = trackingBulkSubmitMove;
  window.trackingBulkExportCsv = trackingBulkExportCsv;
})();
