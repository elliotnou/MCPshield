"""Entry-point shim so `python -m mcp_adapter` works."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main() or 0)
