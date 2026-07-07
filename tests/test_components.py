"""Per-component render tests parametrized over the 85-component catalog.

Each component is rendered via Jinja `Environment.get_template(...).render()` with
example kwargs that mirror the example invocations in `docs/design/COMPONENTS.md`.
This catches:
- missing files (TemplateNotFound)
- syntax errors
- token compliance violations (e.g. sparkle on tag chips, % on score circles)
"""

from __future__ import annotations

import re

import pytest
from jinja2 import ChainableUndefined, Environment, FileSystemLoader

from ui.templates_setup import APPLICATION_STATUS_LABELS, STATUS_DOT_COLORS, TAG_VOCAB

pytestmark = pytest.mark.uses_sample_data_shims

_TEMPLATES_DIR = "src/ui/templates"


@pytest.fixture(scope="module")
def env() -> Environment:
    # Use permissive ChainableUndefined to match runtime behavior — components rely
    # on `var | default(none)` to fall back, and `x or y` short-circuits when `x`
    # is undefined under the default Undefined (StrictUndefined would raise).
    e = Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=True,
        undefined=ChainableUndefined,
    )
    e.globals["STATUS_DOT_COLORS"] = STATUS_DOT_COLORS
    e.globals["STATUS_LABELS"] = APPLICATION_STATUS_LABELS
    e.globals["TAG_VOCAB"] = TAG_VOCAB
    return e


# ------------------------------------------------------------------ #
# Sample data + per-component example kwargs.                        #
# ------------------------------------------------------------------ #

_PROFILE = {
    "name": "Shyam Padia",
    "initials": "SP",
    "title": "Senior Software Engineer",
    "company": "Intuit",
    "location": "San Francisco, CA",
    "open_to_opportunities": True,
    "visa_label": "H1B",
    "contacts": [{"kind": "mail", "value": "shyam@example.com", "href": None}],
    "work_authorization": "H1B",
    "visa_sponsorship_needed": "Yes",
    "willing_to_relocate": "Yes",
    "notice_period_days": 14,
    "salary_expectation_usd": 245000,
    "earliest_start": "2026-06-01",
    "veteran_status": "",
    "disability_status": "",
    "race_ethnicity": "",
    "gender_identity": "Prefer not to say",
}

_BULLET = {
    "id": 1,
    "text": "Built Intuit's ML personalization platform; +23% homepage CTR / $4.2M revenue.",
    "tags": ["ai-ml", "platform"],
    "selection_override": None,
}

_BULLETS = [_BULLET]

_EXPERIENCE = {
    "company": "Intuit",
    "team": "Personalization",
    "title": "Senior Software Engineer",
    "location": "San Francisco, CA",
    "dates": "Sep 2019 — Present",
    "duration": "5y 8m",
    "initial": "I",
    "color": "bg-emerald-600",
}

_JOB = {
    "id": 42,
    "company": "Stripe",
    "company_initial": "S",
    "company_color": "bg-purple-600",
    "gradient_from": "from-indigo-600",
    "gradient_to": "to-purple-600",
    "role": "Senior ML Engineer",
    "team": "Atlas",
    "score": 86,
    "location": "San Francisco",
    "salary_range": "$240-290k",
    "work_mode": "Hybrid",
    "team_size": "team of 12",
    "visa_friendly": True,
    "posted_relative": "2h ago",
    "jd_bullets": ["5+ years building ranking", "Strong systems chops"],
    "warm_intro_label": "Priya",
    "tags": ["ai-ml", "platform"],
    "match_breakdown": {"ai-ml": 0.95, "platform": 0.88},
    "match_overall": 0.86,
    "salary_min": 240,
    "salary_max": 290,
    "equity_pct": "0.05",
    "jd_url": "https://example.com/jobs/42",
}

_APPLICATION = {
    "id": 99,
    "company": "Stripe",
    "company_initial": "S",
    "company_color": "bg-purple-600",
    "role": "Senior ML Engineer",
    "team": "Atlas",
    "score": 86,
    "salary_range": "$240-290k",
    "status": "APPLIED",
    "status_label": "applied",
    "context_chip": "screen Apr 30",
    "context_chip_tone": "indigo",
    "sub_state_pills": [],
    "outreach_engagement": "awaiting_reply",
    "contacts_count": 3,
    "last_touch": "sent 5d ago",
}

