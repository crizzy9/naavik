"""Plan 09a · Issue 14 — Native `<dialog>` backdrop click closes the modal."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


def test_base_js_closes_dialog_on_self_click(client: TestClient) -> None:
    """Click on the dialog element itself (the backdrop area) closes it."""
    body = client.get("/static/base.js").text
    assert "DIALOG" in body and "hasAttribute('open')" in body, (
        "Issue 14 · base.js must register a native-dialog backdrop click handler"
    )


def test_interactions_doc_documents_native_pattern() -> None:
    """INTERACTIONS.md § E.2 must document the new native-dialog pattern."""
    with open("docs/design/INTERACTIONS.md", encoding="utf-8") as f:
        content = f.read()
    assert "Issue 14" in content or "Backdrop click — native" in content
    # Old `.modal-backdrop` pattern marked deprecated
    assert "deprecated" in content.lower()
