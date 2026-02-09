"""Thin wrapper around the OpenAI Responses API for markdown generation.

Supports GPT-4.1, GPT-5, GPT-5.2 and their mini variants, using the
v1/responses endpoint as recommended by OpenAI for both reasoning and
non-reasoning models.
"""

import json
import os
from typing import Any, Dict, Union

from dotenv import load_dotenv
from openai import OpenAI, BadRequestError

from .logging import logger

load_dotenv()

# Primary models per agent (can be overridden from .env)
DEFAULT_STRATEGY_MODEL = os.getenv("TRADE_SHOW_STRATEGY_MODEL", "gpt-5.2")
DEFAULT_BUDGET_MODEL = os.getenv("TRADE_SHOW_BUDGET_MODEL", "gpt-5.2")
DEFAULT_CONTENT_MODEL = os.getenv("TRADE_SHOW_CONTENT_MODEL", "gpt-5.2")

# Optional global fallback if the primary model hits a context window limit
# (e.g., you set TRADE_SHOW_STRATEGY_MODEL=gpt-5.2 but get context_length_exceeded).
FALLBACK_MODEL = os.getenv("TRADE_SHOW_FALLBACK_MODEL", "gpt-4.1")

# Optional knobs for GPT-5 / GPT-5.2 reasoning models (Responses API)
# Docs: https://platform.openai.com/docs/guides/reasoning
REASONING_EFFORT = os.getenv("TRADE_SHOW_REASONING_EFFORT", "medium")  # "none" | "low" | "medium" | "high"
TEXT_VERBOSITY = os.getenv("TRADE_SHOW_TEXT_VERBOSITY", "medium")      # "low" | "medium" | "high"

_client: OpenAI | None = None


def get_client() -> OpenAI:
    """Get (and lazily construct) the OpenAI client."""
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def _extract_text(response: Any) -> str:
    """Extract plain text from a Responses API response in a robust way."""
    parts: list[str] = []

    output = getattr(response, "output", None)
    if output:
        for item in output:
            content_list = getattr(item, "content", []) or []
            for content in content_list:
                if getattr(content, "type", None) == "output_text":
                    text_obj = getattr(content, "text", None)
                    if text_obj is not None:
                        value = getattr(text_obj, "value", None)
                        if isinstance(value, str):
                            parts.append(value)

    # Fallback: some SDKs expose `output_text` directly
    if not parts and hasattr(response, "output_text"):
        try:
            value = getattr(response, "output_text")
            if isinstance(value, str):
                parts.append(value)
        except Exception:
            pass

    text = "\n".join(parts).strip()
    return text


def _build_request_kwargs(model: str, instructions: str, user_input: str) -> Dict[str, Any]:
    """Build kwargs for client.responses.create, adding reasoning/text when appropriate."""
    kwargs: Dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": user_input,
    }

    # GPT-5 family supports reasoning + text controls on the Responses API
    # (gpt-5, gpt-5-mini, gpt-5.2, gpt-5.2-mini, etc.).
    model_lc = model.lower()
    if model_lc.startswith("gpt-5"):
        reasoning = {}
        if REASONING_EFFORT:
            reasoning["effort"] = REASONING_EFFORT  # "none" | "low" | "medium" | "high"
        if reasoning:
            kwargs["reasoning"] = reasoning

        text_cfg = {}
        if TEXT_VERBOSITY:
            text_cfg["verbosity"] = TEXT_VERBOSITY  # "low" | "medium" | "high"
        if text_cfg:
            kwargs["text"] = text_cfg

    return kwargs


def _call_responses_api(model: str, instructions: str, user_input: str) -> str:
    """Single call to v1/responses, with logging."""
    client = get_client()
    kwargs = _build_request_kwargs(model, instructions, user_input)

    logger.info("Calling OpenAI Responses API with model=%s", model)
    response = client.responses.create(**kwargs)
    return _extract_text(response)


def generate_markdown(
    *,
    model: str,
    instructions: str,
    input_payload: Union[str, Dict[str, Any]],
) -> str:
    """Call the Responses API and return plain markdown text.

    - Works with GPT-4.1, GPT-4.1-mini, GPT-5, GPT-5-mini, GPT-5.2, GPT-5.2-mini...
    - Uses v1/responses for both reasoning and non-reasoning models.
    - On `context_length_exceeded` (or similar context window errors),
      automatically falls back to `FALLBACK_MODEL` (default: gpt-4.1)
      if it differs from the primary model.
    """
    if isinstance(input_payload, dict):
        user_input = json.dumps(input_payload, ensure_ascii=False, indent=2)
    else:
        user_input = input_payload

    primary_model = model
    try:
        return _call_responses_api(primary_model, instructions, user_input)
    except BadRequestError as e:
        msg = str(e)

        # Detect context window issues generically.
        if (
            ("context_length_exceeded" in msg or "context window" in msg)
            and FALLBACK_MODEL
            and FALLBACK_MODEL != primary_model
        ):
            logger.warning(
                "Model %s hit context window limits. Falling back to %s.",
                primary_model,
                FALLBACK_MODEL,
            )
            return _call_responses_api(FALLBACK_MODEL, instructions, user_input)

        # Any other BadRequestError bubbles up so we don't silently hide misconfig.
        logger.error("OpenAI BadRequestError for model %s: %s", primary_model, msg)
        raise
