"""classify_email — classification + entity extraction for inbox tracking.

Per BACKEND.md § H.1, § M.3. Extended 2026-07: the classifier also extracts
the employer (company), role, and interview stage so emails can be mapped to
applications (or surfaced as untracked interview processes) even when the
thread carries no application link.
"""

from __future__ import annotations

from pydantic import BaseModel

PROMPT = """You are triaging a job seeker's inbox to track their job applications.

From: {sender}
Subject: {subject}
Body (truncated):
{body}

Classify the email as exactly ONE of:
- interview_request: interview invitations, scheduling / rescheduling /
  availability requests, interview confirmations and reminders, interview
  prep material, and next-step emails that reference a further interview
  round (including third-party interview platforms like Karat, and
  schedulers like GoodTime or Calendly when the event is a job interview).
- assessment: take-home assignments or online tests / coding challenges
  (HackerRank, Codility, CodeSignal, Karat practice, etc.) — invitations,
  instructions, or reminders to complete one.
- offer: a job offer, offer letter, or offer-package discussion.
- rejection: the company is not moving forward — application declined,
  position filled, assessment or interview failed.
- follow_up: application receipts / confirmations ("thanks for applying"),
  recruiter check-ins, thank-you notes, and status updates that require no
  action and do not reference a further interview round.
- other: NOT about one of the job seeker's job applications — newsletters,
  job-alert digests, marketing, product receipts, account/security notices.

Also extract:
- company: the EMPLOYER the job seeker is applying to / interviewing with —
  never the ATS or scheduling vendor, and NEVER a person's name (recruiters,
  interviewers, and the job seeker are people, not companies). (A Karat
  interview delivered "to Headway" → "Headway"; a Greenhouse/Lever/Ashby/
  GoodTime notification names the employer in subject or body.) null when no
  employer organization is identifiable.
- role: the job title mentioned (e.g. "Senior Software Engineer"), null if
  absent.
- stage: only for interview_request — "screen" for a first recruiter call /
  phone screen, "interview" for technical / hiring-manager / onsite / final
  rounds or any round after the first screen. null when unclear or when the
  email is not an interview_request.
- urgency: "high" when action is needed within ~48 hours (upcoming scheduled
  interview, imminent deadline), "medium" for action without a tight
  deadline, "low" for FYI-only.

Return an EmailClassificationResult JSON object.
"""


class EmailClassificationResult(BaseModel):
    classification: str
    urgency: str = "medium"
    company: str | None = None
    role: str | None = None
    stage: str | None = None
