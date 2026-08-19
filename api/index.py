"""Vercel serverless entry point.

Vercel's Python runtime serves the ASGI application exported as `app`. Every
`/api/*` request is rewritten to this function by `vercel.json`, so the same
FastAPI app that runs under uvicorn also runs here — including the Telegram
webhook, which is how the bot works without a long-running process.

Websockets are not available on serverless; the Mini App detects that and falls
back to polling `/api/pvp/{id}/state`, which returns the same authoritative
state. The time-driven parts of the game are advanced by Vercel Cron calling
`/api/internal/tick`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for package_dir in ("backend", "shared", "bot"):
    path = str(ROOT / package_dir)
    if path not in sys.path:
        sys.path.insert(0, path)

# The in-process scheduler must not run in a function that is frozen between
# requests; Vercel Cron drives the tick instead.
os.environ.setdefault("ENABLE_SCHEDULER", "0")

from app.main import app  # noqa: E402

__all__ = ["app"]
