"""Command-line entrypoint for the ApplyPilot local API."""

from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "applypilot.api.app:create_app",
        factory=True,
        host=os.getenv("APPLYPILOT_API_HOST", "127.0.0.1"),
        port=int(os.getenv("APPLYPILOT_API_PORT", "8765")),
    )
