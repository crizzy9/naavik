"""naavik_ops.lib — shared helpers.

Modules:
  flock        — fcntl.flock context manager (single-writer serialization)
  github_api   — GraphQL wrapper with hasNextPage pagination (fixes the 200-cap)
  jsonl        — atomic JSONL read/write (tempfile + os.replace)
  roadmap      — ROADMAP.md parser (A.29: wraps .claude/naavik_ops/lib/roadmap.py)
  semver       — 4-level semver schema parse/compare/bump
  changelog    — keepachangelog v1.1.0 + Conventional Commits classification

Subprocess wrapper error semantics: every shim around the legacy bash scripts
re-raises `subprocess.CalledProcessError` as a Python-native `NaavikOpsError`
with the bash stderr captured verbatim. See `gh.py` / `memory.py`.
"""


class NaavikOpsError(RuntimeError):
    """Wrapped error from a subprocess shim or internal failure."""
