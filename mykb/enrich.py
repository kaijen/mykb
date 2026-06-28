"""KI-Anreicherung beim Ingest über einen lokalen LLM (Ollama, CPU).

Erzeugt je Quelle eine kurze Zusammenfassung und automatische Schlagworte —
die fabric-Idee „versteht den Inhalt". Läuft bewusst auf CPU/RAM (Ollama), um
nicht mit dem Embedder um VRAM zu konkurrieren.

Defensiv: ist Ollama nicht erreichbar oder die Antwort unbrauchbar, wird ohne
Anreicherung weitergemacht (``(None, [])``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import structlog

from .config import Config

logger = structlog.get_logger()

_PROMPT = (
    "Du erhältst den Inhalt eines Dokuments. Antworte ausschließlich als JSON "
    "mit den Feldern 'summary' (2–3 Sätze, Deutsch, sachlich) und 'tags' "
    "(Liste aus 3–7 kurzen Schlagworten, Deutsch oder Fachbegriff). "
    "Kein weiterer Text.\n\nDOKUMENT:\n"
)


@dataclass
class Enrichment:
    summary: str = ""
    tags: list[str] | None = None


class Enricher:
    """Dünner Ollama-Client für Zusammenfassung + Schlagworte."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def enrich(self, text: str) -> Enrichment:
        if not text.strip():
            return Enrichment()
        import httpx

        payload = {
            "model": self.cfg.ollama_model,
            "prompt": _PROMPT + text[: self.cfg.enrich_max_chars],
            "stream": False,
            "format": "json",
        }
        try:
            with httpx.Client(timeout=self.cfg.http_timeout) as client:
                resp = client.post(f"{self.cfg.ollama_url}/api/generate", json=payload)
                resp.raise_for_status()
                raw = resp.json().get("response", "")
            data = json.loads(raw)
        except Exception as exc:  # defensiv: Anreicherung ist optional
            logger.warning("enrich_failed", error=str(exc)[:200])
            return Enrichment()

        summary = (data.get("summary") or "").strip()
        tags = [str(t).strip() for t in (data.get("tags") or []) if str(t).strip()]
        return Enrichment(summary=summary, tags=tags)
