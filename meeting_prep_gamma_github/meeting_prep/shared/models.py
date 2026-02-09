from typing import Optional
from pydantic import BaseModel, Field


class FileRef(BaseModel):
    """Reference to a file known to the backend."""

    id: str = Field(..., description="Unique identifier chosen by UI/backend.")
    filename: str
    mime_type: Optional[str] = None
    storage_path: Optional[str] = Field(
        default=None,
        description="Filesystem path or remote key; for local dev, a real path.",
    )


class DeckOutputBase(BaseModel):
    """Base shape for agent outputs."""

    deck_markdown: str
    download_url: Optional[str] = None
