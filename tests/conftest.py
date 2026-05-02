"""Test configuration. Inserts `src/` onto sys.path so tests can import as the
runtime does (`from main import app`, `from ui.templates_setup import templates`).
"""

import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Switch CWD to the repo root so relative paths in the FastAPI app resolve
# (e.g. `Jinja2Templates(directory="src/ui/templates")`).
os.chdir(Path(__file__).resolve().parent.parent)
