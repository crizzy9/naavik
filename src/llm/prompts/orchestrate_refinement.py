"""orchestrate_refinement — plan 67 (0.3.4) § C.4.

Tool-loop orchestrator prompt + tool definitions. Claude calls 5 tools
(ats_parse_test / detector_test / recruiter_skim_score /
keyword_coverage_check / defensibility_check), reads their results, and
decides whether to ship the bundle or refine a specific stage. Iteration
cap N=3 per OQ-3.
"""

from __future__ import annotations

ORCHESTRATOR_PROMPT = """You are orchestrating PREMIUM-tier refinement
of a resume + cover letter bundle. You have 5 tools available; use them
to verify the bundle meets PREMIUM quality bars.

Quality bars to hit before shipping:
- ATS parse fidelity score >= 0.85
- AI-detector confidence <= 0.30 on resume text and cover letter
- Recruiter 6-second skim score >= 7 / 10
- Keyword coverage on top-30% >= 0.75
- Every selected bullet has profile provenance (defensibility check)

Workflow:
1. Call tools to gather signal (ats_parse_test, detector_test,
   recruiter_skim_score, keyword_coverage_check, defensibility_check).
2. If all quality bars are met, emit a final text message starting with
   "ship" (no further tool calls).
3. If a bar is missed, you may either:
   a. Run additional tool calls to gather more signal, OR
   b. Emit a final text message starting with "ship_with_caveats" listing
      the unresolved concerns (no further tool calls).
4. You have a hard cap of {max_iters} iterations. After the cap, return
   "ship_with_caveats".

Bundle context:
- Resume text (first 2000 chars): {resume_excerpt}
- Cover letter text (first 1000 chars): {cover_excerpt}
- Job role: {role}
- Required skills: {skills}
- Selected bullet ids: {selected_ids}

Begin orchestration. Call tools as needed.
"""


def build_orchestrator_prompt(
    *,
    resume_excerpt: str,
    cover_excerpt: str,
    role: str,
    skills: list[str],
    selected_ids: list[int],
    max_iters: int,
) -> str:
    return ORCHESTRATOR_PROMPT.format(
        resume_excerpt=(resume_excerpt or "")[:2000],
        cover_excerpt=(cover_excerpt or "")[:1000],
        role=role,
        skills=", ".join(skills),
        selected_ids=", ".join(str(i) for i in selected_ids),
        max_iters=max_iters,
    )


TOOL_DEFINITIONS = [
    {
        "name": "ats_parse_test",
        "description": (
            "Run the rendered resume PDF through pdfplumber + extracts 8 "
            "canonical fields. Returns a parse-fidelity score [0,1] + tier "
            "+ fields missing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "detector_test",
        "description": (
            "Run Claude-as-detector + (when configured) Originality.ai on a "
            "text snippet. Returns final ai_confidence [0,1] + iterations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to score"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "recruiter_skim_score",
        "description": (
            "Simulate a recruiter's 6-second skim. Returns a 0-10 score + top "
            "signals captured + missing signals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to skim"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "keyword_coverage_check",
        "description": (
            "Score the top-30% of the resume against the JD must-haves. "
            "Returns coverage score + found + missing keywords."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "defensibility_check",
        "description": (
            "Verify every selected bullet has provenance in the candidate's "
            "profile. Returns bool + dropped-bullet count."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]
