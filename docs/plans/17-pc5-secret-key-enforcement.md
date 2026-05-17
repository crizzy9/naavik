---
Status: IN_PROGRESS
Type: execution
Authored: 2026-05-16
Last updated: 2026-05-16
Depends on: none
GitHub: #7
---

# 17 · PC.5 — SECRET_KEY boot-time enforcement

## Goal

Refuse to start the app when `Settings.secret_key` is the shipped default (`"change-me-in-production"`) or shorter than 32 bytes, unless `NAAVIK_DEBUG=1` (i.e. `Settings.debug is True`). Implementation is a single `model_validator(mode="after")` on `src/config.py:Settings` that raises `ValueError` — pydantic-settings wraps it as `ValidationError`. The error message names both the offending rule and the env-var escape hatch so a self-hoster can fix it without reading source. Ships four unit tests in a new `tests/test_config.py`.

## Why

ROADMAP § Pre-Phase-2 paper cuts row PC.5 (`ROADMAP.md:261`): the JWT signing key today silently accepts `"change-me-in-production"`, which means a self-hoster who skips reading `README § Configuration` ends up running production with a public, well-known secret. That secret signs JWTs in `src/services/auth.py` (verified at `tests/test_auth.py:96,107-108` — both tests use `app_settings.secret_key` directly for `pyjwt.encode/decode`); anyone with the source can forge tokens against any naavik install left at the default. Plan 10c shipped the `Settings.debug` boot-time field (`src/config.py:40-43`); PC.5 finally puts that field to work as the escape hatch for the validator we always wanted. This plan also satisfies ROADMAP row A.8 (first end-to-end `/build` of the v2 agent system, recommended target PC.5) — it ships the canonical paper-cut shape that validates manager → architect → engineer → hacker → devops → ROADMAP-mark → Issue-close → Project-advance end-to-end.

## Proposal

### A · Validator (one file, one method)

`src/config.py` currently ends:

```python
    debug: bool = Field(
        default=False,
        validation_alias=AliasChoices("NAAVIK_DEBUG", "DEBUG"),
    )


settings = Settings()
```

Add the validator AFTER the `debug` field declaration, BEFORE the `settings = Settings()` module-level singleton instantiation. Conventional placement; the validator must see both `secret_key` and `debug`, so any position after both fields is fine, but locating it directly after `debug` (the last field) groups all model-level concerns together.

Exact diff:

```python
# Plan 17 (PC.5, 2026-05-16): boot-time enforcement of SECRET_KEY rules.
# Refuse the shipped default + reject keys shorter than 32 bytes UNLESS
# Settings.debug is True (i.e. NAAVIK_DEBUG=1). 32 bytes ≈ 256 bits of
# entropy, matches OWASP guidance for HS256 JWT signing keys.
@model_validator(mode="after")
def _enforce_secret_key(self) -> "Settings":
    if self.debug:
        return self
    if self.secret_key == "change-me-in-production":
        raise ValueError(
            "SECRET_KEY is set to the shipped default 'change-me-in-production'. "
            "Set it to a random 32+ byte string before running outside of dev. "
            "To run with the default in dev, set NAAVIK_DEBUG=1 (or DEBUG=1)."
        )
    if len(self.secret_key.encode("utf-8")) < 32:
        raise ValueError(
            "SECRET_KEY is shorter than 32 bytes. Generate a strong key with "
            "`python -c 'import secrets; print(secrets.token_urlsafe(48))'` "
            "and set it via the SECRET_KEY env var. "
            "To bypass in dev, set NAAVIK_DEBUG=1 (or DEBUG=1)."
        )
    return self
```

Imports change (top of file):

```python
from pydantic import AliasChoices, Field, model_validator   # add model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
```

That's the whole production-code change. Module-level `settings = Settings()` at `src/config.py:46` continues to work in production (env var SECRET_KEY supplied → validates → instance constructed) and in dev (NAAVIK_DEBUG=1 set by `flake.nix:devEnv` → validator short-circuits at `if self.debug: return self`).

