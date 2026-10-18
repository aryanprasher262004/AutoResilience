#!/usr/bin/env python3
"""Run the AutoResilience local-stack CLI from a checkout: `python3 tools/ar/ar.py --help`.

Standard library only (Python >= 3.11), so it needs no virtualenv; works the same on
macOS, Linux and Windows (`py tools\\ar\\ar.py`).
"""

import sys
from pathlib import Path

if sys.version_info < (3, 11):  # noqa: UP036  (friendly message on old interpreters)
    sys.exit("ar needs Python 3.11 or newer")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ar_cli.main import main

if __name__ == "__main__":
    sys.exit(main())
