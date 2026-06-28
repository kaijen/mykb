"""HTTP-Abruf für Web-Ingestion und Link-Erreichbarkeitsprüfung."""
from __future__ import annotations

from dataclasses import dataclass

import structlog

from .config import Config

logger = structlog.get_logger()


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int | None
    ok: bool
    html: str | None = None
    error: str | None = None


def fetch(url: str, cfg: Config, method: str = "GET") -> FetchResult:
    """Ruft eine URL ab (Redirects folgen). Wirft nicht — Fehler werden im
    Ergebnis gemeldet (defensiv, damit ein toter Link den Lauf nicht killt)."""
    import httpx

    headers = {"User-Agent": cfg.http_user_agent}
    try:
        with httpx.Client(
            follow_redirects=True, timeout=cfg.http_timeout, headers=headers
        ) as client:
            resp = client.request(method, url)
        ok = 200 <= resp.status_code < 400
        html = resp.text if method == "GET" else None
        return FetchResult(url, str(resp.url), resp.status_code, ok, html)
    except httpx.TimeoutException:
        return FetchResult(url, url, None, False, error="timeout")
    except Exception as exc:  # defensiv: DNS, TLS, Verbindungsfehler …
        return FetchResult(url, url, None, False, error=str(exc)[:200])
