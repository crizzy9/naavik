---
Status: GRADUATED → docs/design/INTERACTIONS.md
Type: design
Authored: 2026-04-30
Last updated: 2026-04-30
Graduated: 2026-04-30
Depends on: 02-mvp-master-plan
---

> **Graduated 2026-04-30** to `docs/design/INTERACTIONS.md`. Tier-1/2/3 fixes folded in during graduation: route alignment (B.5 upload route corrected to `/api/v1/extraction/upload`, E.4 confirm modal canonicalized as query-param shape `/_modal/confirm?...`), `confirm modal` partial promoted to canonical pattern, `data-template` body attribute for parameterized-route keyboard handlers, optimistic UI rollback recipe (§ H.4), required `base.html` scripts inventory (§ I.1), DRAFT status references in § J Discover · review & apply per the post-graduation pipeline (DESIGN.md v1.3).

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

Four persistent IDs live on `base.html` so any page can swap into them:

```html
<body>
  <div id="modal-region"></div>             <!-- modals load here via hx-target="#modal-region" -->
  <div id="toast-region"></div>             <!-- OOB toast notifications -->
  <div id="sidebar-badge-jobs"></div>       <!-- Discover unswiped count; OOB updates -->
  <div id="sidebar-badge-tracking"></div>   <!-- Tracking needs-followup count; OOB updates -->
</body>
```

#### A.5 Loading state convention

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
<button hx-get="/_fragments/discover/next"
        hx-target="#discover-card"
        hx-indicator="#discover-skeleton">Next</button>

<div id="discover-skeleton" class="htmx-indicator">
  {% include "components/swipe_card_skeleton.html" %}
</div>
```

`.htmx-indicator` is HTMX's built-in class — hidden by default, visible during the request. Skeletons live as their own component partials so they match the loaded layout's dimensions exactly (no layout shift).

**Debounce conventions:**

- Autosave on blur: `hx-trigger="blur changed delay:500ms"` (covered in B.1)
- Search-as-you-type: `hx-trigger="keyup changed delay:300ms"`
- Drag-end: native to Sortable; debouncing not needed

**Forbidden:** "Loading…" text on regions that fragment-swap into themselves — use a skeleton partial. Loading text breaks layout when the eventual content has different dimensions.

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

#### B.5 File upload (Onboarding resume)

The drop zone in Onboarding step 1 is the only Phase 1 file upload. Pattern:

```html
<form
  hx-post="/api/v1/profile/upload-resume"
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

**On success:** server returns the Step 2 (Extracting) content which connects the SSE stream from § C.3.

**Drag-drop zone:** the visible drop area listens for `dragover` / `drop` events and forwards the file to the hidden `<input type="file">` via `input.files = e.dataTransfer.files; input.dispatchEvent(new Event('change'))`. Lives in the `dropzone.html` component as ~10 lines of JS; HTMX has no native drag-drop file pattern.

#### B.6 Tag chip click-to-toggle (Bullet editor modal)

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
- **After save** — server returns the standard fragment swap (e.g. updated bullet row in the parent page) **plus** an `HX-Trigger: closeModal` response header. A global listener on `base.html` closes any open `<dialog>` when the event fires.

```javascript
// base.html — global modal-close listener
document.body.addEventListener('closeModal', () => {
  document.querySelectorAll('dialog[open]').forEach(d => d.close());
});
```

**Forbidden:** `<script>` tags inside fragment responses to close modals. They execute eagerly, fight HTMX's swap lifecycle, and bypass CSP. `HX-Trigger` headers are the canonical way. If a specific endpoint needs to keep the modal open (e.g. show validation errors inline), it omits the header — modal stays mounted, form fragment shows the error.

#### E.3 Mobile bottom sheet

Same `<dialog>` element, different CSS:

- Desktop (≥ md breakpoint): centered modal, max-width 720px
- Mobile (< md): pinned to bottom, full width, drag-handle at top

Achieved via Tailwind responsive classes inside the modal partial. No separate component needed.

#### E.4 Confirmation modal (destructive actions)