_CONTACT = {
    "name": "Priya R.",
    "initial": "PR",
    "color": "bg-purple-600",
    "title": "Sr ML Engineer",
    "team": "Atlas",
    "company": "Stripe",
    "school": "CMU",
    "mutuals_count": 14,
    "degree": "1st",
    "linkedin_degree": "1st",
    "last_activity": "replied 3d ago",
}

_SIGNAL = {
    "sender": "Priya · Linear",
    "sender_initial": "L",
    "sender_color": "bg-violet-600",
    "subject": "Re: Founding Engineer",
    "classification": "INTERVIEW",
    "classification_label": "Interviewing",
    "score": 88,
    "relative_time": "14m",
}


# Each tuple: (template_name, kwargs)
_CASES: list[tuple[str, dict]] = [
    # ---- Shell ----
    ("shell/auth_shell.html", {}),  # extends base; render only checks parse
    (
        "shell/sidebar.html",
        {
            "active": "overview",
            "user_name": "Shyam Padia",
            "user_initials": "SP",
            "deployment_mode": "self-hosted",
            "unswiped_count": 47,
            "followup_count": 12,
        },
    ),
    ("common/version_pill.html", {"version": "0.4.2", "mode": "self-hosted"}),
    ("shell/api_status_dot.html", {"online": True}),
    ("settings/deployment_badge.html", {"mode": "self-hosted"}),
    # ---- Atomics ----
    ("common/button.html", {"variant": "primary", "label": "Save"}),
    ("common/input.html", {"name": "email", "type": "email", "placeholder": "you@example.com"}),
    ("common/card.html", {"title": "Recent activity", "sub": "last 24h", "body": "<p>hi</p>"}),
    ("common/status_dot.html", {"status": "APPLIED"}),
    ("common/status_badge.html", {"status": "ONSITE_LOOP"}),
    ("common/score_circle.html", {"score": 86, "size": "default"}),
    ("common/ai_badge.html", {"qualifier": "enthusiastic"}),
    ("common/field_label.html", {"label": "Tags", "for_id": "tags", "hint": "3 selected"}),
    (
        "common/info_card.html",
        {"tone": "info", "icon": "key", "title": "SSO coming soon", "body": "<p>foo</p>"},
    ),
    ("common/spinner.html", {"size": "sm"}),
    ("common/toast.html", {"tone": "success", "message": "Bullet saved"}),
    (
        "common/empty_state.html",
        {
            "icon": "search",
            "line": "No new matches today.",
            "cta_label": "Find jobs",
            "cta_url": "/discover",
        },
    ),
    ("common/avatar.html", {"kind": "user", "text": "SP", "size": "sm", "shape": "circle"}),
    # ---- Forms ----
    (
        "common/editor_field.html",
        {"label": "FULL NAME", "name": "full_name", "value": "Shyam Padia"},
    ),
    (
        "profile/editor_card.html",
        {"title": "Identity", "subtitle": "Required", "body": "<div>fields</div>"},
    ),
    ("profile/autosave_indicator.html", {"state": "saved", "relative_time": "12s ago"}),
    (
        "common/modal.html",
        {
            "id": "demo-modal",
            "title": "Edit bullet",
            "subtitle": "· Intuit",
            "body": "<p>body</p>",
            "footer": '<button type="button">Save</button>',
            "size": "lg",
        },
    ),
    (
        "common/confirm_modal.html",
        {
            "title": "Delete bullet",
            "message": "Cannot be undone",
            "confirm_action_url": "/api/v1/bullets/42",
            "confirm_label": "Delete",
            "confirm_tone": "danger",
            "confirm_method": "delete",
            "cancel_label": "Cancel",
        },
    ),
    # ---- Onboarding ----
    ("common/step_indicator.html", {"current_step": 2}),
    ("common/dropzone.html", {"upload_url": "/api/v1/extraction/upload"}),
    (
        "profile/extraction_checklist.html",
        {
            "items": [
                {"label": "Reading PDF", "status": "done", "count": "4 pages"},
                {"label": "Parsing roles", "status": "active", "count": "2 of 4"},
                {"label": "Categorizing", "status": "queued", "count": "queued"},
            ]
        },
    ),
    (
        "profile/extracted_field_row.html",
        {
            "id": "row-name",
            "label": "NAME",
            "value": "Shyam Padia",
            "confidence": 0.99,
            "state": "extracted",
        },
    ),
    ("common/progress_bar.html", {"value": 0.42, "gradient": True}),
    # ---- Profile / Bullet ----
    ("profile/profile_hero.html", {"profile": _PROFILE, "editable": True}),
    (
        "profile/contact_chip.html",
        {"kind": "mail", "value": "shyam@example.com", "href": "mailto:shyam@example.com"},
    ),
    (
        "profile/experience_card.html",
        {"experience": _EXPERIENCE, "bullets": _BULLETS, "expanded": False},
    ),
    ("profile/bullet_row.html", {"bullet": _BULLET}),
    (
        "common/section_anchor_nav.html",
        {
            "anchors": [
                {"id": "summary", "label": "Summary"},
                {"id": "experience", "label": "Experience", "count": 4},
            ],
            "active_id": "experience",
        },
    ),
    (
        "profile/application_readiness_card.html",
        {
            "missing_count": 4,
            "fields": [
                {
                    "name": "work_authorization",
                    "label": "Work auth",
                    "value": "H1B",
                    "filled": True,
                },
                {"name": "veteran_status", "label": "Veteran", "value": "", "filled": False},
            ],
        },
    ),
    ("profile/application_qs_form.html", {"profile": _PROFILE, "region": "US"}),
    ("profile/bullet_edit_row.html", {"bullet": _BULLET}),
    ("common/tag_picker.html", {"selected": ["ai-ml", "platform"]}),
    ("profile/selection_override.html", {"current": "always_include"}),
    ("profile/bullet_textarea.html", {"value": _BULLET["text"]}),
    # ---- Overview ----
    (
        "common/kpi_card.html",
        {
            "label": "RESPONSE RATE · 90D",
            "value": "11.3%",
            "delta": "+2.1%",
            "delta_trend": "up",
            "sub": "3× market avg",
        },
    ),
    (
        "overview/priority_action_row.html",
        {
            "index": 1,
            "kind": "offer",
            "title": "Respond to Figma offer",
            "subtitle": "$290k base · verbal Apr 28",
            "urgency": "today",
            "urgency_label": "TODAY",
            "cta_label": "Open offer",
            "cta_url": "/tracking/123",
        },
    ),
    ("overview/email_signal_row.html", {"signal": _SIGNAL}),
    (
        "overview/pipeline_strip.html",
        {
            "counts": {
                "APPLIED": 14,
                "RECRUITER_SCREEN": 5,
                "ONSITE_LOOP": 3,
                "OFFER": 1,
                "CLOSED": 6,
            }
        },
    ),
    # ---- Discover ----
    ("discover/swipe_card.html", {"job": _JOB, "dimmed": False, "swiping_dir": None}),
    (
        "discover/match_breakdown.html",
        {
            "breakdown": {"ai-ml": 0.95, "platform": 0.88, "leadership": 0.82},
            "overall": 0.86,
        },
    ),
    (
        "discover/score_card.html",
        {
            "score": 86,
            "match_breakdown": {
                "per_dimension": {"ai-ml": 0.95, "platform": 0.88, "leadership": 0.82},
                "strengths": ["Strong ML platform background", "Personalization signal"],
                "gaps": ["No explicit foundation-model experience"],
                "visa_concern": False,
                "visa_note": None,
                "layers_run": ["layer-1", "layer-2", "layer-3"],
                "layer_4_provider": "anthropic",
                "layer_4_model": "claude-opus-4-7",
                "judge_skipped": False,
                "scored_at": "2026-05-20T03:30:00Z",
            },
            "expanded": True,
        },
    ),
    ("discover/discover_action_bar.html", {"job_id": 42}),
    (
        "discover/swipe_action_btn.html",
        {
            "icon": "x",
            "label": "Skip",
            "tone": "skip",
            "key_hint": "←",
            "action_url": "/api/v1/discover/42/skip",
        },
    ),
    (
        "discover/discover_stats_strip.html",
        {
            "stats": {
                "applied": 4,
                "auto": 2,
                "manual": 1,
                "saved": 8,
                "skipped": 12,
                "scanned": 247,
            }
        },
    ),
    (
        "discover/up_next_card.html",
        {
            "job": {
                "id": 51,
                "company": "Anthropic",
                "company_initial": "A",
                "company_color": "bg-orange-500",
                "role": "Founding ML Engineer",
                "salary_range": "$300-380k",
                "score": 91,
            },
            "state": "default",
        },
    ),
    (
        "common/tip_card.html",
        {"title": "Tip", "body": "Tap to expand a job before applying."},
    ),
    ("common/keyboard_hints.html", {}),
    # ---- Discover · review ----
    ("discover/apply_topbar.html", {"job": _JOB, "application": _APPLICATION}),
    (
        "discover/warm_intro_card.html",
        {"contact": _CONTACT, "referrals_this_year": 4},
    ),
    (
        "discover/tailored_bullet_row.html",
        {
            "bullet": _BULLET,
            "selected": True,
            "trimmed_line": "Trimmed line",
            "chips": ["jd", "scale"],
        },
    ),
    (
        "discover/cover_letter_section.html",
        {
            "application_id": 99,
            "section": "intro",
            "label": "INTRO",
            "text": "Hello.",
            "mode": "view",
        },
    ),
    (
        "discover/screener_question_card.html",
        {
            "answer": {
                "id": 1,
                "question": "Why this role?",
                "body": "Because it's a good fit.",
                "source": "drafted",
                "reviewed_at": None,
            }
        },
    ),
    (
        "discover/apply_action_bar.html",
        {
            "application": {"id": 99},
            "screener_count": 3,
            "unreviewed_count": 0,
            "cost_estimate_usd": 0.12,
            "board_label": "greenhouse.io",
        },
    ),
    # ---- Tracking ----
    ("common/view_toggle.html", {"current_view": "board"}),
    (
        "outreach/provider_chip.html",
        {"provider": "gmail", "icon": "mail", "connected": True, "sub": "synced 2m ago"},
    ),
    (
        "tracking/integration_card.html",
        {
            "name": "Gmail",
            "icon": "mail",
            "state": "connected",
            "account": "shyam@gmail.com",
            "disconnect_url": "/api/v1/integrations/gmail/disconnect",
        },
    ),
    (
        "tracking/followup_banner.html",
        {
            "count": 2,
            "items": [
                {
                    "contact": {"name": "Priya", "initial": "P", "color": "bg-violet-600"},
                    "application": {"company": "Linear"},
                    "last_touch_label": "sent 3d ago",
                    "action_label": "Draft reply",
                    "action_url": "/outreach",
                }
            ],
        },
    ),
    (
        "tracking/stage_column.html",
        {"status": "APPLIED", "cards": [_APPLICATION], "column_id": "col-applied"},
    ),
    ("tracking/tracking_card.html", {"application": _APPLICATION}),
    (
        "tracking/tracking_list_row.html",
        {"application": dict(_APPLICATION, last_activity="2d ago", source="manual")},
    ),
    (
        "tracking/tracking_board.html",
        {
            "columns": [{"status": "APPLIED", "cards": [_APPLICATION]}],
            "show_closed": False,
            "closed_count": 6,
        },
    ),
    # ---- Outreach ----
    ("outreach/outreach_app_row.html", {"application": _APPLICATION, "selected": True}),
    (
        "outreach/recommended_move_card.html",
        {
            "application": _APPLICATION,
            "contact": _CONTACT,
            "tone_recommendation": "warm + direct",
            "last_touch_relative": "5d ago",
            "context": "they asked you back",
            "draft_body": "Hey Priya — quick nudge.",
        },
    ),
    (
        "outreach/outreach_message_card.html",
        {
            "message": {
                "id": 1,
                "body": "Hey Priya",
                "status": "DRAFT",
                "ai_generated": True,
                "contact_name": "Priya",
            },
            "editable": True,
        },
    ),
    ("outreach/contact_card.html", {"contact": _CONTACT, "state": "referred_you"}),
    (
        "outreach/linkedin_status_chip.html",
        {"connected": True, "handle": "shyampadia", "dms_today": 7, "connections": 487},
    ),
    # Plan 78 § D.6 (0.4.0.15) — visa_status_chip catalogue entry.
    (
        "discover/visa_status_chip.html",
        {"restriction": "sponsorship_available"},
    ),
    (
        "outreach/outreach_timeline.html",
        {
            "events": [
                {
                    "kind": "linkedin_dm",
                    "description": "You sent a DM",
                    "relative_time": "5d ago",
                    "payload_preview": "Hi",
                }
            ]
        },
    ),
    # ---- Settings ----
    ("settings/settings_tabs.html", {"current_tab": "llm-provider"}),
    (
        "settings/provider_card.html",
        {
            "provider": {
                "id": "anthropic",
                "name": "Anthropic Claude",
                "kind": "CLOUD",
                "description": "Recommended",
                "model_default": "claude-3.5-sonnet",
            },
            "selected": True,
        },
    ),
    ("settings/cost_card.html", {"label": "THIS MONTH", "value": "$3.42", "sub": "≈412k tokens"}),
    (
        "settings/deployment_status_card.html",
        {
            "mode": "self-hosted",
            "status": "active",
            "version": "0.4.2",
            "meta": "docker-compose · uptime 14d 6h",
        },
    ),
    (
        "settings/log_tail.html",
        {
            "log_path": "~/.naavik/logs · live tail",
            "lines": [{"timestamp": "14:02:41", "level": "INFO", "message": "ok"}],
            "streaming": True,
        },
    ),
    (
        "settings/on_disk_card.html",
        {
            "paths": [
                {"label": "DATA DIR", "path": "~/.naavik/data", "sub": "12 MB", "icon": "database"}
            ]
        },
    ),
    (
        "settings/connection_status_card.html",
        {"ok": True, "latency_ms": 412, "model": "claude-3.5-sonnet", "provider": "Anthropic"},
    ),
    # ---- Skeletons ----
    ("discover/swipe_card_skeleton.html", {}),
    ("tracking/tracking_card_skeleton.html", {}),
    ("overview/priority_action_row_skeleton.html", {}),
    ("overview/email_signal_row_skeleton.html", {}),
    ("profile/bullet_edit_row_skeleton.html", {}),
]

