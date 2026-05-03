"""Typst PDF generation — async compile + native page-count validation.

Per BACKEND.md § K.4 + plan 10 § C.2.1.
"""

from __future__ import annotations

from .compiler import CompileResult, TypstError, compile, template_path
from .validator import overflows, validate_page_count

__all__ = [
    "CompileResult",
    "TypstError",
    "compile",
    "overflows",
    "template_path",
    "validate_page_count",
]