Destructive actions — Delete bullet, Discard profile changes, Skip-after-detail-view, Reject offer, Disconnect Gmail — open a confirmation modal before firing. Centralized in `components/confirm_modal.html`:

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

**Trigger:**

```html
<button hx-get="/_modal/confirm?title=Delete+bullet&message=This+can%27t+be+undone&action=/api/v1/bullets/42&label=Delete&tone=danger&method=delete"
        hx-target="#modal-region"
        hx-swap="innerHTML">
  Delete
</button>
```

The server-side handler renders `confirm_modal.html` from query parameters. **Tones:**
- `danger` (rose, default for destructive — Delete, Disconnect, Withdraw)
- `warning` (amber, for "are you sure" non-destructive — Discard unsaved edits)
- `primary` (indigo, rare — "this will start auto-apply on N jobs")

**No nested confirms.** If a confirm-action triggers another destructive op, that's a flow-design problem upstream.

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

`<body data-template="/discover/:id">` carries the **template path** (parameterized), set by the page handler from the route's `name` attribute — not from `request.url.path`. This keeps shortcuts working across routes that take params (`/discover/:id`, `/tracking/:id` later, etc.). Cover-letter shortcuts gate on `data-active-tab` so they only fire when the user is editing the letter pane (not the resume pane).

**No `/generate/*` paths.** Cover letter and resume editing live inside `/discover/:id`; there is no `/generate/cover-letter` or `/generate/resume` route in MVP.

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

#### H.4 Optimistic UI rollback (Discover swipes, status toggles, Kanban drops)

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

### I · Cross-cutting attributes on `base.html`

```html
<body
  hx-boost="true"                                 <!-- progressive enhancement on regular links -->
  hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'
  hx-ext="sse,response-targets"                   <!-- response-targets: per-status-code targets -->
  data-template="{{ active_template_path }}">     <!-- e.g. "/discover/:id"; route name, not URL -->
```

`active_template_path` is set in the page handler from the FastAPI route's `name` attribute (or a small lookup). Carrying the **template path** (not `request.url.path`) keeps page-scoped keyboard handlers and any other page-aware scripts working across parameterized routes.

`hx-boost="true"` makes regular `<a>` links HTMX-loaded by default (faster than full page loads). Disable per-link with `hx-boost="false"` on links that should hard-navigate (e.g. external `Open ATS · greenhouse.io`).

### J · Per-screen interaction recap (cross-reference)

For each screen, name the patterns it uses. Plan 09 (page implementation) will compose against this:

| Screen | Patterns in use |
|---|---|
| Login | B.2 full-form submit; A.5 in-button spinner; H.1 toast errors |
| Onboarding | B.5 file upload (step 1); C.3 SSE extraction stream (step 2); B.2 commit (step 3); A.5 region skeleton during step transitions |
| Overview | A.3 OOB pipeline / signal updates; C.3 SSE email signals; H.4 optimistic "mark all done"; G toast on actions |
| Profile | (read-only; mostly hx-boost links) |
| Profile editor | B.1 per-field autosave; D.1 bullet drag-drop; E modal for bullet editor; A.3 OOB autosave indicator; E.4 confirm modal on Discard / Remove role |
| Bullet editor (modal) | E modal open/close (HX-Trigger: closeModal); B.4 form validation; B.6 tag chip toggle; F.2 modal shortcuts; E.4 confirm modal on Delete bullet |
| Discover | F.1 keyboard shortcuts (`/discover` map); A.2 outerHTML swap on next-card; H.4 optimistic swipe |
| Discover · review & apply | F.1 cover-letter shortcuts (`/discover/:id` map, gated on `data-active-tab`); B.3 inline edit (cover letter sections, screener answers); E modal (bullet editor); C.3 SSE cover letter generation; A.3 OOB on submit |
| Tracking | A.3 OOB stage change; D.2 Kanban drag-drop with H.4 optimistic move; C.3 SSE email signals; A.2 view-toggle full swap |
| Outreach | A.2 left-pane row click swaps right pane; B.3 inline edit on draft; A.3 OOB on send; E.4 confirm modal on Disconnect LinkedIn |
| Settings | C.3 SSE log tail (Deployment); B.1 per-field for some settings (LLM key); B.2 form for others (Notifications); E.4 confirm modal on Delete account / Disconnect Gmail |

