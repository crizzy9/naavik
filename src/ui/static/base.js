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
    if (e.target.tagName === 'DIALOG' && e.target.hasAttribute('open')) {
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
})();
