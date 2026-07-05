"""Guard: every service function the conftest shim patches must still exist
on its real module.

`tests/conftest.py::_patch_services_to_sample_data` monkeypatches ~60 service
functions *by attribute name* onto in-memory `sample_data` shadow rows. If a
refactor moves or renames one of those functions without leaving a same-name
re-export, the `monkeypatch.setattr` silently no-ops for a function that no
longer exists — pytest raises `AttributeError` at setattr time only for a
*missing* target, but a target that was moved-then-shadowed by a facade, or a
rename that lands a *different* function under the old name, slips through and
un-shims the ~189 files that carry the marker (green-but-meaningless).

This test AST-parses the conftest fixture, extracts every
`monkeypatch.setattr(<services module>, "<attr>", ...)` target, and asserts the
attribute still resolves on the freshly-imported real module. It is the
Phase-0.1 prerequisite for the Phase-4 god-module splits — see
`docs/plans/91-full-codebase-refactor-audit.md` (cross-cutting rule §1).

If this test goes red during a refactor: either add a re-export of the moved
symbol on its old module, or update the conftest shim to the new location —
**in the same commit** as the move.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

_CONFTEST = Path(__file__).resolve().parent / "conftest.py"
_FIXTURE_NAME = "_patch_services_to_sample_data"


def _shim_targets() -> list[tuple[str, str]]:
    """Parse conftest and return [(module_path, attr), ...] for every
    `monkeypatch.setattr(mod, "attr", fn)` inside the shim fixture."""
    tree = ast.parse(_CONFTEST.read_text())
    fixture = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == _FIXTURE_NAME
        ),
        None,
    )
    assert fixture is not None, f"{_FIXTURE_NAME} not found in {_CONFTEST}"

    # Local name → dotted module path, for every `from services import ...`
    # inside the fixture body (both the big tuple import and `llm_models`).
    service_mods: dict[str, str] = {}
    for node in ast.walk(fixture):
        if isinstance(node, ast.ImportFrom) and node.module == "services":
            for alias in node.names:
                local = alias.asname or alias.name
                service_mods[local] = f"services.{alias.name}"

    targets: list[tuple[str, str]] = []
    for node in ast.walk(fixture):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "setattr":
            continue
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "monkeypatch"):
            continue
        if len(node.args) < 2:
            continue
        mod_arg, attr_arg = node.args[0], node.args[1]
        if not (isinstance(mod_arg, ast.Name) and mod_arg.id in service_mods):
            continue
        if not (isinstance(attr_arg, ast.Constant) and isinstance(attr_arg.value, str)):
            continue
        targets.append((service_mods[mod_arg.id], attr_arg.value))
    return sorted(set(targets))


_TARGETS = _shim_targets()


def test_shim_targets_parsed():
    """Sanity check that the AST parser actually found the shim targets — a
    silent parse drift (0 targets) would make the guard vacuously pass."""
    assert len(_TARGETS) >= 50, (
        f"only parsed {len(_TARGETS)} shim targets from conftest — the parser "
        "drifted from the fixture shape (expected ~60). Fix _shim_targets()."
    )


@pytest.mark.parametrize(
    ("module_path", "attr"),
    _TARGETS,
    ids=[f"{m.split('.')[-1]}.{a}" for m, a in _TARGETS],
)
def test_shim_target_exists(module_path: str, attr: str):
    module = importlib.import_module(module_path)
    assert hasattr(module, attr), (
        f"conftest shims `{module_path}.{attr}` but it no longer exists on the "
        f"real module. A refactor moved/renamed it — add a re-export on "
        f"{module_path} or update the conftest shim in the SAME commit "
        "(plan 91 cross-cutting rule §1)."
    )