## Open questions

> **Locked 2026-04-30** — all "My recommendation:" answers below are now binding decisions per user review. Implementation follows them verbatim unless a future plan revisits the call. Q6 graduates to § E.4 (confirmation modal partial); Q8 graduates to § H.4 (optimistic UI rollback).

1. **HTMX SSE vs custom EventSource** — HTMX's SSE extension covers our cases. Custom EventSource gives finer control over reconnect / event filtering. My recommendation: **HTMX extension**. Simpler, matches the rest of the stack.
2. **Sortable.js init location** — global `htmx:afterSettle` listener (proposed; auto-handles new lists from fragment swaps) or per-page init (explicit, more verbose). My recommendation: **global listener**.
3. **Toast auto-dismiss timing** — 4s default (proposed). Errors might warrant longer (until manually dismissed). My recommendation: **success/info auto-dismiss 4s; warning/danger persist until dismissed**.
4. **`hx-boost` default** — `true` everywhere (proposed; faster nav) or only on the sidebar links (more conservative). My recommendation: **true everywhere**; opt out per-link for external destinations.
5. **CSRF token rotation** — token in a `<meta>` tag set on initial render, replicated to `hx-headers` on `<body>`. Rotate on auth events only (not per-request). My recommendation: **rotate on auth events only**.
6. **Modal confirmation patterns** — destructive actions (Delete bullet, Discard profile changes) should always confirm. Use the same `<dialog>` modal pattern with a confirm/cancel inside. My recommendation: yes — small `confirm_modal.html` partial parameterized by message + confirm-action URL.
7. **Empty-state vs error-state distinction** — empty states (no jobs found yet) render via the page template's branching; error states (server unreachable) render via toasts + inline error cards. My recommendation: **separate** — empty is a happy-path UI variant, error is exceptional.
8. **Optimistic UI** — when a user clicks "Skip" on Discover, do we optimistically advance the queue before the server confirms (proposed; feels snappy) or wait for the response? My recommendation: **optimistic** for swipe / status-toggle / mark-done; **server-first** for submission + delete.

## Approval checklist

- [x] Swap conventions (§ A) — naming targets, default modes, OOB pattern, **four** persistent IDs on `base.html` (added `#sidebar-badge-tracking`), loading-state convention via `.htmx-request` / `.htmx-indicator` (A.5).
- [x] Form patterns (§ B) — per-field autosave (B.1), full-form (B.2), inline edit (B.3), validation (B.4), **file upload (B.5)**, **tag chip toggle (B.6)**.
- [x] SSE streams (§ C) — pattern, reconnect/fallback, four streams in scope.
- [x] Drag-and-drop (§ D) — Sortable.js wrapping, two cases (bullets, Kanban).
- [x] Modal pattern (§ E) — native `<dialog>`, close paths standardized on `HX-Trigger: closeModal` (no `<script>` injection), mobile bottom-sheet via responsive classes, **confirmation modal partial (E.4)**.
- [x] Keyboard shortcuts (§ F) — page-scoped + modal-scoped, full inventory; keyed by `data-template` (parameterized routes); **no `/generate/*` references**.
- [x] Toast region (§ G) — persistent on `base.html`, OOB-swap target, four tones, auto-dismiss policy.
- [x] Error handling (§ H) — `htmx:responseError`, `htmx:sendError`, SSE error events, **optimistic UI rollback (H.4)**.
- [x] `base.html` cross-cutting attrs (§ I) — `hx-boost`, `hx-headers`, `hx-ext`, `data-template` (replaces `data-page`).
- [x] Per-screen recap (§ J) — every screen's pattern usage spelled out.
- [x] Open questions (1–8) — locked in; Q6 → § E.4, Q8 → § H.4.
- [x] After approval: graduates verbatim to `docs/design/INTERACTIONS.md`. Plan archived. Plan 09 (page implementation) consumes this directly.
