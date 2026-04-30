---
Status: AWAITING REVIEW
Type: design
Authored: 2026-04-30
Last updated: 2026-04-30
Depends on: 02-mvp-master-plan
---

# 06 · Interactions spec

## Goal

Define the cross-cutting HTMX interaction patterns that every page and component template uses. The spec covers: swap conventions, form-submission patterns, SSE streams, drag-and-drop, modals + bottom sheets, keyboard shortcuts, toast notifications, and error handling. When approved, this plan's content graduates to `docs/design/INTERACTIONS.md` — the contract that page templates (plan 09) wire HTMX calls against.

## Context / why

`SCREENS.md` per-screen "Interactions" sections describe behavior screen-by-screen but don't cross-cut: every page has slightly different swap targets, form-save patterns, modal flows, and keyboard handlers. Without a cross-cutting spec, page templates re-invent each pattern slightly differently — so HTMX errors handle inconsistently, modals open/close differently per page, and keyboard shortcuts don't compose.

This plan locks the patterns. Page templates pick from this catalogue; if a screen needs a behavior not in the catalogue, the plan gets extended (and the screen's SCREENS.md entry references the new pattern).

## Proposal

### A · HTMX swap conventions

#### A.1 Naming swap targets

Every page identifies its swap targets by stable IDs. Convention: kebab-case, prefixed with the screen slug.

```html
<main id="overview-main">
  <section id="overview-priority-actions">…</section>
  <section id="overview-email-signal">…</section>
  <section id="overview-pipeline">…</section>
</main>
```

Components emit IDs only when they're a swap target. Generic components (buttons, chips) don't.

#### A.2 Default swap modes

| Pattern | `hx-swap` | When |
|---|---|---|
| Replace one chunk in place | `innerHTML` | Most fragment swaps (priority actions list refresh, pipeline strip refresh) |
| Replace the wrapper element + its contents | `outerHTML` | Per-row swaps where the row's parent shouldn't accumulate stale children (`bullet_edit_row`, `tracking_card`) |
| Append to a list | `beforeend` | Live log lines, live email signal events |
| Prepend (newest at top) | `afterbegin` | Live notifications |
| Replace the entire page | (rare) — use a real navigation instead | |

#### A.3 OOB swaps

Out-of-band swaps land in the page's other regions without being the primary swap target. Used heavily for:

- **Autosave indicator** — every per-field PUT returns the field's new value AND an OOB-swap of the autosave indicator (`<div id="autosave" hx-swap-oob="outerHTML">…</div>`).
- **Pipeline strip refresh** — submitting an application from Discover · review returns the new application card AND an OOB-swap of `#overview-pipeline` (if visible).
- **Toast notifications** — any state-changing endpoint can return an OOB toast `<div id="toast-region" hx-swap-oob="afterbegin">`.

Convention: OOB elements include `hx-swap-oob` as an HTML attribute on the root element of the partial, so the same partial can be returned both inline and OOB depending on context.

#### A.4 Targets for cross-page concerns

Three persistent IDs live on `base.html` so any page can swap into them:

```html
<body>
  <div id="modal-region"></div>      <!-- modals load here via hx-target="#modal-region" -->
  <div id="toast-region"></div>      <!-- OOB toast notifications -->
  <div id="sidebar-badge-jobs"></div><!-- job count badge in sidebar; updates via OOB -->
</body>
```

### B · Form submission patterns

Three flavors:

#### B.1 Per-field autosave on blur (Profile editor)

Every input has:

```html
<input
  type="text"
  name="full_name"
  value="{{ profile.full_name }}"
  hx-put="/api/v1/profile/full_name"
  hx-trigger="blur changed delay:500ms"
  hx-swap="none"
  hx-include="this"
/>
```

`blur changed` fires on blur only if the value changed. `delay:500ms` debounces multi-blur edits. `hx-swap="none"` because the response is consumed via OOB swaps (autosave indicator update) — see § A.3.

Server response: 200 with an OOB autosave indicator partial. Errors: 422 with an OOB toast.

#### B.2 Full-form submit (Login, Onboarding step 1)

```html
<form
  hx-post="/api/v1/auth/login"
  hx-target="#login-card"
  hx-swap="outerHTML"
  hx-disabled-elt="find button[type=submit]"
>
  <input type="email" name="email" required />
  <input type="password" name="password" required />
  <button type="submit">Sign in</button>
</form>
```

`hx-disabled-elt` disables the submit button while the request is in flight. On success, the response can be a redirect (`HX-Redirect: /` header) or a swap of the form card with a success/loading state.

#### B.3 Inline edit save (Cover letter sections, screener answers)

Click-to-edit pattern:

```html
<div id="cover-section-intro"
     hx-get="/_fragments/apply/cover-letter-section/{{ id }}/intro?mode=edit"
     hx-trigger="click"
     hx-swap="outerHTML">
  <p>{{ section_text }}</p>
</div>
```

Click swaps in an editable version with a textarea + Save button. Save POSTs back, returns the read-only version.

#### B.4 Form validation

Client-side: native HTML5 attributes (`required`, `type="email"`, `pattern`, `minlength`). HTMX `hx-validate="true"` attribute on forms enables HTMX-mediated validation messages.

Server-side: 422 response with field-level errors as a fragment (rendered above the form via OOB swap or as the primary swap target).

### C · SSE streams

Four streams in Phase 1 (per plan 04 § E). All use HTMX's SSE extension (`hx-ext="sse"`).

#### C.1 Pattern

```html
<div hx-ext="sse"
     sse-connect="/api/v1/extraction/{{ id }}/stream"
     sse-swap="progress,field,done">
  <!-- inner UI updates as events fire -->
  <div id="extraction-progress"></div>
  <div id="extraction-fields"></div>
  <div id="extraction-status">Reading your resume…</div>
</div>
```

Each `sse-swap` event name (e.g. `progress`, `field`) maps to an OOB-swap of the matching ID in the response payload.

Server-side payload (per event):

```
event: progress
data: <div id="extraction-progress">42%</div>

event: field
data: <div id="extracted-field-row-name" hx-swap-oob="outerHTML">{{ rendered_field }}</div>

event: done
data: <div id="extraction-status" hx-swap-oob="outerHTML">✓ Extracted 6 of 6 fields</div>
```

#### C.2 Reconnect / fallback

HTMX's SSE extension auto-reconnects. If reconnect fails 3× in a row, fall back to polling: a small JS snippet on `base.html` swaps `sse-connect` for `hx-trigger="every 5s"` on the same target.

For Phase 1, the fallback is a nice-to-have; the primary path is SSE.

#### C.3 Streams in scope

| Stream | URL | Events | Consumer page |
|---|---|---|---|
| Onboarding extraction | `/api/v1/extraction/{id}/stream` | `progress`, `field`, `done`, `error` | `pages/onboarding.html` |
| Cover letter generation | `POST /api/v1/applications/{id}/cover-letter/generate` (returns SSE-friendly chunked response) | `chunk`, `done` | `pages/discover_review.html` |
| Email signals | `/api/v1/tracking/email-signals` | `signal`, `stage_change` | `pages/tracking.html`, `pages/overview.html` |
| Live log tail | `/api/v1/settings/deployment/logs` | `logline` | `pages/settings.html` (Deployment tab) |

### D · Drag-and-drop

Sortable.js wraps lists that need reorder. Two cases in Phase 1:

#### D.1 Bullet reorder (Profile editor)

```html
<div id="bullet-list"
     data-sortable="true"
     hx-post="/api/v1/bullets/reorder"
     hx-trigger="end"
     hx-include="closest [data-sortable]"
     hx-vals='js:{"bullet_ids": [...document.querySelectorAll("#bullet-list [data-bullet-id]")].map(e => e.dataset.bulletId)}'>
  {% for bullet in bullets %}
    {% include "components/bullet_edit_row.html" with {"bullet": bullet} %}
  {% endfor %}
</div>
```

A small JS snippet in `base.html` initializes Sortable on every `[data-sortable="true"]`:

```javascript
document.addEventListener('htmx:afterSettle', () => {
  document.querySelectorAll('[data-sortable="true"]').forEach(el => {
    if (!el._sortable) el._sortable = Sortable.create(el, { handle: '.drag-handle', animation: 150 });
  });
});
```

The `end` event triggers the HTMX request after a drag completes. Server returns 204 No Content.

#### D.2 Tracking Kanban card move

Same Sortable.js pattern, multi-list mode (cards drag between columns):

```html
<div class="tracking-board">
  {% for column in columns %}
    <div data-sortable="true" data-column="{{ column.id }}"
         hx-post="/api/v1/applications/move"
         hx-trigger="end">
      {% for app in column.apps %}
        <div data-app-id="{{ app.id }}">{% include "components/tracking_card.html" %}</div>
      {% endfor %}
    </div>
  {% endfor %}
</div>
```

The `move` endpoint receives `{ application_id, target_column }` derived from the dragged card's new parent. Status update happens server-side.

### E · Modal + bottom-sheet pattern

Native `<dialog>` element — best a11y, free Escape handling, free backdrop click (with a small JS shim).

#### E.1 Modal open

Click trigger:

```html
<button hx-get="/_modal/bullet-editor/{{ bullet.id }}"
        hx-target="#modal-region"
        hx-swap="innerHTML">
  Edit
</button>
```

Server returns:

```html
<dialog id="bullet-editor-modal" open>
  <div class="modal-backdrop" hx-on:click="this.closest('dialog').close()"></div>
  <div class="modal-content">
    <!-- form, closes on save via hx-on:click on Cancel; hx-on:htmx:after-request for Save -->
  </div>
</dialog>
```

`<dialog>` with `open` attribute renders modal. CSS handles centering + scaling animation per DESIGN.md § Motion.

#### E.2 Modal close

- **Escape key** — native to `<dialog>`.
- **Backdrop click** — handled via the `.modal-backdrop` element's `hx-on:click`.
- **Cancel button** — `hx-on:click="document.getElementById('bullet-editor-modal').close()"`.
- **After save** — server response includes `<script>document.getElementById('bullet-editor-modal').close()</script>` OR an HTMX `HX-Trigger: closeModal` response header that a global listener handles.

#### E.3 Mobile bottom sheet

Same `<dialog>` element, different CSS:

- Desktop (≥ md breakpoint): centered modal, max-width 720px
- Mobile (< md): pinned to bottom, full width, drag-handle at top

Achieved via Tailwind responsive classes inside the modal partial. No separate component needed.

### F · Keyboard shortcut conventions

Keyboard handlers live in two places:

#### F.1 Page-scoped shortcuts (Discover)

```html
<body
  hx-on:keydown="if (event.repeat) return;
                 if (event.key === 'ArrowLeft') document.getElementById('skip-btn').click();
                 if (event.key === 'ArrowRight') document.getElementById('auto-apply-btn').click();
                 if (event.key === 'ArrowUp') document.getElementById('save-btn').click();
                 if (event.key === 'Enter' || event.key === ' ') document.getElementById('review-btn').click();">
```

Or extracted into a small shared script `src/ui/static/keys.js`:

```javascript
// keys.js — page-scoped keyboard handlers
const handlers = {
  '/discover': {
    'ArrowLeft': () => click('skip-btn'),
    'ArrowRight': () => click('auto-apply-btn'),
    'ArrowUp': () => click('save-btn'),
    'Enter': () => click('review-btn'),
  },
  '/generate/cover-letter-section': {  // when active inside DiscoverDetail
    'meta+k': () => triggerRewriteSelection(),
    'meta+Enter': () => triggerRegen(),
  },
};

window.addEventListener('keydown', (e) => {
  const page = document.body.dataset.page;
  const map = handlers[page];
  if (!map) return;
  const key = (e.metaKey ? 'meta+' : '') + (e.ctrlKey ? 'ctrl+' : '') + e.key;
  if (map[key]) { e.preventDefault(); map[key](); }
});
```

`<body data-page="/discover">` carries the active page slug.

#### F.2 Modal-scoped shortcuts

While a modal is open, page shortcuts are suspended (the modal's focus trap prevents bubble). Modal-specific shortcuts (e.g. `Cmd+Enter` to save) are wired on the modal's form element.

#### F.3 Inventory of shortcuts in scope

| Page | Shortcut | Action |
|---|---|---|
| Discover | `←` | Skip |
| Discover | `→` | Auto-apply |
| Discover | `↑` | Save |
| Discover | `↵` / tap | Review & apply |
| Discover · review & apply (cover letter) | `⌘K` | Rewrite selection |
| Discover · review & apply (cover letter) | `⌘↵` | Regenerate (preserves edits) |
| Discover · review & apply (cover letter) | `⌘C` | Copy |
| Modal (any) | `Esc` | Close |
| Modal (forms) | `⌘↵` | Save |
| Modal (forms) | `Esc` | Cancel + close |

### G · Toast notification region

Persistent `<div id="toast-region">` on `base.html`. Any state-changing endpoint can return a toast as an OOB swap:

```html
<div hx-swap-oob="afterbegin:#toast-region">
  <div class="toast toast-success" role="status" aria-live="polite">
    Bullet saved
    <button hx-on:click="this.closest('.toast').remove()">×</button>
  </div>
</div>
```

Tones: `success` (emerald), `info` (sky), `warning` (amber), `danger` (rose). Auto-dismiss after 4s via a tiny global script:

```javascript
document.addEventListener('htmx:oobAfterSwap', (e) => {
  const toast = e.target.querySelector('.toast');
  if (toast) setTimeout(() => toast.remove(), 4000);
});
```

### H · Error handling

#### H.1 HTMX-level errors

`htmx:responseError` fires on 4xx/5xx. Global handler in `base.html`:

```html
<script>
document.body.addEventListener('htmx:responseError', (e) => {
  const r = e.detail.xhr;
  const region = document.getElementById('toast-region');
  region.insertAdjacentHTML('afterbegin', `
    <div class="toast toast-danger" role="alert">
      ${r.status} — ${r.statusText}
      <button hx-on:click="this.closest('.toast').remove()">×</button>
    </div>
  `);
});
</script>
```

Specific endpoints can return a richer error fragment via the body of the 4xx response — HTMX swaps it into the target if `hx-target` is set, otherwise the global handler fires.

#### H.2 SSE errors

Each SSE stream emits an `error` event when the server detects a problem. Consumer pages handle by swapping in an error card and disabling the stream connection:

```html
<div sse-swap="error" hx-swap="outerHTML">
  <!-- error card replaces the streaming UI -->
</div>
```

#### H.3 Network offline

`htmx:sendError` fires when the request can't reach the server. Same toast pattern as § H.1, with copy `"Offline — changes will retry when reconnected"`.

For autosave specifically, queue retries in a small client-side buffer on `htmx:sendError` and replay on `online` event. (Phase 1.x optional; not blocking MVP.)

### I · Cross-cutting attributes on `base.html`

```html
<body
  hx-boost="true"               <!-- progressive enhancement on regular links -->
  hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'
  hx-ext="sse,response-targets" <!-- response-targets allows per-status-code targets -->
  data-page="{{ request.url.path }}">
```

`hx-boost="true"` makes regular `<a>` links HTMX-loaded by default (faster than full page loads). Disable per-link with `hx-boost="false"` on links that should hard-navigate (e.g. external `Open ATS · greenhouse.io`).

### J · Per-screen interaction recap (cross-reference)

For each screen, name the patterns it uses. Plan 09 (page implementation) will compose against this:

| Screen | Patterns in use |
|---|---|
| Login | B.2 full-form submit; H.1 toast errors |
| Onboarding | B.2 form (step 1 upload); C.3 SSE extraction stream (step 2); B.2 commit (step 3) |
| Overview | A.3 OOB pipeline / signal updates; C.3 SSE email signals; F (no shortcuts); G toast on actions |
| Profile | (read-only; mostly hx-boost links) |
| Profile editor | B.1 per-field autosave; D.1 bullet drag-drop; E modal for bullet editor; A.3 OOB autosave indicator |
| Bullet editor (modal) | E modal open/close; B.4 form validation; F.2 modal shortcuts |
| Discover | F.1 keyboard shortcuts; A.2 outerHTML swap on next-card |
| Discover · review & apply | B.3 inline edit (cover letter sections, screener answers); E modal (bullet editor); C.3 SSE cover letter generation; A.3 OOB on submit |
| Tracking | A.3 OOB stage change; D.2 Kanban drag-drop; C.3 SSE email signals; A.2 view-toggle full swap |
| Outreach | A.2 left-pane row click swaps right pane; B.3 inline edit on draft; A.3 OOB on send |
| Settings | C.3 SSE log tail (Deployment); B.1 per-field for some settings (LLM key); B.2 form for others (Notifications) |

## Open questions

1. **HTMX SSE vs custom EventSource** — HTMX's SSE extension covers our cases. Custom EventSource gives finer control over reconnect / event filtering. My recommendation: **HTMX extension**. Simpler, matches the rest of the stack.
2. **Sortable.js init location** — global `htmx:afterSettle` listener (proposed; auto-handles new lists from fragment swaps) or per-page init (explicit, more verbose). My recommendation: **global listener**.
3. **Toast auto-dismiss timing** — 4s default (proposed). Errors might warrant longer (until manually dismissed). My recommendation: **success/info auto-dismiss 4s; warning/danger persist until dismissed**.
4. **`hx-boost` default** — `true` everywhere (proposed; faster nav) or only on the sidebar links (more conservative). My recommendation: **true everywhere**; opt out per-link for external destinations.
5. **CSRF token rotation** — token in a `<meta>` tag set on initial render, replicated to `hx-headers` on `<body>`. Rotate on auth events only (not per-request). My recommendation: **rotate on auth events only**.
6. **Modal confirmation patterns** — destructive actions (Delete bullet, Discard profile changes) should always confirm. Use the same `<dialog>` modal pattern with a confirm/cancel inside. My recommendation: yes — small `confirm_modal.html` partial parameterized by message + confirm-action URL.
7. **Empty-state vs error-state distinction** — empty states (no jobs found yet) render via the page template's branching; error states (server unreachable) render via toasts + inline error cards. My recommendation: **separate** — empty is a happy-path UI variant, error is exceptional.
8. **Optimistic UI** — when a user clicks "Skip" on Discover, do we optimistically advance the queue before the server confirms (proposed; feels snappy) or wait for the response? My recommendation: **optimistic** for swipe / status-toggle / mark-done; **server-first** for submission + delete.

## Approval checklist

- [ ] Swap conventions (§ A) — naming targets, default modes, OOB pattern, three persistent IDs on `base.html`.
- [ ] Form patterns (§ B) — per-field autosave (B.1), full-form (B.2), inline edit (B.3), validation (B.4).
- [ ] SSE streams (§ C) — pattern, reconnect/fallback, four streams in scope.
- [ ] Drag-and-drop (§ D) — Sortable.js wrapping, two cases (bullets, Kanban).
- [ ] Modal pattern (§ E) — native `<dialog>`, three close paths, mobile bottom-sheet via responsive classes.
- [ ] Keyboard shortcuts (§ F) — page-scoped + modal-scoped, full inventory.
- [ ] Toast region (§ G) — persistent on `base.html`, OOB-swap target, four tones, auto-dismiss.
- [ ] Error handling (§ H) — `htmx:responseError`, `htmx:sendError`, SSE error events.
- [ ] `base.html` cross-cutting attrs (§ I) — `hx-boost`, `hx-headers`, `hx-ext`, `data-page`.
- [ ] Per-screen recap (§ J) — every screen's pattern usage spelled out.
- [ ] Open questions — locked in.
- [ ] After approval: graduates verbatim to `docs/design/INTERACTIONS.md`. Plan archived. Plan 09 (page implementation) consumes this directly.