### B · Decisions (resolved inline)

#### B.1 — Validator type: `model_validator(mode="after")` vs `field_validator("secret_key")`

| Option | Capability | Robustness | Maintenance | Lock-in |
|---|---|---|---|---|
| `field_validator("secret_key")` with `info.data["debug"]` | Sees `secret_key` directly; reads `debug` via `info.data` IF pydantic validated `debug` first | **Fragile** — pydantic v2 field-validation order is the declaration order (per pydantic docs, since v2.0); changes to field order break the check. `debug` is currently declared AFTER `secret_key`, so `info.data["debug"]` would actually be UNAVAILABLE at the time `secret_key` validates → the validator would never short-circuit | Subtle — future contributors don't see the ordering coupling | Low — easy to switch to model_validator later |
| **`model_validator(mode="after")`** | Sees full `Settings` instance — `self.secret_key`, `self.debug`, anything else we add later | **Robust** — runs after ALL fields populated; insensitive to declaration order | Self-documenting — touches the model as a whole | Low — easy to remove if rules collapse |

**Recommendation: `model_validator(mode="after")`.** The `field_validator` route is actively broken given current field order (`secret_key` at line 16, `debug` at lines 40-43; pydantic-settings validates in declaration order, so `info.data["debug"]` would be empty when `secret_key` validates). Even if we reordered, the coupling is a foot-gun. `mode="after"` runs once per `Settings()` construction (cost: negligible at this model size), sees all fields, raises clean `ValueError`. The trade-off accepted: a model-level validator is slightly less precise about WHICH field failed in pydantic's auto-generated error trace, but the explicit error message we craft compensates fully.

#### B.2 — Failure mode: `ValueError` vs `RuntimeError` vs custom exception

| Option | Capability | Cost | Risk | Maintenance |
|---|---|---|---|---|
| **`ValueError`** | pydantic auto-wraps into `pydantic.ValidationError` with field-name context | None | Idiomatic; tests use `pytest.raises(ValidationError)` | Standard pydantic pattern |
| `RuntimeError` (raised manually) | Skips pydantic's wrapping; stack trace lands raw | None | Tests have to import RuntimeError; non-idiomatic for pydantic | Surprises future contributors |
| Custom exception (`SecretKeyEnforcementError`) | Most precise type | Adds one class somewhere | Overkill for a one-rule validator | New module member to maintain |

**Recommendation: `ValueError`.** It's the canonical pydantic pattern; `ValidationError` raised by `Settings()` construction makes the failure trace clean and named. The trade-off accepted: callers who want to catch JUST this rule (vs other future validators) have to inspect `.errors()`; not a concern at PC.5's scope.

#### B.3 — Threshold: 32 bytes vs 16 vs 64

| Option | Capability | Standard | Risk |
|---|---|---|---|
| 16 bytes (128 bits) | Lower bar; almost any token utility produces this | Below OWASP minimum for HS256 secrets | Brute-force feasibility nonzero against weak / leaked partial keys |
| **32 bytes (256 bits)** | Standard minimum for HS256 JWT signing per OWASP JWT cheat sheet + RFC 7518 § 3.2 ("A key of the same size as the hash output (for instance, 256 bits for HS256) MUST be used"). `secrets.token_urlsafe(32)` produces 43-char base64url string ≈ 32 bytes binary. | OWASP-aligned | Negligible |
| 64 bytes (512 bits) | Stronger margin; matches HS512 sizing | Overkill for HS256 | None — but the validator is needlessly restrictive against valid HS256 keys |

**Recommendation: 32 bytes**, encoded length (`len(self.secret_key.encode("utf-8"))`). Matches the ROADMAP row's explicit `<32 bytes` wording. Matches OWASP + RFC 7518 § 3.2 minimum for HS256 (`src/services/auth.py` uses HS256). Trade-off accepted: a user who picks a 31-byte ASCII passphrase ("supercalifragilistic-explained") gets rejected — but the error message points at `secrets.token_urlsafe(48)` which generates a strong 48-byte url-safe key in one line.

