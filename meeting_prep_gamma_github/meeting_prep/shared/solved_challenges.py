"""Central access point for 'Solved Challenges' data.

Works both when:
- The CSV is global (no `company_id` column) – all rows are shared across companies.
- The CSV has a `company_id` column – rows are filtered per company.
"""

import os
from functools import lru_cache

import pandas as pd

from .logging import logger

DEFAULT_PATH = os.getenv(
    "TRADE_SHOW_SOLVED_CHALLENGES_PATH",
    "data/solved_challenges.csv",
)


@lru_cache(maxsize=256)
def _load_all() -> pd.DataFrame:
    """Load the solved challenges CSV once and cache it."""
    if not os.path.isfile(DEFAULT_PATH):
        logger.warning(
            "Solved challenges file not found at %s. Returning empty DataFrame.",
            DEFAULT_PATH,
        )
        return pd.DataFrame()

    logger.info("Loading solved challenges from %s", DEFAULT_PATH)
    try:
        df = pd.read_csv(DEFAULT_PATH)
    except Exception as exc:
        logger.error(
            "Failed to read solved challenges CSV at %s: %s",
            DEFAULT_PATH,
            exc,
        )
        return pd.DataFrame()

    return df


def load_for_company(company_id: str | None) -> pd.DataFrame:
    """Return solved challenges for a given company_id, or global dataset if not segmented.

    Behaviors:
    - If the dataset is *not* segmented by company (no `company_id` column)
      OR if company_id is None/empty:
        -> return the full dataset.
    - If `company_id` column exists:
        -> return only rows matching that company_id.
    """
    df = _load_all()
    if df.empty:
        return df

    # No company segmentation => use as a shared/global solved challenges pool.
    if not company_id or "company_id" not in df.columns:
        logger.info(
            "Using global solved challenges dataset (no company_id filtering applied)."
        )
        return df.reset_index(drop=True)

    filtered = df[df["company_id"] == company_id].copy()
    if filtered.empty:
        logger.info(
            "No solved challenges found for company_id=%s; returning empty DataFrame.",
            company_id,
        )
        return pd.DataFrame(columns=df.columns)

    return filtered.reset_index(drop=True)
