"""
Gamma API Integration
=====================
Handles theme listing, presentation generation, polling, and download
via the Gamma public API (v1.0).

API Docs: https://developers.gamma.app/reference
"""

from __future__ import annotations

import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger("meeting_prep.gamma")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GAMMA_API_BASE = "https://public-api.gamma.app/v1.0"
GAMMA_GENERATIONS_URL = f"{GAMMA_API_BASE}/generations"
GAMMA_THEMES_URL = f"{GAMMA_API_BASE}/themes"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_gamma_api_key() -> Optional[str]:
    """Retrieve the Gamma API key from environment or Streamlit secrets."""
    key = os.getenv("GAMMA_API_KEY")
    if key:
        return key
    # Fallback: try Streamlit secrets at runtime
    try:
        import streamlit as st
        return st.secrets.get("GAMMA_API_KEY", None)
    except Exception:
        return None


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "accept": "application/json",
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
    }


# ---------------------------------------------------------------------------
# Theme Listing
# ---------------------------------------------------------------------------
def list_themes(
    api_key: str | None = None,
    query: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Fetch available Gamma themes from the workspace.

    Returns a list of dicts with keys: id, name, type, colorKeywords, toneKeywords.
    Paginates automatically to collect all themes.
    """
    api_key = api_key or _get_gamma_api_key()
    if not api_key:
        logger.warning("Gamma API key not set — cannot list themes")
        return []

    headers = {"accept": "application/json", "X-API-KEY": api_key}
    all_themes: list[dict[str, Any]] = []
    cursor: str | None = None

    for _ in range(20):  # safety cap on pages
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        if cursor:
            params["after"] = cursor

        try:
            resp = requests.get(
                GAMMA_THEMES_URL,
                headers=headers,
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch Gamma themes: %s", exc)
            break

        # Response can be a list or paginated object
        if isinstance(data, list):
            all_themes.extend(data)
            break
        elif isinstance(data, dict):
            items = data.get("data", [])
            if isinstance(items, list):
                all_themes.extend(items)
            has_more = data.get("hasMore", False)
            cursor = data.get("nextCursor")
            if not has_more or not cursor:
                break
        else:
            break

    return all_themes


# ---------------------------------------------------------------------------
# Presentation Generation
# ---------------------------------------------------------------------------
def generate_presentation(
    markdown_text: str,
    api_key: str | None = None,
    theme_id: str | None = None,
    export_as: str = "pptx",
    logo_position: str | None = None,
    progress_callback=None,
) -> dict[str, Any]:
    """
    Submit markdown to Gamma, poll for completion, and return result.

    Args:
        markdown_text: The Gamma-ready markdown content.
        api_key: Gamma API key (auto-detected if None).
        theme_id: Optional Gamma theme ID for styling.
        export_as: "pptx" or "pdf".
        logo_position: Optional logo placement key (e.g. "headerFooter").
        progress_callback: Optional callable(status_msg: str, pct: float)
                           for real-time progress updates.

    Returns:
        dict with keys:
            ok (bool), export_url (str|None), generation_id (str|None),
            error (str|None)
    """
    api_key = api_key or _get_gamma_api_key()
    if not api_key:
        return {"ok": False, "export_url": None, "generation_id": None,
                "error": "GAMMA_API_KEY not configured"}

    headers = _auth_headers(api_key)

    # Count slides for numCards hint
    num_cards = sum(1 for line in markdown_text.splitlines() if line.strip() == "---") + 1

    payload: dict[str, Any] = {
        "inputText": markdown_text,
        "textMode": "preserve",
        "format": "presentation",
        "cardSplit": "auto",
        "exportAs": export_as,
        "numCards": num_cards,
        "additionalInstructions": (
            "IMPORTANT RULES: "
            "1. Include ALL sections from the input markdown - do NOT drop, skip, or omit any content. "
            "2. DO NOT add any commentary, filler text, or explanatory notes that are not in the input. "
            "3. DO NOT add phrases like 'Due to space constraints', 'representative sample', etc. "
            "4. Present ONLY the data provided in the markdown, nothing more. "
            "5. Preserve the exact structure and all content from the input."
        ),
    }

    if theme_id:
        payload["themeId"] = theme_id

    if logo_position:
        payload["cardOptions"] = {
            "headerFooter": {
                logo_position: {
                    "type": "image",
                    "source": "themeLogo",
                    "size": "sm",
                }
            }
        }

    def _update(msg: str, pct: float):
        if progress_callback:
            progress_callback(msg, pct)

    # --- Step 1: Submit generation request ---
    _update("Submitting to Gamma API...", 0.05)

    try:
        resp = requests.post(
            GAMMA_GENERATIONS_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        generation_id = resp.json().get("generationId")
        if not generation_id:
            return {"ok": False, "export_url": None, "generation_id": None,
                    "error": "Gamma response missing generationId"}
    except requests.exceptions.HTTPError as exc:
        error_body = ""
        try:
            error_body = exc.response.text[:500]
        except Exception:
            pass
        return {"ok": False, "export_url": None, "generation_id": None,
                "error": f"Gamma API HTTP {exc.response.status_code}: {error_body}"}
    except Exception as exc:
        return {"ok": False, "export_url": None, "generation_id": None,
                "error": f"Gamma API request failed: {exc}"}

    # --- Step 2: Poll for completion ---
    _update("Gamma is generating your presentation...", 0.15)

    status_url = f"{GAMMA_GENERATIONS_URL}/{generation_id}"
    status_headers = {"accept": "application/json", "X-API-KEY": api_key}

    max_attempts = int(os.getenv("GAMMA_MAX_ATTEMPTS", "60"))
    poll_min = float(os.getenv("GAMMA_POLL_MIN_SECONDS", "10"))
    poll_max = float(os.getenv("GAMMA_POLL_MAX_SECONDS", "15"))
    initial_delay = float(os.getenv("GAMMA_INITIAL_DELAY_SECONDS", "5"))

    time.sleep(random.uniform(initial_delay, initial_delay + 1.0))

    for attempt in range(max_attempts):
        pct = 0.15 + (attempt / max_attempts) * 0.75  # 15% → 90%
        _update(
            f"Gamma is generating... (poll {attempt + 1}/{max_attempts})",
            min(pct, 0.90),
        )

        try:
            status_resp = requests.get(status_url, headers=status_headers, timeout=30)
            data = status_resp.json()
            status = data.get("status")

            if status == "completed":
                export_url = data.get("exportUrl")
                if export_url:
                    _update("Presentation ready!", 0.95)
                    return {"ok": True, "export_url": export_url,
                            "generation_id": generation_id, "error": None}
                return {"ok": False, "export_url": None,
                        "generation_id": generation_id,
                        "error": "Gamma completed but no exportUrl returned"}

            if status == "failed":
                return {"ok": False, "export_url": None,
                        "generation_id": generation_id,
                        "error": f"Gamma generation failed: {data}"}

        except Exception as exc:
            logger.warning("Gamma poll error (attempt %d): %s", attempt + 1, exc)

        time.sleep(random.uniform(poll_min, poll_max))

    return {"ok": False, "export_url": None, "generation_id": generation_id,
            "error": f"Gamma generation timed out after {max_attempts} attempts"}


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def download_presentation(url: str, output_path: str | Path) -> bool:
    """Download the generated presentation file from Gamma's export URL."""
    try:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        with requests.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            with out.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        logger.info("Gamma presentation downloaded to %s", out)
        return True
    except Exception as exc:
        logger.warning("Gamma download failed: %s", exc)
        return False
