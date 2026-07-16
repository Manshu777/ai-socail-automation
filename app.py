#!/usr/bin/env python3
"""
AI Social Media Automation — entry point.

Desktop (local): CustomTkinter UI via `python app.py`
Cloud (Render):  Web UI automatically — no Tk / display needed

Run locally as web:
    python app.py --web
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import get_logger  # noqa: E402


def _wants_web() -> bool:
    """Detect cloud / headless environments (e.g. Render)."""
    if "--web" in sys.argv or os.getenv("APP_MODE", "").lower() == "web":
        return True
    # Render and similar PaaS set PORT and often RENDER=true
    if os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"):
        return True
    if os.getenv("PORT") and not os.getenv("DISPLAY"):
        # Common on Linux containers without a GUI
        return True
    # No Tk available → fall back to web
    try:
        import tkinter  # noqa: F401
        import _tkinter  # noqa: F401
    except Exception:
        return True
    return False


def main() -> int:
    logger = get_logger("app")
    use_web = _wants_web()
    logger.info(
        "Starting AI Social Media Automation (%s mode)",
        "web" if use_web else "desktop",
    )
    try:
        if use_web:
            from web_app import run_web

            run_web()
        else:
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
