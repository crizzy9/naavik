"""Async Typst compiler — wraps `typst compile` + `typst query`.

Per BACKEND.md § K.4 + plan 10 § C.2.1.

The page count is recovered via `typst query <input.typ> "<naavik-meta>"`
(every Naavik template embeds a `#metadata((pages: counter(page).final()))<naavik-meta>`
element). No `pdfinfo` / poppler dependency — Typst already ships in the
dev shell.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class TypstError(Exception):
    """Compile or query failure."""

    def __init__(self, message: str, *, stderr: str = "", returncode: int = -1) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


class CompileResult(BaseModel):
    output_path: Path
    page_count: int
    byte_size: int
    compiled_at: datetime

    model_config = {"arbitrary_types_allowed": True}


def template_path(template_name: str) -> Path:
    """Resolve a packaged template by short name (e.g. `onepage`)."""
    candidate = TEMPLATES_DIR / f"{template_name}.typ"
    if not candidate.exists():
        raise TypstError(f"template not found: {candidate}")
    return candidate


async def _run(args: list[str]) -> tuple[int, bytes, bytes]:
    """Run a subprocess; return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return (proc.returncode or 0), out, err


async def compile(  # noqa: A001 — `compile` is the natural verb
    template_name: str,
    data: dict[str, Any],
    output_path: Path,
    *,
    timeout: float = 30.0,
    pdf_standard: str | None = None,
) -> CompileResult:
    """Compile a packaged Typst template against `data` JSON.

    `data` is serialized to JSON and passed to the template via
    `--input data=...`. The template calls `json.decode(sys.inputs.data)`
    to materialize it. Two passes — compile then query — recover the page
    count from the `<naavik-meta>` metadata element baked into every
    template.

    `pdf_standard` (plan 66, 0.3.1, T6) — when set (e.g. ``"a-1b"`` for
    PDF/A-1b conformance), passed through as ``--pdf-standard <value>``.
    Requires typst 0.13+. Falls through to default PDF (untrusted) when
    None.

    CONCURRENCY (plan 91 6.7): callers pass FIXED output paths
    (`<app_id>/resume.pdf`); two concurrent generations for the SAME
    application race on the file and the loser's PDF wins the disk. The
    per-app in-flight registry in `services.generation.dispatch` is the
    current guard — do not add a second unguarded call site for the same
    application id.
    """
    src = template_path(template_name)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Serialize `data` to a JSON string and pass via --input.
    data_json = json.dumps(data, default=str)

    compile_args = [
        "typst",
        "compile",
        "--root",
        str(src.parent),
        "--input",
        f"data={data_json}",
    ]
    if pdf_standard:
        compile_args += ["--pdf-standard", pdf_standard]
    compile_args += [
        str(src.resolve()),
        str(output_path.resolve()),
    ]
    try:
        rc, _stdout, stderr = await asyncio.wait_for(_run(compile_args), timeout=timeout)
    except TimeoutError as exc:
        raise TypstError(
            f"typst compile timed out after {timeout}s",
            returncode=-1,
        ) from exc
    if rc != 0:
        raise TypstError(
            f"typst compile failed (rc={rc})",
            stderr=stderr.decode("utf-8", errors="replace"),
            returncode=rc,
        )

    # Page count via metadata query (no poppler needed)
    query_args = [
        "typst",
        "query",
        "--root",
        str(src.parent),
        "--input",
        f"data={data_json}",
        str(src.resolve()),
        "<naavik-meta>",
        "--field",
        "value",
        "--one",
    ]
    # Plan 91 6.7 — the compile pass wraps its timeout in TypstError but this
    # query pass leaked a raw TimeoutError past every `except TypstError`
    # handler in the generation pipeline.
    try:
        rc, qstdout, qstderr = await asyncio.wait_for(_run(query_args), timeout=timeout)
    except TimeoutError as exc:
        raise TypstError(
            f"typst query timed out after {timeout}s",
            returncode=-1,
        ) from exc

    if rc != 0:
        raise TypstError(
            f"typst query failed (rc={rc})",
            stderr=qstderr.decode("utf-8", errors="replace"),
            returncode=rc,
        )

    try:
        meta = json.loads(qstdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise TypstError(f"typst query returned invalid JSON: {exc}") from exc

    pages = int(meta.get("pages", 0)) if isinstance(meta, dict) else 0

    byte_size = output_path.stat().st_size if output_path.exists() else 0

    return CompileResult(
        output_path=output_path,
        page_count=pages,
        byte_size=byte_size,
        compiled_at=datetime.now(UTC),
    )
