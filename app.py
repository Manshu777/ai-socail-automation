#!/usr/bin/env python3
"""
AI Social Media Automation — application entry point.

Run:
    python app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path when launched from another cwd
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import get_logger  # noqa: E402


def main() -> int:
    """Boot logging, scheduler hooks, and the CustomTkinter UI."""
    logger = get_logger("app")
    logger.info("Starting AI Social Media Automation")
    try:
        from ui import run_app

        run_app()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0
    except Exception:
        logger.exception("Fatal application error")
        return 1
    logger.info("Application closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