#### B.4 — Bypass gate: existing `Settings.debug` (NAAVIK_DEBUG / DEBUG) vs new env var

| Option | Capability | Cost | Maintenance |
|---|---|---|---|
| **Reuse `Settings.debug` (NAAVIK_DEBUG / DEBUG)** | Already wired: `src/config.py:40-43` + `flake.nix:devEnv` exports `NAAVIK_DEBUG=1` for `nix run .#dev`, and `pytest` reads `.env` via `SettingsConfigDict(env_file=".env")` | Zero new surface | One operational env var to remember, already documented in `README` |
| New env var (e.g. `NAAVIK_ALLOW_DEFAULT_SECRET=1`) | Single-purpose flag | New surface to document + maintain | Two env vars do similar work; sunset target for one of them later |

**Recommendation: reuse `Settings.debug`.** It already gates other dev-only behaviors (`~/.naavik/dev-credentials` write, lifespan credential echo, `/_design/components` route per `src/ui/routes/design.py:_legacy_env_gate`). Adding a third surface for "I'm in dev, skip the validator" violates the operational-surface-minimization principle that plan 10c locked in. Trade-off accepted: an operator who wants to keep `NAAVIK_DEBUG` off but ship a short test key — say, in a one-off scripted reproduction — has to either supply a valid 32-byte key or set debug. That's the right friction.

### C · Tests — new file `tests/test_config.py`

Pre-condition verified: no existing `tests/test_config*.py`. All `Settings(...)` constructions in the test suite (grep'd at planning time: `tests/test_models.py:266`, `tests/test_llm_provider.py:95,111,124,137`) refer to `models.Settings` (the SQLModel DB row), not `config.Settings`. Tests that interact with the config singleton import `from config import settings as app_settings` (e.g. `tests/test_auth.py:89`, `tests/test_seed.py:165`) and only read fields — never re-construct. **The new validator does not break any existing test.**

The new `tests/test_config.py` adds 4 cases. All four construct `Settings` directly with explicit kwargs to bypass `.env` and OS env-var inheritance:

```python
"""PC.5 — boot-time enforcement of SECRET_KEY rules.

Each test constructs Settings() with explicit kwargs to isolate from the
ambient process env (which under `nix develop` has NAAVIK_DEBUG=1 set,
and tests run with whatever .env supplies). _env_isolated() further clears
NAAVIK_DEBUG / DEBUG / SECRET_KEY so the validator sees only the kwargs.
"""

import os
from contextlib import contextmanager

import pytest
from pydantic import ValidationError

from config import Settings


@contextmanager
def _env_isolated():
    """Strip env vars that pydantic-settings would otherwise read."""
    keys = ("NAAVIK_DEBUG", "DEBUG", "SECRET_KEY")
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_default_secret_key_raises_when_not_debug():
    with _env_isolated(), pytest.raises(ValidationError) as exc:
        Settings(secret_key="change-me-in-production", debug=False)
    msg = str(exc.value)
    assert "change-me-in-production" in msg
    assert "NAAVIK_DEBUG" in msg


def test_short_secret_key_raises_when_not_debug():
    with _env_isolated(), pytest.raises(ValidationError) as exc:
        Settings(secret_key="too-short", debug=False)
    msg = str(exc.value)
    assert "32" in msg
    assert "NAAVIK_DEBUG" in msg


def test_valid_secret_key_passes_when_not_debug():
    # 48 base64url chars ≈ 36 bytes — comfortably above 32.
    strong = "x" * 48
    with _env_isolated():
        s = Settings(secret_key=strong, debug=False)
    assert s.secret_key == strong
    assert s.debug is False


def test_default_secret_key_allowed_in_debug():
    with _env_isolated():
        s = Settings(secret_key="change-me-in-production", debug=True)
    assert s.debug is True
    assert s.secret_key == "change-me-in-production"
```

The `_env_isolated()` helper is load-bearing: under `nix develop` the orchestrator-style env exports `NAAVIK_DEBUG=1`, and pytest inherits the parent shell's env. Without isolation, `Settings(debug=False, ...)` would still see `NAAVIK_DEBUG=1` from the environment and `Settings.debug` would resolve to `True` (pydantic-settings reads env vars BEFORE kwargs only when the field's `validation_alias` matches — kwargs take precedence — but the helper makes the test intent explicit and also protects against future surprises). Strip in test, restore on exit.

