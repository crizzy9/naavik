"""Page-count validator — reads `CompileResult.page_count` from Typst.

Per plan 10 § C.2.1. No `pdfinfo` / poppler dep — page count comes from
`typst query`'s `<naavik-meta>` payload baked into every template.
"""

from __future__ import annotations

from .compiler import CompileResult


def validate_page_count(result: CompileResult, expected: int) -> bool:
    """True iff the compiled doc has exactly `expected` pages."""
    return result.page_count == expected


def overflows(result: CompileResult, *, max_pages: int = 1) -> bool:
    """True iff the compiled doc has more than `max_pages` pages."""
    return result.page_count > max_pages
