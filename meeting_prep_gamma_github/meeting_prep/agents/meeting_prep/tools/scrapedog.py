# # scrapedog.py — ScrapingDog integrations (LinkedIn Person Profile) + helpers.
# # Fully productionized: correct params, URL/slug handling, array→dict normalization,
# # retries with jitter, robust JSON detection, and structured envelopes.

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List, Union
from urllib.parse import urlparse, urlunparse

import httpx
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------------------
# Local project integration
# --------------------------------------------------------------------------------------
try:
    # Use your project's decorator if present (no-op fallback for docs/tests)
    from agents import function_tool  # type: ignore  # noqa: F401
except Exception:  # pragma: no cover
    def function_tool(fn):  # type: ignore
        return fn

try:
    # Project Settings (env-aware)
    # We use a simple environment getter here since we haven't ported the full config module yet.
    # In the Trade Show agents structure, this might be handled via .env and os.getenv directly in the tool for simplicity
    # or via a shared config. For now, we replicate the robust pattern.
    class Settings(BaseModel):
        scrapingdog_api_key: Optional[str] = Field(default=os.getenv("SCRAPINGDOG_API_KEY"))
except Exception:  # pragma: no cover
    class Settings(BaseModel):  # type: ignore
        scrapingdog_api_key: Optional[str] = Field(default=os.getenv("SCRAPINGDOG_API_KEY"))

__all__ = [
    "LinkedInProfileResponse",
    "fetch_person_profile",
    "find_and_fetch_linkedin_profile_from_doc",
    "extract_linkedin_url_from_text",
    "sanitize_linkedin_url",
]

# --------------------------------------------------------------------------------------
# Logger
# --------------------------------------------------------------------------------------
logger = logging.getLogger("meeting_prep.tools.scrapedog")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

# --------------------------------------------------------------------------------------
# Constants & Regex
# --------------------------------------------------------------------------------------

# Recognize LinkedIn person profile URLs: /in/, /pub/, or /m/in/
LINKEDIN_URL_RE = re.compile(
    r"(https?://)?(www\.)?linkedin\.com/(in|pub|m/in)/[A-Za-z0-9\-_%/]+",
    flags=re.IGNORECASE,
)

# Random UAs to look browser-y
_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


@dataclass
class ScrapingDogConfig:
    api_key: str
    # UPDATED per Scrapingdog "Profile Scraper / Person Profile Scraper" docs:
    # GET https://api.scrapingdog.com/profile/?api_key=...&type=profile&id=<slug>
    endpoint: str = "https://api.scrapingdog.com/profile/"


class LinkedInProfileResponse(BaseModel):
    """
    Uniform return envelope for agent consumption.
    NOTE: `data` is normalized to a DICT (first element) when ScrapingDog returns a LIST.
    """
    ok: bool = Field(..., description="True if fetch succeeded")
    status_code: int = Field(..., description="HTTP-ish status code")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Profile JSON (normalized to dict)")
    error: Optional[str] = Field(default=None, description="Error summary (when ok=False)")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Diagnostics (headers, snippets, upstream errors)")
    source_url: Optional[str] = Field(default=None, description="Canonical LinkedIn URL (if derivable)")
    mode: Optional[str] = Field(default="api", description="Always 'api' here")

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def _get_cfg() -> ScrapingDogConfig:
    settings = Settings()  # env-aware
    key = settings.scrapingdog_api_key or os.getenv("SCRAPINGDOG_API_KEY")
    if not key:
        raise RuntimeError("SCRAPINGDOG_API_KEY is not set")
    return ScrapingDogConfig(api_key=key)


def _jitter_sleep(base: float = 0.5, spread: float = 0.4) -> None:
    time.sleep(max(0.05, random.uniform(base - spread, base + spread)))


def sanitize_linkedin_url(url: str) -> Optional[str]:
    """
    Normalize LinkedIn profile URLs:
      - Trim whitespace + trailing punctuation
      - Force https://www.linkedin.com
      - Remove query/fragment
    Returns canonical URL or None if invalid/off-domain.
    """
    if not url:
        return None
    u = url.strip().rstrip(").,;]}>\"'")
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    try:
        p = urlparse(u)
        if "linkedin.com" not in p.netloc.lower():
            return None
        return urlunparse(("https", "www.linkedin.com", p.path, "", "", ""))
    except Exception:
        return None


def extract_linkedin_url_from_text(doc_text: str, person_name_hint: Optional[str] = None) -> Optional[str]:
    """
    Scan text for a LinkedIn profile URL. If multiple, prefer overlap with name hint.
    """
    if not doc_text:
        return None
    candidates = [m.group(0) for m in LINKEDIN_URL_RE.finditer(doc_text)]
    if not candidates:
        return None

    norm: List[str] = []
    seen: set[str] = set()
    for c in candidates:
        u = sanitize_linkedin_url(c)
        if u and u not in seen:
            seen.add(u)
            norm.append(u)

    if not norm:
        return None

    if person_name_hint:
        toks = [t for t in re.split(r"\s+", person_name_hint.strip().lower()) if t]

        def score(u: str) -> int:
            path = u.lower()
            return sum(1 for t in toks if t in path)

        norm.sort(key=score, reverse=True)

    return norm[0]


