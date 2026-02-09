"""Filesystem-based helpers for loading FileRef content."""

import os
from typing import Optional

import pandas as pd
import pdfplumber
from docx import Document

from .models import FileRef
from .logging import logger


def _ensure_path(file_ref: FileRef) -> str:
    if not file_ref.storage_path:
        raise ValueError(f"FileRef {file_ref.id} has no storage_path set")
    path = file_ref.storage_path
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File does not exist at storage_path: {path}")
    return path


def read_document(file_ref: FileRef) -> str:
    """Read a document into text (txt, md, pdf, docx, csv, xlsx)."""
    path = _ensure_path(file_ref)
    _, ext = os.path.splitext(path)
    ext = ext.lower()

    logger.info("Reading document %s (%s)", file_ref.filename, ext)

    if ext in [".txt", ".md"]:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    if ext == ".pdf":
        try:
            import pymupdf4llm
            return pymupdf4llm.to_markdown(path)
        except ImportError:
            logger.warning("pymupdf4llm not found, falling back to pdfplumber")
            texts = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    texts.append(page.extract_text() or "")
            return "\n\n".join(texts)

    if ext == ".docx":
        doc = Document(path)
        paragraphs = [p.text for p in doc.paragraphs]
        return "\n".join(paragraphs)

    if ext in [".csv", ".tsv"]:
        df = pd.read_csv(path, sep="\t" if ext == ".tsv" else ",")
        return df.to_csv(index=False)

    if ext in [".xlsx", ".xls"]:
        df = pd.read_excel(path)
        return df.to_csv(index=False)

    # Fallback: plain text
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def read_spreadsheet(file_ref: FileRef) -> pd.DataFrame:
    """Load a CSV/Excel file into a DataFrame."""
    path = _ensure_path(file_ref)
    _, ext = os.path.splitext(path)
    ext = ext.lower()

    logger.info("Reading spreadsheet %s (%s)", file_ref.filename, ext)

    if ext in [".csv", ".tsv"]:
        return pd.read_csv(path, sep="\t" if ext == ".tsv" else ",")
    if ext in [".xlsx", ".xls"]:
        return pd.read_excel(path)

    raise ValueError(f"Unsupported spreadsheet extension for path: {path}")


def read_maybe(file_ref: Optional[FileRef]) -> Optional[str]:
    if file_ref is None:
        return None
    return read_document(file_ref)
