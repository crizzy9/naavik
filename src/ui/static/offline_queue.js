/* Naavik offline_queue.js — IndexedDB-backed retry buffer for onboarding autosave.
 *
 * Plan 57 / 0.2.7.13 — INTERACTIONS.md § H.3 deferred surface. On
 * `htmx:sendError` for mutating /api/v1/profile/* or /api/v1/onboarding/*
 * requests, capture the request payload + queue in IndexedDB. On the
 * `online` event AND on DOMContentLoaded-after-reconnect, drain the queue
 * via fetch(); exponential backoff (1/2/4/8/16s) up to 5 retries, then
 * drop + dispatch `naavik:offline-queue-drop` so the page can toast.
 *
 * Path-gated to `/onboarding/*` at the top of the IIFE so the IndexedDB
 * open cost stays off other pages until a follow-up extends the surface
 * to profile-edit + Settings (see plan §  Item 2).
 *
 * Idempotency guard mirrors base.js — `hx-boost="true"` re-executes this
 * script on every navigation; the guard makes the IIFE a no-op after the
 * first run.
 */
(function () {
  'use strict';

  // Path gate — only attach listeners on the onboarding surface today.
  // Follow-up rows extend the prefix list to /profile/edit + /settings.
  if (!window.location.pathname.startsWith('/onboarding')) {
    return;
  }

  // Idempotency guard for hx-boost re-execution (mirrors base.js:13-22).
  if (window._naavikOfflineQueueLoaded) {
    return;
  }
  window._naavikOfflineQueueLoaded = true;

  var DB_NAME = 'naavik_offline_queue';
  var STORE = 'pending';
  var MAX_RETRIES = 5;
  var BACKOFF_MS = [1000, 2000, 4000, 8000, 16000];
  // Replay candidates — restrict to the autosave surface so we never replay
  // arbitrary user requests captured by the htmx:sendError net.
  var REPLAY_PREFIXES = ['/api/v1/profile', '/api/v1/onboarding'];

  function openDb() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
        }
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  function putPending(entry) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, 'readwrite');
        var store = tx.objectStore(STORE);
        var req = store.add(entry);
        req.onsuccess = function () { resolve(req.result); };
        req.onerror = function () { reject(req.error); };
      });
    });
  }

  function getAllPending() {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, 'readonly');
        var store = tx.objectStore(STORE);
        var req = store.getAll();
        req.onsuccess = function () { resolve(req.result || []); };
        req.onerror = function () { reject(req.error); };
      });
    });
  }

  function deletePending(id) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, 'readwrite');
        var store = tx.objectStore(STORE);
        var req = store.delete(id);
        req.onsuccess = function () { resolve(); };
        req.onerror = function () { reject(req.error); };
      });
    });
  }

  function updatePending(entry) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, 'readwrite');
        var store = tx.objectStore(STORE);
        var req = store.put(entry);
        req.onsuccess = function () { resolve(); };
        req.onerror = function () { reject(req.error); };
      });
    });
  }

  function isReplayable(url, method) {
    if (!url || !method) return false;
    var m = method.toUpperCase();
    if (m !== 'POST' && m !== 'PUT' && m !== 'PATCH' && m !== 'DELETE') return false;
    for (var i = 0; i < REPLAY_PREFIXES.length; i++) {
      if (url.indexOf(REPLAY_PREFIXES[i]) === 0) return true;
    }
    return false;
  }

  function captureSendError(evt) {
    // htmx:sendError detail carries xhr + requestConfig
    var rc = evt && evt.detail && evt.detail.requestConfig;
    if (!rc) return;
    var url = rc.path || rc.url;
    var method = rc.verb || rc.method || 'POST';
    if (!isReplayable(url, method)) return;

    // Capture request shape. headers may be a Headers instance or plain obj.
    var headers = {};
    if (rc.headers) {
      if (typeof rc.headers.forEach === 'function') {
        rc.headers.forEach(function (v, k) { headers[k] = v; });
      } else {
        for (var k in rc.headers) {
          if (Object.prototype.hasOwnProperty.call(rc.headers, k)) {
            headers[k] = rc.headers[k];
          }
        }
      }
    }
    // X-CSRF-Token header rides on every HTMX request via base.html hx-headers.
    var csrf = document.querySelector('meta[name="csrf-token"]');
    if (csrf && !headers['X-CSRF-Token']) {
      headers['X-CSRF-Token'] = csrf.getAttribute('content') || '';
    }

    var entry = {
      url: url,
      method: method.toUpperCase(),
      headers: headers,
      body: rc.parameters || rc.body || null,
      target_id: rc.target ? (rc.target.id || null) : null,
      retry_count: 0,
      queued_at: Date.now(),
    };
    putPending(entry).catch(function (err) {
      // IndexedDB failure is non-fatal — log + drop.
      console.warn('[naavik] offline_queue: failed to persist entry', err);
    });
  }

  function replayEntry(entry) {
    var init = {
      method: entry.method,
      headers: entry.headers || {},
      credentials: 'same-origin',
    };
    // Serialize body: HTMX captures `parameters` as a plain object for form
    // posts. Send as application/x-www-form-urlencoded unless caller had a
    // JSON content-type set.
    var ct = (init.headers['Content-Type'] || init.headers['content-type'] || '').toLowerCase();
    if (entry.body != null) {
      if (ct.indexOf('json') !== -1) {
        init.body = typeof entry.body === 'string' ? entry.body : JSON.stringify(entry.body);
      } else {
        var params = new URLSearchParams();
        if (typeof entry.body === 'object') {
          for (var k in entry.body) {
            if (Object.prototype.hasOwnProperty.call(entry.body, k)) {
              params.append(k, entry.body[k]);
            }
          }
          init.body = params.toString();
          if (!init.headers['Content-Type']) {
            init.headers['Content-Type'] = 'application/x-www-form-urlencoded';
          }
        } else {
          init.body = String(entry.body);
        }
      }
    }
    return fetch(entry.url, init);
  }

  function dropEntry(entry) {
    try {
      window.dispatchEvent(new CustomEvent('naavik:offline-queue-drop', {
        detail: { url: entry.url, method: entry.method },
      }));
    } catch (e) {
      // CustomEvent not constructible in very old browsers — silent fallback.
    }
  }

  function drainQueue() {
    if (!navigator.onLine) return;
    getAllPending().then(function (entries) {
      entries.forEach(function (entry) {
        replayEntry(entry).then(function (resp) {
          if (resp.ok) {
            deletePending(entry.id);
          } else {
            scheduleRetry(entry);
          }
        }).catch(function () {
          scheduleRetry(entry);
        });
      });
    }).catch(function (err) {
      console.warn('[naavik] offline_queue: drain failed', err);
    });
  }

  function scheduleRetry(entry) {
    var next = (entry.retry_count || 0) + 1;
    if (next >= MAX_RETRIES) {
      dropEntry(entry);
      deletePending(entry.id);
      return;
    }
    entry.retry_count = next;
    var delay = BACKOFF_MS[next - 1] || BACKOFF_MS[BACKOFF_MS.length - 1];
    updatePending(entry).then(function () {
      setTimeout(function () {
        if (navigator.onLine) replayEntry(entry).then(function (resp) {
          if (resp.ok) deletePending(entry.id);
          else scheduleRetry(entry);
        }).catch(function () { scheduleRetry(entry); });
      }, delay);
    });
  }

  // Wire up listeners. base.js attaches the global Lucide hooks; this file
  // owns only the offline-queue surface so a regression here can't poison
  // other handlers.
  document.body.addEventListener('htmx:sendError', captureSendError);
  window.addEventListener('online', drainQueue);
  if (document.readyState !== 'loading') {
    if (navigator.onLine) drainQueue();
  } else {
    document.addEventListener('DOMContentLoaded', function () {
      if (navigator.onLine) drainQueue();
    });
  }
})();
