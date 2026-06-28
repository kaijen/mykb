"""Inhaltsextraktion: lokale Dateien (PDF/MD/TXT) und HTML → Text.

Defensiv: eine fehlerhafte Datei darf den Lauf nicht abbrechen.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger()


@dataclass
class Extracted:
    text: str
    title: str
    pages: int = 0
    content_hash: str = ""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_pdf(path: Path) -> Extracted:
    from pypdf import PdfReader

    data = path.read_bytes()
    reader = PdfReader(io.BytesIO(data))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return Extracted(text, path.stem, len(reader.pages), sha256_bytes(data))


def extract_textfile(path: Path) -> Extracted:
    data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    return Extracted(text, path.stem, 0, sha256_bytes(data))


def load_file(path: Path) -> Extracted | None:
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return extract_pdf(path)
        if suffix in {".md", ".markdown", ".txt"}:
            return extract_textfile(path)
    except Exception as exc:  # defensiv
        logger.error("extract_failed", file=str(path), error=str(exc))
    return None


def html_to_text(html: str) -> tuple[str, str]:
    """HTML auf Lesetext reduzieren. Liefert (text, title).

    Bewusst permissiv (BeautifulSoup, MIT) statt trafilatura (GPLv3), passend
    zur sonst Apache/MIT/BSD-Linie des Projekts.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    for tag in soup(
        ["script", "style", "nav", "header", "footer", "aside", "noscript", "form"]
    ):
        tag.decompose()

    raw = soup.get_text("\n")
    lines = [ln.strip() for ln in raw.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return text, title