def _http_client() -> httpx.Client:
    timeouts = httpx.Timeout(connect=10.0, read=100.0, write=10.0, pool=10.0)
    headers = {
        "User-Agent": random.choice(_UA_POOL),
        "Accept": "application/json, */*;q=0.1",
        "Accept-Language": "en-US,en;q=0.8",
    }
    return httpx.Client(timeout=timeouts, headers=headers, follow_redirects=True)


def _respect_retry_after(resp: httpx.Response) -> None:
    ra = resp.headers.get("Retry-After")
    if ra:
        try:
            time.sleep(min(30.0, float(ra)))
            return
        except Exception:
            pass
    time.sleep(2.0)


def _looks_like_slug(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-_%]+", s.strip("/")))


def _extract_public_id_from_url_or_slug(s: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Accept a full LinkedIn URL or a bare slug.
    Returns (public_id, canonical_profile_url).

    For the Profile Scraper API we pass this slug as the `id` param.
    """
    if not s:
        return None, None

    s = s.strip()
    if _looks_like_slug(s):
        slug = s.strip("/")
        return slug, f"https://www.linkedin.com/in/{slug}"

    u = sanitize_linkedin_url(s)
    if not u:
        return None, None
    try:
        p = urlparse(u)
        parts = [seg for seg in p.path.strip("/").split("/") if seg]
        if not parts:
            return None, None
        idx = 0
        if parts[0].lower() == "m":
            idx = 1
        if idx >= len(parts) or parts[idx].lower() not in ("in", "pub"):
            return None, None
        if idx + 1 >= len(parts):
            return None, None
        slug = parts[idx + 1].strip("/")
        slug = re.split(r"[?#]", slug)[0]
        if _looks_like_slug(slug):
            return slug, f"https://www.linkedin.com/in/{slug}"
    except Exception:
        return None, None
    return None, None


def _is_json_like(resp: httpx.Response) -> bool:
    """
    Consider JSON-like if Content-Type says JSON OR if body starts with '{' or '['.
    """
    ct = (resp.headers.get("Content-Type") or "").lower()
    if "application/json" in ct:
        return True
    body = resp.text.strip() if resp.text else ""
    return body.startswith("{") or body.startswith("[")

# --------------------------------------------------------------------------------------
# Public tools
# --------------------------------------------------------------------------------------

@function_tool
def fetch_person_profile(
    linkedin_url: str,
    *,
    premium: Optional[bool] = None,
    webhook: Optional[bool] = None,
) -> LinkedInProfileResponse:
    """
    ScrapingDog Person Profile Scraper (per docs):

      GET https://api.scrapingdog.com/profile/
          ?api_key=...
          &type=profile
          &id=<public_identifier>

    linkedin_url:
        Full LinkedIn profile URL or a 'slug' (public identifier).
        We extract the slug and pass it as the `id` parameter.

    premium:
        Optional bool. When True, enables premium proxies to bypass LinkedIn captcha.
        Forwarded as "premium=true"/"premium=false" as per Scrapingdog docs.

    webhook:
        Optional bool. When True, sends `webhook=true` to schedule scraping
        (Scrapingdog will scrape and deliver later to your configured webhook).
        We still return immediately; callers should handle 202 / async behavior if used.
    """
    cfg = _get_cfg()

    # Simplified extraction per user request
    slug = linkedin_url
    if "linkedin.com/in/" in linkedin_url:
        slug = linkedin_url.split("linkedin.com/in/")[-1].rstrip('/')
    else:
        slug = linkedin_url.rstrip('/')
    
    logger.info("📝 Extracted LinkedIn slug: %s", slug)
    print(f"\n>>> [ScrapingDog] Fetching profile for slug: {slug} ...")
    canonical_url = f"https://www.linkedin.com/in/{slug}"

    # Map to new Profile Scraper params (id + type=profile)
    params: Dict[str, Any] = {
        "api_key": cfg.api_key,
        "type": "profile",
        "id": slug,
        "premium": "true", # Hardcoded per user request
    }

    if webhook is not None:
        # Only relevant when type=profile (per docs)
        params["webhook"] = "true" if webhook else "false"

    endpoint = cfg.endpoint
    last_err: Optional[str] = None

    with _http_client() as client:
        for attempt in range(1, 5):
            try:
                _jitter_sleep()
                resp = client.get(endpoint, params=params)
                sc = resp.status_code

                if sc == 429:
                    logger.warning("ScrapingDog 429 rate limit (attempt %s).", attempt)
                    _respect_retry_after(resp)
                    last_err = f"429 (attempt {attempt})"
                    continue

                if sc in (401, 403):
                    return LinkedInProfileResponse(
                        ok=False,
                        status_code=sc,
                        error="Auth/plan error from ScrapingDog. Check API key, plan, or credits.",
                        details={"headers": dict(resp.headers), "body_head": resp.text[:500]},
                        source_url=canonical_url,
                        mode="api",
                    )

                if sc == 404:
                    return LinkedInProfileResponse(
                        ok=False,
                        status_code=404,
                        error="Profile not found or ID/slug is invalid.",
                        details=None,
                        source_url=canonical_url,
                        mode="api",
                    )

                if sc == 202:
                    # Docs: 202 means scraping still in progress for LinkedIn.
                    # We treat this as a transient failure and retry a few times.
                    last_err = "202 Accepted (profile scraping still in progress)"
                    logger.info("ScrapingDog returned 202 (in progress) (attempt %s).", attempt)
                    _jitter_sleep(2.0, 1.0)
                    continue

                if sc == 410:
                    # Docs: 410 = request timeout on their side, safe to retry.
                    last_err = "410 Request timeout"
                    logger.warning("ScrapingDog 410 timeout (attempt %s); will retry.", attempt)
                    _jitter_sleep(1.5, 0.7)
                    continue

                if sc != 200:
                    last_err = f"HTTP {sc}: {resp.text[:200]}"
                    logger.warning("ScrapingDog non-200 (attempt %s): %s", attempt, last_err)
                    _jitter_sleep(1.0, 0.6)
                    continue

                if not _is_json_like(resp):
                    return LinkedInProfileResponse(
                        ok=False,
                        status_code=200,
                        error="Non-JSON response from ScrapingDog.",
                        details={"content_type": resp.headers.get("Content-Type"), "body_head": resp.text[:500]},
                        source_url=canonical_url,
                        mode="api",
                    )

                # Decode
                try:
                    payload: Union[Dict[str, Any], List[Dict[str, Any]]] = resp.json()
                except json.JSONDecodeError as e:
                    return LinkedInProfileResponse(
                        ok=False,
                        status_code=200,
                        error=f"JSON decode error: {e}",
                        details={"body_head": resp.text[:500]},
                        source_url=canonical_url,
                        mode="api",
                    )

                # ScrapingDog returns a LIST for person profiles (often length 1).
                # Normalize to a dict for downstream consumers.
                normalized: Optional[Dict[str, Any]] = None
                if isinstance(payload, list):
                    if len(payload) == 0:
                        return LinkedInProfileResponse(
                            ok=False,
                            status_code=404,
                            error="Profile list is empty.",
                            details=None,
                            source_url=canonical_url,
                            mode="api",
                        )
                    if len(payload) > 1:
                        logger.info("ScrapingDog returned %d items; using first.", len(payload))
                    first = payload[0]
                    if not isinstance(first, dict):
                        return LinkedInProfileResponse(
                            ok=False,
                            status_code=502,
                            error="Unexpected payload shape (list item not dict).",
                            details={"body_head": str(first)[:200]},
                            source_url=canonical_url,
                            mode="api",
                        )
                    normalized = first
                elif isinstance(payload, dict):
                    normalized = payload
                else:
                    return LinkedInProfileResponse(
                        ok=False,
                        status_code=502,
                        error="Unexpected payload shape (neither dict nor list).",
                        details={"type": str(type(payload))},
                        source_url=canonical_url,
                        mode="api",
                    )

                # Upstream error passthrough
                if isinstance(normalized, dict) and normalized.get("error"):
                    return LinkedInProfileResponse(
                        ok=False,
                        status_code=502,
                        error="ScrapingDog upstream error.",
                        details={"upstream_error": normalized.get("error")},
                        source_url=canonical_url,
                        mode="api",
                    )

                return LinkedInProfileResponse(
                    ok=True,
                    status_code=200,
                    data=normalized,
                    error=None,
                    details=None,
                    source_url=canonical_url,
                    mode="api",
                )

            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                last_err = f"network-timeout: {e}"
                logger.warning("ScrapingDog network timeout (attempt %s): %s", attempt, last_err)
                _jitter_sleep(1.2, 0.8)
            except Exception as e:
                last_err = f"unexpected: {type(e).__name__}: {e}"
                logger.warning("ScrapingDog unexpected error (attempt %s): %s", attempt, last_err)
                _jitter_sleep(1.0, 0.6)

    return LinkedInProfileResponse(
        ok=False,
        status_code=502,
        error=f"Failed after retries: {last_err}",
        details=None,
        source_url=canonical_url or linkedin_url,
        mode="api",
    )


@function_tool
def find_and_fetch_linkedin_profile_from_doc(
    doc_text: str,
    person_name_hint: Optional[str] = None,
    *,
    premium: Optional[bool] = None,
) -> LinkedInProfileResponse:
    """
    Convenience: find a LinkedIn URL in arbitrary text, then fetch via ScrapingDog.
    """
    url = extract_linkedin_url_from_text(doc_text, person_name_hint=person_name_hint)
    if not url:
        return LinkedInProfileResponse(
            ok=False,
            status_code=422,
            error="No LinkedIn URL found in research doc. Provide a profile URL or slug.",
            details={"hint": "Use https://www.linkedin.com/in/<slug> or just 'john-smith-1234'."},
            source_url=None,
            mode="api",
        )
    return fetch_person_profile(url, premium=premium)
