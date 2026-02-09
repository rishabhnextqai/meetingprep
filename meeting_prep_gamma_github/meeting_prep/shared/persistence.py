"""Simple filesystem-based persistence for decks."""

import os
from pathlib import Path

from .logging import logger

BASE_OUTPUT_DIR = os.getenv("TRADE_SHOW_OUTPUT_DIR", "outputs")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_deck(event_id: str, step: str, markdown: str) -> str:
    """Save deck markdown to outputs/<event_id>/<step>/deck.md and return the path."""
    base = Path(BASE_OUTPUT_DIR) / event_id / step
    _ensure_dir(base)
    path = base / "deck.md"

    logger.info("Saving deck for event_id=%s step=%s to %s", event_id, step, path)
    path.write_text(markdown, encoding="utf-8")

    return str(path.resolve())
