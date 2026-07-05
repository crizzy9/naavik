"""Plan 87 / 0.4.5.03 — conftest opt-in marker contract.

Verifies the inversion: `_patch_services_to_sample_data` is no longer
autouse; it activates only when the test (or its module / class) is
marked with `pytest.mark.uses_sample_data_shims`. An unmarked test in
the same file does not get the shim — service-layer functions retain
their original implementations.
"""

from __future__ import annotations

import inspect

import pytest

from services import applications as application_service


def test_unmarked_test_does_not_get_application_service_shim():
    """Without the marker, `application_service.get_application` is the
    real coroutine (living under `src/services/` — since plan 91 4.2 the
    implementation is `services/applications/queries.py` behind the
    facade), not the conftest's `_get_application` closure that reads from
    `db.sample_data.APPLICATIONS`."""
    src_file = inspect.getsourcefile(application_service.get_application)
    assert src_file is not None
    assert "/src/services/" in src_file and "conftest" not in src_file, (
        f"expected real implementation; got {src_file} — the autouse "
        "shim has leaked into a non-marked test (plan 87 contract broken)"
    )


@pytest.mark.uses_sample_data_shims
def test_marked_test_gets_application_service_shim():
    """With the marker, `application_service.get_application` is the
    conftest's monkey-patched closure that reads sample_data.APPLICATIONS."""
    src_file = inspect.getsourcefile(application_service.get_application)
    assert src_file is not None
    assert src_file.endswith("tests/conftest.py"), (
        f"expected conftest shim; got {src_file} — the opt-in marker did "
        "not activate the fixture (plan 87 contract broken)"
    )