assert len(_CASES) == 85, f"Expected 85 components, got {len(_CASES)}"


@pytest.mark.parametrize(
    "template_name,kwargs", _CASES, ids=lambda x: x if isinstance(x, str) else ""
)
def test_component_renders(env: Environment, template_name: str, kwargs: dict) -> None:
    """Every component renders without TemplateNotFound / UndefinedError."""
    tpl = env.get_template(f"components/{template_name}")
    out = tpl.render(**kwargs)
    assert out, f"{template_name} rendered empty"


# ---------------------------------------------------------------- #
# Token-compliance assertions on specific components.              #
# ---------------------------------------------------------------- #


def test_score_circle_no_percent_sign(env: Environment) -> None:
    out = env.get_template("components/common/score_circle.html").render(score=86, size="default")
    # Score number rendered as "86", not "86%".
    assert ">86</span>" in out
    assert "86%" not in out
    assert (
        "match" not in out.lower()
        or "match" not in re.sub(r"aria-label=\"score \d+\"", "", out).lower()
    )


def test_score_circle_uses_macro_via_macros_file(env: Environment) -> None:
    # Macro rendering — calls into _macros.html score_circle().
    macro_module = env.get_template("components/common/_macros.html").module
    out = macro_module.score_circle(score=92, size="hero")
    assert ">92</span>" in out
    assert "%" not in out
    assert "stroke-emerald-400" in out  # threshold ≥ 80