### D · Build sequence

1. **Read `src/config.py:1-46`** (the entire file — it's 46 lines).
2. **Edit `src/config.py`:** add `model_validator` to the pydantic import line; append the `_enforce_secret_key` method between the `debug` field and `settings = Settings()`.
3. **Create `tests/test_config.py`** with the 4 cases above.
4. **Run validation:**
   ```bash
   uv run pytest tests/test_config.py -x -v
   uv run pytest -x                  # full suite — confirm no regression
   uv run ruff check .
   uv run ruff format --check .
   ```
5. **Manual QA per `engineer-manual-qa-gate` skill § "Config validator" (lines 89-97)** — runs the two-liner reproductions from that skill against the new code. Capture stderr text into engineer's hand-back.
6. **Mark ROADMAP row PC.5 `[x]`**, add deliverable note pointing at the archived plan.

### E · Risk + mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Validator fires on app boot in production for ANY user who hasn't set SECRET_KEY env var (currently the default works silently) | HIGH (intentional) | App refuses to start with a clear error | This is the entire point of PC.5. README § Configuration already documents SECRET_KEY (`AGENTS.md:210`). The validator's error message names the env var + the dev escape hatch + the suggested `secrets.token_urlsafe` recipe inline — operator can fix in ~10 seconds without reading docs. **Engineer's manual QA must include reproducing this error against a fresh shell to confirm message readability.** |
| Existing tests construct `Settings()` (without args) and expect default behavior | LOW (verified) | Test suite breaks | Pre-verified: no `tests/**/test_config*.py` exists; all `Settings(...)` constructions in tests target `models.Settings` not `config.Settings`. The runtime singleton `config.settings = Settings()` at `src/config.py:46` runs in the dev environment under `NAAVIK_DEBUG=1` (set by `flake.nix:devEnv`) so the validator short-circuits there too. If pytest somehow runs without `NAAVIK_DEBUG` AND with a bad SECRET_KEY in the inherited env, the module import would fail at `from config import settings` — caught by the full-suite run in step 4. |
| pydantic v2's `model_validator(mode="after")` runs after every field, including `extra="ignore"` field defaults — does it run on the singleton module-import? | CERTAIN (correct) | `from config import settings` raises `ValidationError` if production env has the default | Correct behavior; matches PC.5 intent. The dev orchestrator sets `NAAVIK_DEBUG=1` so import succeeds in `nix run .#dev`. Self-hosters who haven't set SECRET_KEY get the clean error message at `nix run .#dev` / `docker compose up` startup. |
| Operator on cloud / managed deploy hits the validator and can't bypass | LOW | Deploy blocked | The validator's error message names `secrets.token_urlsafe(48)` as the fix. Cloud-tier installer (out of scope for this plan) should provision SECRET_KEY automatically; `docs/DEPLOYMENT.md` already covers the cloud path. PC.5 is a guard, not a regression. |
| `len(self.secret_key.encode("utf-8"))` is used instead of `len(self.secret_key)` — multi-byte chars affect threshold | LOW | A 32-char string of multi-byte chars (say 32 emoji) passes char-count but fails byte-count, OR vice versa | Encoded length is the security-relevant measure (entropy is bits-of-byte; HMAC operates on bytes). Documented in the comment above the validator. If users complain, future plan can ALSO allow char-count >= 32 as a passing condition — but this is the right default. |

### F · Manual QA gate

Engineer runs the manual QA per `.claude/skills/engineer-manual-qa-gate/SKILL.md § "Config validator (e.g. boot-time SECRET_KEY enforcement)"` (lines 89-97 of that skill). Three reproductions, three expected outcomes:

```bash
# 1. Default secret + no debug → fail with clear message
SECRET_KEY='change-me-in-production' NAAVIK_DEBUG= DEBUG= uv run python -c "from config import Settings; Settings()"
# Expect: ValidationError; message mentions "change-me-in-production" + "NAAVIK_DEBUG"

# 2. Short secret + no debug → fail with clear message
SECRET_KEY='short' NAAVIK_DEBUG= DEBUG= uv run python -c "from config import Settings; Settings()"
# Expect: ValidationError; message mentions "32 bytes" + "secrets.token_urlsafe" + "NAAVIK_DEBUG"

# 3. Default secret + debug → succeed
SECRET_KEY='change-me-in-production' NAAVIK_DEBUG=1 uv run python -c "from config import Settings; print(Settings().secret_key[:8])"
# Expect: prints "change-m" with no error

# 4. Valid 48-byte secret + no debug → succeed
SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" NAAVIK_DEBUG= uv run python -c "from config import Settings; print(Settings().secret_key[:8])"
# Expect: prints 8 chars of a strong key, no error
```

Also verify the orchestrator still boots:

```bash
nix run .#dev   # should start cleanly because flake.nix:devEnv exports NAAVIK_DEBUG=1
# Expect: orchestrator boots; ~/.naavik/dev-credentials echo appears as today
```

Capture the four `python -c` outcomes verbatim into the engineer hand-back's `manual QA:` block. Per `engineer-manual-qa-gate` skill § "Evidence capture for the hand-back".

### G · Files NOT modified (explicit scope guard)

- `src/cli/` — CLI sunset (ROADMAP § Phase 2 task 2.11). PC.5 is a config-layer change; the CLI doesn't enter.
- `src/services/vault.py` — vault sunset (ROADMAP § Phase 2 task 2.12). PC.5 hardens the JWT signing key (a `Settings` field), not the encrypted vault.
- `README.md` § Configuration — already documents `SECRET_KEY` at `AGENTS.md:210` (mirrored to README). No change needed; the validator's error message is self-documenting.
- `flake.nix` / `nix/devshell.nix` — `NAAVIK_DEBUG=1` already exported by `flake.nix:devEnv`. No change.
- `docs/DEPLOYMENT.md` — already covers env-var configuration. No change.
- `migrations/versions/` — no DB change.

`architect-sunset-guard` skill check: no `src/cli/` touched, no vault scope added, no new `naavik <verb>` subcommand, no `~/.naavik/<artifact>` path, no AES-GCM machinery. Clean.

## Open questions

None. The four decisions in § B are resolved with rationale; the user signs off via § Approval checklist.

## Approval checklist

- [ ] Validator type: `model_validator(mode="after")` (not `field_validator`) — per § B.1
- [ ] Error type: `ValueError` raised inside the validator; pydantic wraps as `ValidationError` — per § B.2
- [ ] Threshold: encoded length `len(self.secret_key.encode("utf-8")) < 32` (32 bytes, OWASP + RFC 7518 § 3.2 minimum for HS256) — per § B.3
- [ ] Bypass gate: reuse existing `Settings.debug` (NAAVIK_DEBUG / DEBUG); no new env var — per § B.4
- [ ] Test surface: 4 cases in new `tests/test_config.py` per § C; existing tests verified clean (no regression)
- [ ] Error message wording: per § A, includes the rule violated AND the `NAAVIK_DEBUG` escape hatch AND the `secrets.token_urlsafe(48)` recipe for the length case

## Deviations from plan (in progress — finalized at archive)

Three findings from the PR #49 hacker review (2026-05-16) were folded into this PR rather than deferred to follow-up paper cuts (PC.8/9/10 would otherwise have been filed). Each became its own commit on `feat/PC.5-secret-key-enforcement` after the rebased base SHA `b5a7f84`:

- **What:** Narrowed `Settings.debug` validation_alias from `AliasChoices("NAAVIK_DEBUG", "DEBUG")` to plain `"NAAVIK_DEBUG"`; dropped `AliasChoices` import; refined both validator error messages (no "(or DEBUG=1)" parenthetical); updated README env-var table + dev-credentials note. (Commit `1260e01`.) **Why:** Hacker finding 1 — generic `DEBUG=1` is shared by Flask/Django/many web frameworks; a self-hoster with `DEBUG=1` exported from a sibling app would silently disable the PC.5 validator. Naavik owns its env-var namespace explicitly. **Impact:** § B.4's "Bypass gate: reuse existing `Settings.debug` (NAAVIK_DEBUG / DEBUG)" now reads as "`NAAVIK_DEBUG` only." PC.8 follow-up not needed. No code outside `src/config.py` relied on the `DEBUG` alias (verified: `src/ui/routes/design.py:_legacy_env_gate` reads only `NAAVIK_DEBUG`; the only bare `DEBUG=` in operational config files is an archived plan reference at `docs/plans/archive/10-backend-impl.md:144` that doesn't bind anything).
- **What:** `docker-compose.yml:53` flipped from `${SECRET_KEY:-change-me-in-production}` to strict-require `${SECRET_KEY:?...}` so compose-render fails before the container starts; `.env.example` `SECRET_KEY=` placeholder dropped (now empty + a generation recipe comment); `.env.example` leading note flipped to declare SECRET_KEY required. (Commit `464dd0a`.) **Why:** Hacker finding 2 — the compose default was training operators to expect the dev default works in production; with the validator in place this just delays the failure to module-import time with a less-obvious error path. Fail at the earliest opportunity. **Impact:** PC.9 follow-up not needed. Self-hoster bootstrap experience now matches the validator's expectations end-to-end: copy `.env.example` to `.env`, populate `SECRET_KEY` via the recipe, `docker compose up`.
- **What:** Finding 3 was attempted (`Settings.model_config` gained `populate_by_name=True`; `tests/test_config.py` simplified to use `debug=True` / `debug=False` kwargs directly — commit `8337bb8`) but **reverted in commit `a5b78c0`** when manual QA caught that `populate_by_name=True` under pydantic-settings v2.13 also re-enables the field-name as an env-var key (case-insensitive), so bare `DEBUG=1` in the environment would still set `Settings.debug=True` — silently defeating finding 1's whole point of dropping the `DEBUG` alias. Source: `pydantic_settings.sources.providers.env.PydanticBaseEnvSettingsSource._extract_field_info` appends `(field_name, env_prefix + field_name, ...)` when `populate_by_name=True` is set, in addition to the validation_alias entry. The final state: `populate_by_name` not set; test 4 routes through `os.environ["NAAVIK_DEBUG"] = "1"` (matches the pre-finding-3 ship); `_env_isolated()` strips `("NAAVIK_DEBUG", "SECRET_KEY")` (per finding 1). **Why:** Hacker finding 3 recommended a cleaner test surface, but the production-code change required (populate_by_name=True) cannot land without also breaking finding 1's `DEBUG=1`-deny guarantee. **Impact:** Finding 3's intent (cleaner test kwargs) deferred — a future plan could ship it via case_sensitive=True (breaks every other env var), explicit `alias=` matching validation_alias on the debug field, or switching tests to `Settings.model_validate()` (bypasses the env-source pipeline). None is small enough to fold into this PR. The 4 tests remain functionally correct; only the bypass-case test routes through env-var instead of kwarg.

These three deviations are scope additions to PC.5 driven by the hacker review and folded back into the same PR per user directive — not regressions or design changes to the original plan. Archive step will promote this section to the canonical `## Deviations from plan` form after merge.
