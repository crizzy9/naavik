/* Naavik base.js — six cross-cutting handlers per INTERACTIONS.md § I.1
 * + the mobile sidebar drawer toggle (DaisyUI was removed in plan 08).
 *
 * No bundlers. Loaded once from base.html after Lucide / HTMX / Sortable.
 */
(function () {
  'use strict';

  // ---------------------------------------------------------------- //
  // 1. Lucide reinit                                                 //
  // Paint icons after every HTMX swap. Initial paint runs on         //
  // DOMContentLoaded.                                                //
  // ---------------------------------------------------------------- //
  function reinitLucide() {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
  }
  document.addEventListener('DOMContentLoaded', reinitLucide);
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
  // Mobile sidebar drawer toggle                                     //
  // [data-sidebar-toggle] flips `data-sidebar-open` on <body>.       //
  // CSS in styles.css translates to slide-in.                        //
  // ---------------------------------------------------------------- //
  document.body.addEventListener('click', function (e) {
    if (e.target.closest('[data-sidebar-toggle]')) {
      var open = document.body.dataset.sidebarOpen === 'true';
      document.body.dataset.sidebarOpen = open ? 'false' : 'true';
      return;
    }
    if (e.target.closest('[data-sidebar-backdrop]')) {
      document.body.dataset.sidebarOpen = 'false';
      return;
    }
    // Close drawer when navigating via sidebar link on mobile.
    var sidebarLink = e.target.closest('aside.sidebar a[href]');
    if (sidebarLink && window.innerWidth < 1024) {
      document.body.dataset.sidebarOpen = 'false';
    }
  });

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
