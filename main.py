from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from app.server import run_server


if __name__ == "__main__":
    run_server()
