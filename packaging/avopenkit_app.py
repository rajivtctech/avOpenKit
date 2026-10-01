"""Entry point for the packaged program (PyInstaller needs a script, not a module)."""

import sys

from avopenkit.__main__ import main

sys.exit(main())
