# Naavik Interactions Spec

> **Last updated:** 2026-04-30
> **Status:** Canonical — graduated from `docs/plans/06-interactions-spec.md` (archived).
> **Scope:** Cross-cutting HTMX interaction patterns. Page templates pick from this catalogue; if a screen needs a behavior not in the catalogue, the doc gets extended (and the screen's SCREENS.md entry references the new pattern).
> **Companion docs:** `DESIGN.md` (visual contract), `docs/design/SCREENS.md` (functional contract), `docs/design/BACKEND.md` (route table; canonical URLs source-of-truth), `docs/design/DATA_MODEL.md` (entities + state axes), `docs/design/COMPONENTS.md` (component library).

---

## A · HTMX swap conventions

### A.1 Naming swap targets

Every page identifies its swap targets by stable IDs. Convention: kebab-case, prefixed with the screen slug.

```html
<main id="overview-main">
  <section id="overview-priority-actions">…</section>
  <section id="overview-email-signal">…</section>
  <section id="overview-pipeline">…</section>
</main>
```

Components emit IDs only when they're a swap target. Generic components (buttons, chips) don't.

### A.2 Default swap modes

| Pattern | `hx-swap` | When |
|---|---|---|
| Replace one chunk in place | `innerHTML` | Most fragment swaps (priority actions list refresh, pipeline strip refresh) |
| Replace the wrapper element + its contents | `outerHTML` | Per-row swaps where the row's parent shouldn't accumulate stale children (`bullet_edit_row`, `tracking_card`) |
| Append to a list | `beforeend` | Live log lines, live email signal events |
| Prepend (newest at top) | `afterbegin` | Live notifications |
| Replace the entire page | (rare) — use a real navigation instead | |

### A.3 OOB swaps

Out-of-band swaps land in the page's other regions without being the primary swap target. Used heavily for:

- **Autosave indicator** — every per-field PUT returns the field's new value AND an OOB-swap of the autosave indicator (`<div id="autosave" hx-swap-oob="outerHTML">…</div>`).
- **Pipeline strip refresh** — submitting an application from Discover · review returns the new application card AND an OOB-swap of `#overview-pipeline` (if visible).
- **Toast notifications** — any state-changing endpoint can return an OOB toast `<div id="toast-region" hx-swap-oob="afterbegin">`.
- **Sidebar count badges** — Discover unswiped count + Tracking needs-followup count update via OOB swaps from any endpoint that mutates queue or followup state.

Convention: OOB elements include `hx-swap-oob` as an HTML attribute on the root element of the partial, so the same partial can be returned both inline and OOB depending on context.

### A.4 Targets for cross-page concerns

Four persistent IDs live on `base.html` so any page can swap into them:

```html
<body>
  <div id="modal-region"></div>             <!-- modals load here via hx-target="#modal-region" -->
  <div id="toast-region"></div>             <!-- OOB toast notifications -->
  <div id="sidebar-badge-jobs"></div>       <!-- Discover unswiped count; OOB updates -->
  <div id="sidebar-badge-tracking"></div>   <!-- Tracking needs-followup count; OOB updates -->
</body>
```

### A.5 Loading state convention

While an HTMX request is in flight, HTMX automatically toggles `.htmx-request` on the triggering element and shows any `[hx-indicator]` target. Pages and components rely on this — no bespoke spinner orchestration.

**In-button spinner** (Sign in, Save bullet, Submit application):

```html
<button type="submit" class="btn-primary">
  <span class="htmx-show-loading hidden">{% include "components/spinner.html" %}</span>
  <span class="htmx-hide-loading">Sign in</span>
</button>
```

CSS class-driven swap (no JS): `.htmx-request .htmx-show-loading { display: inline-flex } .htmx-request .htmx-hide-loading { display: none }`.

**Region skeleton during fragment load:**

```html
<button hx-get="/_fragments/discover/next-card"
        hx-target="#discover-card"
        hx-indicator="#discover-skeleton">Next</button>

<div id="discover-skeleton" class="htmx-indicator">
  {% include "components/swipe_card_skeleton.html" %}
</div>
```

`.htmx-indicator` is HTMX's built-in class — hidden by default, visible during the request. Skeleton components live as their own partials per `docs/design/COMPONENTS.md` (`*_skeleton.html`) so they match the loaded layout's dimensions exactly (no layout shift).

**Debounce conventions:**

- Autosave on blur: `hx-trigger="blur changed delay:500ms"` (covered in B.1)
- Search-as-you-type: `hx-trigger="keyup changed delay:300ms"`
- Drag-end: native to Sortable; debouncing not needed

**Forbidden:** "Loading…" text on regions that fragment-swap into themselves — use a skeleton partial. Loading text breaks layout when the eventual content has different dimensions.

---

## B · Form submission patterns

### B.1 Per-field autosave on blur (Profile editor)

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

Server response: 200 with an OOB autosave indicator partial. Errors: 422 with an OOB toast. The JSON API at `/api/v1/profile/{field}` returns the OOB indicator as part of its response — no separate `/_fragments/profile/autosave` round-trip needed.

### B.2 Full-form submit (Login, Onboarding step 3)

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

### B.3 Inline edit save (Cover letter sections, screener answers)

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

### B.4 Form validation

Client-side: native HTML5 attributes (`required`, `type="email"`, `pattern`, `minlength`). HTMX `hx-validate="true"` attribute on forms enables HTMX-mediated validation messages.

Server-side: 422 response with field-level errors as a fragment (rendered above the form via OOB swap or as the primary swap target).

### B.5 File upload (Onboarding resume)

The drop zone in Onboarding step 1 is the only Phase 1 file upload. Pattern:

```html
<form
  hx-post="/api/v1/extraction/upload"
  hx-encoding="multipart/form-data"
  hx-target="#onboarding-step-content"
  hx-swap="innerHTML"
  hx-indicator="#upload-progress">
  <input type="file" name="resume" accept="application/pdf" required>
  <button type="submit" class="btn-primary">Upload</button>
  <progress id="upload-progress"
            class="htmx-indicator htmx-progress"
            value="0" max="100"></progress>
</form>
```

**Canonical route:** `POST /api/v1/extraction/upload` (per BACKEND.md § D.2). Response carries `{extraction_id, status: "queued"}`, and the page handler swaps in the Step 2 (Extracting) UI which connects to the SSE stream from § C.3.

**Progress wiring** (small global script in `base.html`):

```javascript
document.body.addEventListener('htmx:xhr:progress', (e) => {
  const bar = document.getElementById('upload-progress');
  if (bar && e.detail.lengthComputable) {
    bar.value = (e.detail.loaded / e.detail.total) * 100;
  }
});
```

**Validation:** server-side only. `accept="application/pdf"` is advisory; the server independently checks MIME + size (max 10 MB per SCREENS.md § 2). Failure → 422 with an inline error fragment swapped into the form region.

**Drag-drop zone:** the visible drop area listens for `dragover` / `drop` events and forwards the file to the hidden `<input type="file">` via `input.files = e.dataTransfer.files; input.dispatchEvent(new Event('change'))`. Lives in the `dropzone.html` component as ~10 lines of JS; HTMX has no native drag-drop file pattern.

### B.6 Tag chip click-to-toggle (Bullet editor modal)

The 9-tag picker is a row of chips; click toggles selected/unselected. The selection drives a hidden `tags[]` field that submits with the bullet form — **no per-chip HTMX request**.

```html
<fieldset class="tag-picker" data-tag-picker>
  <legend class="sr-only">Tags · {{ selected|length }} selected</legend>

  {% for tag in TAG_VOCAB %}
    <label class="tag-chip {% if tag in selected %}is-selected{% endif %}">
      <input type="checkbox" name="tags[]" value="{{ tag }}"
             {% if tag in selected %}checked{% endif %} class="sr-only">
      <span class="tag-chip__label">{{ tag }}</span>
    </label>
  {% endfor %}
</fieldset>
```

CSS handles the selected variant via `:has(input:checked)`:

```css
.tag-chip:has(input:checked) {
  @apply bg-indigo-500/15 text-indigo-200 ring-1 ring-indigo-500/40;
}
```

**No HTMX round-trip per chip.** Selection is form-local; it's submitted with the form on Save. Counter ("Tags · {N} selected") updates via a tiny `change` listener on the fieldset that recounts and rewrites the legend.

This pattern generalizes to any chip-toggle UI (e.g. Discover filter chips, Outreach contact-tag filters) — same fieldset + checkbox + `:has()` recipe.

---

## C · SSE streams

Four streams in Phase 1. All use HTMX's SSE extension (`hx-ext="sse"`). URLs match BACKEND.md § E.

### C.1 Pattern

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

### C.2 Reconnect / fallback

HTMX's SSE extension auto-reconnects. If reconnect fails 3× in a row, fall back to polling: a small JS snippet on `base.html` swaps `sse-connect` for `hx-trigger="every 5s"` on the same target.

For Phase 1, the fallback is a nice-to-have; the primary path is SSE.

### C.3 Streams in scope

| Stream | URL | Events | Consumer page |
|---|---|---|---|
| Onboarding extraction | `/api/v1/extraction/{id}/stream` | `progress`, `field`, `done`, `error` | `pages/onboarding.html` |
| Cover letter generation | `POST /api/v1/applications/{id}/cover-letter/generate` (returns SSE-friendly chunked response) | `chunk`, `done` | `pages/discover_review.html` |
| Email signals | `/api/v1/tracking/email-signals` | `signal`, `stage_change` | `pages/tracking.html`, `pages/overview.html` |
| Live log tail | `/api/v1/settings/deployment/logs` | `logline` | `pages/settings.html` (Deployment tab) |

---

## D · Drag-and-drop

Sortable.js wraps lists that need reorder. Two cases in Phase 1:

### D.1 Bullet reorder (Profile editor)

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

### D.2 Tracking Kanban card move

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

The `move` endpoint receives `{ application_id, target_status }` derived from the dragged card's new parent. Status update happens server-side, with optimistic UI per § H.4.

---

## E · Modal + bottom-sheet pattern

Native `<dialog>` element — best a11y, free Escape handling, free backdrop click (with a small JS shim).

### E.1 Modal open

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
    <!-- form, closes on save via hx-on:click on Cancel; HX-Trigger: closeModal on Save -->
  </div>
</dialog>
```

`<dialog>` with `open` attribute renders modal. CSS handles centering + scaling animation per DESIGN.md § Motion.

### E.2 Modal close

- **Escape key** — native to `<dialog>`.
- **Backdrop click — native** (plan 09a · Issue 14). The dialog's backdrop is the dialog element itself; clicks that land on the dialog (rather than its inner content) close it via a global handler in `base.js`. The legacy `.modal-backdrop` div pattern (a `<div>` inside the dialog wired to `hx-on:click`) is **deprecated** — `<dialog>` is its own stacking context, so the inner div doesn't reliably receive backdrop clicks. New modals omit the inner backdrop div entirely.

```javascript
// base.js — global native-dialog backdrop click handler
document.body.addEventListener('click', (e) => {
  if (e.target.tagName === 'DIALOG' && e.target.hasAttribute('open')) {
    e.target.close();
  }
});
```
- **Cancel button** — `hx-on:click="document.getElementById('bullet-editor-modal').close()"`.
- **After save** — server returns the standard fragment swap (e.g. updated bullet row in the parent page) **plus** an `HX-Trigger: closeModal` response header. A global listener on `base.html` closes any open `<dialog>` when the event fires.

```javascript
// base.html — global modal-close listener
document.body.addEventListener('closeModal', () => {
  document.querySelectorAll('dialog[open]').forEach(d => d.close());
});
```

**Forbidden:** `<script>` tags inside fragment responses to close modals. They execute eagerly, fight HTMX's swap lifecycle, and bypass CSP. `HX-Trigger` headers are the canonical way. If a specific endpoint needs to keep the modal open (e.g. show validation errors inline), it omits the header — modal stays mounted, form fragment shows the error.

### E.3 Mobile bottom sheet

Same `<dialog>` element, different CSS:

- Desktop (≥ md breakpoint): centered modal, max-width 720px
- Mobile (< md): pinned to bottom, full width, drag-handle at top

Achieved via Tailwind responsive classes inside the modal partial. No separate component needed.

### E.4 Confirmation modal (destructive actions)

Destructive actions — Delete bullet, Discard profile changes, Skip-after-detail-view, Reject offer, Disconnect Gmail, Discard draft application — open a confirmation modal before firing. Centralized in `components/confirm_modal.html`:

```html
<dialog id="confirm-modal" open class="modal-confirm">
  <div class="modal-backdrop" hx-on:click="this.closest('dialog').close()"></div>
  <div class="modal-content">
    <h3>{{ title }}</h3>
    <p>{{ message }}</p>
    <footer>
      <button hx-on:click="document.getElementById('confirm-modal').close()">
        Cancel
      </button>
      <button class="btn-{{ confirm_tone | default('danger') }}"
              hx-{{ confirm_method | default('post') }}="{{ confirm_action_url }}"
              hx-on:htmx:after-request="document.getElementById('confirm-modal').close()">
        {{ confirm_label }}
      </button>
    </footer>
  </div>
</dialog>
```

**Trigger** (canonical query-param shape):

```html
<button hx-get="/_modal/confirm?title=Delete+bullet&message=This+can%27t+be+undone&action=/api/v1/bullets/42&label=Delete&tone=danger&method=delete"
        hx-target="#modal-region"
        hx-swap="innerHTML">
  Delete
</button>
```

**Canonical route:** `GET /_modal/confirm?<params>` (per BACKEND.md § C). The handler renders `confirm_modal.html` from the query parameters. Path-param shape (`/_modal/confirm/{action_id}`) was rejected — query-params are more flexible (any title/message/action_url combo without pre-registering action_ids).

**Tones:**
- `danger` (rose, default for destructive — Delete, Disconnect, Withdraw)
- `warning` (amber, for "are you sure" non-destructive — Discard unsaved edits)
- `primary` (indigo, rare — "this will start auto-apply on N jobs")

**No nested confirms.** If a confirm-action triggers another destructive op, that's a flow-design problem upstream.

---

## F · Keyboard shortcut conventions

Keyboard handlers live in two places.

### F.1 Page-scoped shortcuts (Discover)

```html
<body
  hx-on:keydown="if (event.repeat) return;
                 if (event.key === 'ArrowLeft') document.getElementById('skip-btn').click();
                 if (event.key === 'ArrowRight') document.getElementById('auto-apply-btn').click();
                 if (event.key === 'ArrowUp') document.getElementById('save-btn').click();
                 if (event.key === 'Enter' || event.key === ' ') document.getElementById('review-btn').click();">
```

For pages with more than 2 shortcuts, extract into `src/ui/static/keys.js`:

```javascript
// keys.js — page-scoped keyboard handlers, keyed by template path (parameterized)
const handlers = {
  '/discover': {
    'ArrowLeft':  () => click('skip-btn'),
    'ArrowRight': () => click('auto-apply-btn'),
    'ArrowUp':    () => click('save-btn'),
    'Enter':      () => click('review-btn'),
  },
  '/discover/:id': {
    // Active only when the cover-letter tab is focused
    'meta+k':     () => activeTabIs('cover-letter') && triggerRewriteSelection(),
    'meta+Enter': () => activeTabIs('cover-letter') && triggerRegen(),
    'meta+c':     () => activeTabIs('cover-letter') && copyCoverLetterToClipboard(),
  },
};

window.addEventListener('keydown', (e) => {
  const page = document.body.dataset.template;  // template path, not URL
  const map = handlers[page];
  if (!map) return;
  const key = (e.metaKey ? 'meta+' : '') + (e.ctrlKey ? 'ctrl+' : '') + e.key;
  if (map[key]) { e.preventDefault(); map[key](); }
});

function activeTabIs(tab) {
  return document.querySelector('[data-active-tab]')?.dataset.activeTab === tab;
}
```

`<body data-template="/discover/:id">` carries the **template path** (parameterized), set by the page handler from the FastAPI route's `name` attribute — not from `request.url.path`. This keeps shortcuts working across routes that take params (`/discover/:id`, `/tracking/:id` later, etc.). Cover-letter shortcuts gate on `data-active-tab` so they only fire when the user is editing the letter pane (not the resume pane).

**No `/generate/*` paths.** Cover letter and resume editing live inside `/discover/:id`; there is no `/generate/cover-letter` or `/generate/resume` route in MVP.

### F.2 Modal-scoped shortcuts

While a modal is open, page shortcuts are suspended (the modal's focus trap prevents bubble). Modal-specific shortcuts (e.g. `Cmd+Enter` to save) are wired on the modal's form element.

### F.3 Inventory of shortcuts in scope

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

### F.4 Touch swipe conventions (Discover)

Plan 09a · Issue 3. The Discover swipe queue accepts pointer-event-based swipes on `#discover-card` (touch + pen; mouse stays on keyboard + buttons). No external library — native [Pointer Events](https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events) suffice for our single-element directional gestures.

| Direction | Threshold | Action | Stamp visual |
|---|---|---|---|
| `dx ≤ -80px` (left) | dominant-axis | click `#discover-skip-btn` | red `SKIP` stamp |
| `dx ≥ +80px` (right) | dominant-axis | click `#discover-auto-apply-btn` | emerald `APPLY` stamp |
| `dy ≤ -80px` (up) | dominant-axis | click `#discover-save-btn` | indigo `SAVE` stamp |
| Below threshold | — | snap card back, no action | — |

Stamp visuals reveal at a smaller threshold (30px) so the user gets feedback while still mid-drag. They're rendered server-side on `swipe_card.html` (3 spans, `data-stamp="left|right|up"`, opacity-0 by default) and shown via CSS scoped to `.is-swipe-{dir}` classes that `keys.js` toggles during pointermove.

Re-attached on `htmx:afterSwap` so each new card (after skip / save / auto-apply) gets the listener.

```javascript
// keys.js (excerpt) — see attachDiscoverSwipe()
card.addEventListener('pointerdown', (e) => {
  if (e.pointerType === 'mouse') return;
  // …
});
card.addEventListener('pointermove', (e) => {
  // update transform + toggle .is-swipe-{left,right,up}
});
card.addEventListener('pointerup', () => {
  // commit if abs delta ≥ 80px on dominant axis; else snap back
});
```

**Why no Hammer.js:** single-element directional gestures don't need momentum / velocity physics. Pointer events are native, no CDN, no 35KB bundle. Sortable.js (already loaded) is for list reorder — wrong primitive.

**Why pointer events not touch events:** pointer events deliver touch + pen + (optionally) mouse through one API. Touch-only events miss pen input on hybrid devices.

---

## G · Toast notification region

Persistent `<div id="toast-region">` on `base.html`. Any state-changing endpoint can return a toast as an OOB swap:

```html
<div hx-swap-oob="afterbegin:#toast-region">
  <div class="toast toast-success" role="status" aria-live="polite">
    Bullet saved
    <button hx-on:click="this.closest('.toast').remove()">×</button>
  </div>
</div>
```

Tones: `success` (emerald), `info` (sky), `warning` (amber), `danger` (rose).

**Auto-dismiss policy:** `success` and `info` auto-dismiss after 4s. `warning` and `danger` persist until user dismisses (errors warrant attention; auto-fading them risks missed alerts).

```javascript
document.addEventListener('htmx:oobAfterSwap', (e) => {
  const toast = e.target.querySelector('.toast');
  if (toast && (toast.classList.contains('toast-success') || toast.classList.contains('toast-info'))) {
    setTimeout(() => toast.remove(), 4000);
  }
});
```

Toast partial lives at `components/toast.html`.

---

## H · Error handling

### H.1 HTMX-level errors

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

### H.2 SSE errors

Each SSE stream emits an `error` event when the server detects a problem. Consumer pages handle by swapping in an error card and disabling the stream connection:

```html
<div sse-swap="error" hx-swap="outerHTML">
  <!-- error card replaces the streaming UI -->
</div>
```

### H.3 Network offline

`htmx:sendError` fires when the request can't reach the server. Same toast pattern as § H.1, with copy `"Offline — changes will retry when reconnected"`.

For autosave specifically, queue retries in a small client-side buffer on `htmx:sendError` and replay on `online` event. (Phase 1.x optional; not blocking MVP.)

### H.4 Optimistic UI rollback (Discover swipes, status toggles, Kanban drops)

For actions where perceived latency matters and failure rate is low, pre-update the DOM and roll back on error. **Optimistic if reversible and frequent; server-first if irreversible or expensive.**

**Pattern:** stash the pre-action DOM in a `data-rollback` attribute, apply the optimistic change, restore on `htmx:responseError` / `htmx:sendError`.

```javascript
// base.html — global optimistic-rollback handler
['htmx:responseError', 'htmx:sendError'].forEach(evt => {
  document.body.addEventListener(evt, (e) => {
    const el = e.detail.target;
    const stash = el?.dataset.rollback;
    if (stash) {
      el.outerHTML = decodeURIComponent(stash);
      showToast('danger', "Couldn't save — restored. Try again?");
    }
  });
});
```

**Per-action use:**

```html
<button
  hx-post="/api/v1/discover/{{ job.id }}/skip"
  hx-target="#discover-card"
  hx-swap="outerHTML"
  hx-on:htmx:before-request="
    const card = document.getElementById('discover-card');
    card.dataset.rollback = encodeURIComponent(card.outerHTML);
    card.classList.add('is-skipping');  // optimistic: animate out
  ">
  ✕ Skip
</button>
```

Server-success returns the next-card fragment that replaces the optimistically-marked card. Server-error triggers the global rollback handler, which restores the pre-skip DOM and shows a toast.

**Optimistic in scope:**

| Action | Why it qualifies |
|---|---|
| Discover swipe (skip / save / queue auto-apply) | Reversible (swipe back), frequent, snappy is the whole point |
| Tracking Kanban card move | Reversible (drag back), failure is rare |
| "Mark all done" priority actions (Overview) | Reversible, frequent |
| Notification dismissal | Reversible (re-fetchable) |

**Server-first (NOT optimistic):**

| Action | Why |
|---|---|
| Application submission | Irreversible; user expects the wait |
| Delete bullet / contact / application | Destructive; needs server confirmation before UI hides it |
| Generate documents (resume / cover letter) | Expensive; wait state is the UI |
| LLM provider switch / API key save | Validation must complete server-side first |
| Discard DRAFT application | Destructive (loses the generated bundle); confirm modal first |

---

## I · Cross-cutting attributes on `base.html`

```html
<body
  hx-boost="true"                                 <!-- progressive enhancement on regular links -->
  hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'
  hx-ext="sse,response-targets"                   <!-- response-targets: per-status-code targets -->
  data-template="{{ active_template_path }}">     <!-- e.g. "/discover/:id"; route name, not URL -->
```

`active_template_path` is set in the page handler from the FastAPI route's `name` attribute (or a small lookup). Carrying the **template path** (not `request.url.path`) keeps page-scoped keyboard handlers and any other page-aware scripts working across parameterized routes.

`hx-boost="true"` makes regular `<a>` links HTMX-loaded by default (faster than full page loads). Disable per-link with `hx-boost="false"` on links that should hard-navigate (e.g. external `Open ATS · greenhouse.io`).

CSRF token lives in a `<meta name="csrf-token" content="{{ csrf_token }}">` tag; rotated on auth events only (login / logout / password change), not per-request. The Jinja template injects it from the auth dependency.

### I.1 Required `base.html` scripts (Phase 1)

These global scripts attach the cross-cutting handlers documented above. They live inline in `base.html` for Phase 1 (single template inheritance graph; the inline-vs-external trade-off favors inline at this size).

| Script | Section | Purpose |
|---|---|---|
| Lucide CDN + post-swap reinit | DESIGN.md § Iconography | `lucide.createIcons()` after `htmx:afterSwap` so SVG icons render in fragment-swapped content |
| Sortable.js auto-init | § D | Initializes `[data-sortable="true"]` lists after `htmx:afterSettle` |
| Modal-close listener | § E.2 | Closes any open `<dialog>` on `closeModal` event |
| Toast auto-dismiss | § G | Removes success/info toasts after 4s |
| Optimistic rollback | § H.4 | Restores pre-action DOM on `htmx:responseError` / `htmx:sendError` |
| Upload progress | § B.5 | Updates `<progress>` element on `htmx:xhr:progress` |
| Page-scoped keys | § F.1 | Loads `keys.js`; routes keystrokes via `data-template` lookup |

`base.html` is the only place these wire up — components and page templates never re-attach them. This keeps the global handler graph predictable and the per-component code free of script tags.

---

## J · Per-screen interaction recap (cross-reference)

For each screen, name the patterns it uses. Plan 09 (page implementation) composes against this.

| Screen | Patterns in use |
|---|---|
| Login | B.2 full-form submit; A.5 in-button spinner; H.1 toast errors |
| Onboarding | B.5 file upload (step 1); C.3 SSE extraction stream (step 2); B.2 commit (step 3); A.5 region skeleton during step transitions |
| Overview | A.3 OOB pipeline / signal updates; C.3 SSE email signals; H.4 optimistic "mark all done"; G toast on actions |
| Profile | (read-only; mostly hx-boost links) |
| Profile editor | B.1 per-field autosave; D.1 bullet drag-drop; E modal for bullet editor; A.3 OOB autosave indicator; E.4 confirm modal on Discard / Remove role |
| Bullet editor (modal) | E modal open/close (HX-Trigger: closeModal); B.4 form validation; B.6 tag chip toggle; F.2 modal shortcuts; E.4 confirm modal on Delete bullet |
| Discover | F.1 keyboard shortcuts (`/discover` map); A.2 outerHTML swap on next-card; H.4 optimistic swipe |
| Discover · review & apply | F.1 cover-letter shortcuts (`/discover/:id` map, gated on `data-active-tab`); B.3 inline edit (cover letter sections, screener answers); E modal (bullet editor); C.3 SSE cover letter generation; A.3 OOB on submit; E.4 confirm modal on Discard draft |
| Tracking | A.3 OOB stage change; D.2 Kanban drag-drop with H.4 optimistic move; C.3 SSE email signals; A.2 view-toggle full swap |
| Outreach | A.2 left-pane row click swaps right pane; B.3 inline edit on draft; A.3 OOB on send; E.4 confirm modal on Disconnect LinkedIn |
| Settings | C.3 SSE log tail (Deployment); B.1 per-field for some settings (LLM key); B.2 form for others (Notifications); E.4 confirm modal on Delete account / Disconnect Gmail |
