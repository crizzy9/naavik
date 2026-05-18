"""naavik-ops CLI dispatcher.

Routes `<group> <command> [args]` to module functions. Each group maps to a
Python module under `naavik_ops/`; each command maps to a `cmd_<name>` function.

Subcommand groups (per design doc § 10):
  task     list / insert / defer / prioritize / move / renumber / check / bump
           / sync / next-unblocked
  release  cut / dry-run / changelog
  deps     add / remove / list / check
  gh       (subprocess wrappers around scripts/gh-project.sh during A.29)
  memory   (subprocess wrappers around scripts/agent-memory.sh during A.29)

Direct: --help, --version
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence

from naavik_ops import __version__

GROUPS: dict[str, str] = {
    "task": "naavik_ops.task",
    "release": "naavik_ops.release",
    "deps": "naavik_ops.deps",
    "gh": "naavik_ops.gh",
    "memory": "naavik_ops.memory",
}

USAGE = """\
naavik-ops — agent-system operations dispatcher

Usage:
  naavik-ops <group> <command> [args] [--dry-run]
  naavik-ops --help | --version

Groups:
  task      release-version task ops (list / insert / defer / prioritize / move / etc.)
  release   release ceremony (cut / dry-run / changelog)
  deps      cross-task / cross-version dependency graph (add / remove / list / check)
  gh        GitHub Project + Issue ops (subprocess wraps scripts/gh-project.sh during A.29)
  memory    agent memory ops (subprocess wraps scripts/agent-memory.sh during A.29)

Run `naavik-ops <group> --help` for group-level help.

Design doc: docs/design/PHASE_NUMBERING.md
Plan:       docs/plans/24-A.29-phase-numbering-system.md
"""


def _print_help() -> int:
    sys.stdout.write(USAGE)
    return 0


def _print_version() -> int:
    sys.stdout.write(f"naavik-ops {__version__}\n")
    return 0


def main(argv: Sequence[str]) -> int:
    """Dispatch to <group> <command> [args]."""
    if not argv or argv[0] in ("-h", "--help", "help"):
        return _print_help()
    if argv[0] in ("-V", "--version"):
        return _print_version()

    group = argv[0]
    if group not in GROUPS:
        sys.stderr.write(f"naavik-ops: unknown group '{group}'. Run --help.\n")
        return 2

    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        try:
            module = importlib.import_module(GROUPS[group])
        except ImportError as e:
            sys.stderr.write(f"naavik-ops {group}: failed to load module: {e}\n")
            return 2
        doc = getattr(module, "__doc__", None) or f"(no help available for '{group}')"
        sys.stdout.write(doc.rstrip() + "\n")
        return 0

    command = argv[1]
    rest = list(argv[2:])

    try:
        module = importlib.import_module(GROUPS[group])
    except ImportError as e:
        sys.stderr.write(f"naavik-ops {group}: failed to load module: {e}\n")
        return 2

    fn_name = f"cmd_{command.replace('-', '_')}"
    fn = getattr(module, fn_name, None)
    if fn is None:
        sys.stderr.write(
            f"naavik-ops {group}: unknown command '{command}'. Run `naavik-ops {group} --help`.\n"
        )
        return 2

    try:
        result = fn(rest)
    except KeyboardInterrupt:
        sys.stderr.write("\nnaavik-ops: interrupted\n")
        return 130
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — top-level dispatcher boundary
        sys.stderr.write(f"naavik-ops {group} {command}: {e}\n")
        return 1
    return int(result or 0)
