import os
import re
import uuid
from pathlib import Path

from .logging import logger


def slugify(value: str) -> str:
    """Lowercase, strip non-alphanumerics, replace with '-'."""
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "default"


def generate_event_id() -> str:
    """Fallback random event id (used only if we cannot infer anything)."""
    eid = f"evt-{uuid.uuid4().hex[:8]}"
    logger.info("Generated fallback event_id=%s", eid)
    return eid


def infer_company_id_from_filename(filename: str) -> str:
    """Infer a company_id from a filename, best-effort."""
    base = os.path.splitext(filename)[0]
    cid = slugify(base)
    logger.info("Inferred company_id=%s from filename=%s", cid, filename)
    return cid


def infer_event_id_from_ref(
    *,
    filename: str,
    storage_path: str | None = None,
) -> str | None:
    """Infer a stable event_id from a FileRef.

    Priority:
    1. If storage_path looks like .../<event_id>/<step>/deck.md,
       extract <event_id> from the path.
    2. Otherwise, use the filename stem (without extension).
    3. If both fail, return None and let caller fall back.
    """
    # Try to infer from storage_path (e.g. outputs/<event_id>/strategy/deck.md)
    if storage_path:
        try:
            p = Path(storage_path)
            parts = p.parts
            # ... / <event_id> / <step> / deck.md
            if len(parts) >= 3:
                candidate = parts[-3]
                if candidate and candidate not in ("outputs",):
                    logger.info(
                        "Inferred event_id=%s from storage_path=%s",
                        candidate,
                        storage_path,
                    )
                    return candidate
        except Exception as exc:
            logger.warning(
                "Failed to infer event_id from storage_path=%s: %s",
                storage_path,
                exc,
            )

    # Fallback: derive from filename stem
    stem = Path(filename).stem
    if stem:
        eid = slugify(stem)
        logger.info("Inferred event_id=%s from filename=%s", eid, filename)
        return eid

    return None
