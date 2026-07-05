"""Outreach package — OutreachMessage lifecycle + Contact read accessors.

Plan 93 Part 1 grouped `outreach_service` (→ `service.py`) and
`contact_tracker` (→ `contacts.py`) into this package. Both former
surfaces live on this `__init__`; conftest keeps its two seam names via
aliases (`from services import outreach as outreach_service` / `as
contact_tracker`) that bind the same package object, so every shim and
`patch("services.outreach.X")` intercepts.
"""

from __future__ import annotations

from services.outreach.contacts import (
    get_contact,
    list_contacts,
    list_contacts_for_application,
    list_contacts_for_company,
)
from services.outreach.service import (
    create_message,
    get_message,
    list_all_messages,
    list_messages_for_application,
    list_messages_for_contact,
    mark_sent,
)

__all__ = [
    "create_message",
    "get_contact",
    "get_message",
    "list_all_messages",
    "list_contacts",
    "list_contacts_for_application",
    "list_contacts_for_company",
    "list_messages_for_application",
    "list_messages_for_contact",
    "mark_sent",
]