def test_status_dot_colors_complete() -> None:
    # 6 pipeline keys (DRAFT + 5 visible).
    pipeline_keys = {"DRAFT", "APPLIED", "RECRUITER_SCREEN", "ONSITE_LOOP", "OFFER", "CLOSED"}
    for k in pipeline_keys:
        assert k in STATUS_DOT_COLORS, f"missing {k} in STATUS_DOT_COLORS"


def test_sidebar_uses_inbox_not_kanban(env: Environment) -> None:
    out = env.get_template("components/shell/sidebar.html").render(
        active="tracking",
        user_name="Shyam",
        user_initials="SP",
        deployment_mode="self-hosted",
        unswiped_count=0,
        followup_count=0,
    )
    assert 'data-lucide="inbox"' in out
    assert "kanban-square" not in out


def test_sidebar_width_is_w64() -> None:
    """Direct file inspection to enforce the literal `w-64` token."""
    with open("src/ui/templates/components/shell/sidebar.html") as f:
        contents = f.read()
    assert "w-64" in contents
    assert "w-60" not in contents


def test_no_dark_prefixes_in_components() -> None:
    """No light-mode `dark:` Tailwind prefixes anywhere in components."""
    import glob

    for path in glob.glob("src/ui/templates/components/**/*.html", recursive=True):
        with open(path) as f:
            contents = f.read()
        # The `dark:` prefix must not appear inside any class attribute.
        bad = re.findall(r'class="[^"]*\bdark:', contents)
        assert not bad, f"`dark:` prefix found in {path}: {bad[:2]}"
