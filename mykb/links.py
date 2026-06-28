"""Linksammlung über Linkwarden.

Linkwarden ist das Capture-/Archiv-Frontend (Browser-Extension, Tags,
Collections, Archivierung). mykb ist die Index- und MCP-Schicht:

- ``sync_from_linkwarden`` zieht die Links per API, übernimmt Metadaten in die
  ``links``-Tabelle und indexiert den Lesetext als ``source_type = link`` in
  ``documents`` (damit semantisch durchsuchbar, überlebt Link-Rot).
- ``check_links`` prüft die Erreichbarkeit (Link-Rot) und aktualisiert den
  Status in ``links``.

Hinweis: Die Linkwarden-API variiert je nach Version. Endpoint und Feldnamen
sind in :class:`Linkwarden` gebündelt und dort ggf. anzupassen.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime

import structlog

from . import extract, store, web
from .config import Config
from .ingest import Ingestor

logger = structlog.get_logger()


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Linkwarden:
    """Dünner Client für die Linkwarden-REST-API."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.base = os.getenv("LINKWARDEN_URL", "").rstrip("/")
        self.token = os.getenv("LINKWARDEN_TOKEN", "")

    def available(self) -> bool:
        return bool(self.base and self.token)

    def fetch_links(self) -> list[dict]:
        """Alle Links abrufen (cursor-basierte Paginierung)."""
        import httpx

        headers = {"Authorization": f"Bearer {self.token}"}
        out: list[dict] = []
        seen_ids: set = set()
        cursor: int | None = None
        with httpx.Client(timeout=self.cfg.http_timeout, headers=headers) as client:
            # Harte Obergrenze als Sicherung gegen Fehlverhalten der Paginierung.
            for _ in range(1000):
                params: dict[str, int] = {}
                if cursor is not None:
                    params["cursor"] = cursor
                resp = client.get(f"{self.base}/api/v1/links", params=params)
                resp.raise_for_status()
                batch = resp.json().get("response", [])
                if not batch:
                    break
                # Nur neue Einträge übernehmen; bringt ein Batch keine neuen ids,
                # macht die Paginierung keinen Fortschritt -> abbrechen.
                fresh = [it for it in batch if it.get("id") not in seen_ids]
                if not fresh:
                    break
                out.extend(fresh)
                seen_ids.update(it.get("id") for it in fresh)
                last_id = batch[-1].get("id")
                if last_id is None or last_id == cursor:
                    break
                cursor = last_id
        return out

    def create_link(
        self,
        url: str,
        tags: list[str] | None = None,
        note: str = "",
        collection: str = "",
    ) -> dict:
        """Ein Bookmark in Linkwarden anlegen (für die Capture-Übergabe).

        Feldnamen/Endpoint sind Linkwarden-versionsabhängig — hier ggf.
        anpassen.
        """
        import httpx

        headers = {"Authorization": f"Bearer {self.token}"}
        body: dict = {"url": url}
        if note:
            body["description"] = note
        if tags:
            body["tags"] = [{"name": t} for t in tags]
        if collection:
            body["collection"] = {"name": collection}

        with httpx.Client(timeout=self.cfg.http_timeout, headers=headers) as client:
            resp = client.post(f"{self.base}/api/v1/links", json=body)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def map_item(item: dict) -> dict:
        """Linkwarden-Eintrag auf unsere Felder reduzieren."""
        return {
            "url": item.get("url") or "",
            "title": item.get("name") or item.get("url") or "",
            "tags": [t.get("name") for t in item.get("tags", []) if t.get("name")],
            "note": item.get("description") or "",
            "collection": (item.get("collection") or {}).get("name", ""),
            # Manche Versionen liefern den Lesetext direkt mit.
            "text": item.get("textContent") or "",
            "added_at": item.get("createdAt") or "",
        }


def sync_from_linkwarden(cfg: Config, ingestor: Ingestor | None = None) -> int:
    """Links aus Linkwarden übernehmen und ihre Inhalte indexieren.

    ``ingestor`` kann übergeben werden, um den bereits geladenen Embedder
    wiederzuverwenden (z. B. im Watcher) statt das Modell neu zu laden.
    """
    lw = Linkwarden(cfg)
    if not lw.available():
        logger.error("linkwarden_not_configured")
        return 0

    ing = ingestor or Ingestor(cfg)  # teilt Embedder + documents-Tabelle
    links_table = store.ensure_links(ing.db)
    # Bestehende Liveness-Felder bewahren — ein Sync darf den von check_links()
    # geschriebenen Status nicht verlieren (Invariante aus CLAUDE.md).
    existing = store.links_by_url(links_table)

    items = lw.fetch_links()
    count = 0
    for raw in items:
        item = Linkwarden.map_item(raw)
        url = item["url"]
        if not url:
            continue

        # Lesetext: bevorzugt aus Linkwarden, sonst selbst abrufen.
        text = item["text"]
        if not text.strip():
            res = web.fetch(url, cfg)
            if res.ok and res.html:
                text, _ = extract.html_to_text(res.html)

        content_hash = extract.sha256_text(text) if text.strip() else ""
        if text.strip():
            ing.ingest_text(
                source_type="link",
                uri=url,
                title=item["title"],
                source=url,
                url=url,
                collection=item["collection"],
                tags=item["tags"],
                text=text,
                content_hash=content_hash,
            )

        prev = existing.get(url, {})
        store.upsert_link(
            links_table,
            {
                "id": extract.sha256_text(url)[:16],
                "url": url,
                # Metadaten aus Linkwarden aktualisieren …
                "title": item["title"],
                "tags": item["tags"],
                "note": item["note"],
                "added_at": item["added_at"],
                "content_hash": content_hash,
                # … Liveness-Felder aus dem bestehenden Datensatz übernehmen
                # (neue Links bleiben „unchecked").
                "last_checked": prev.get("last_checked", ""),
                "status": prev.get("status", "unchecked"),
                "http_status": prev.get("http_status", 0),
                "final_url": prev.get("final_url", ""),
                "last_ok_at": prev.get("last_ok_at", ""),
            },
        )
        count += 1

    logger.info("linkwarden_synced", count=count)
    return count


def _classify(res: web.FetchResult) -> str:
    if res.ok:
        return "ok"
    if res.error == "timeout":
        return "timeout"
    if res.status is not None:
        return "broken"  # 4xx/5xx
    return "error"  # DNS/TLS/Verbindung


def check_links(cfg: Config) -> dict[str, int]:
    """Erreichbarkeit aller Links prüfen und Status aktualisieren (Link-Rot)."""
    db = store.connect(cfg)
    links_table = store.ensure_links(db)
    rows = store.all_links(links_table)

    summary: dict[str, int] = {}
    for row in rows:
        url = row["url"]
        res = web.fetch(url, cfg, method="GET")
        status = _classify(res)
        summary[status] = summary.get(status, 0) + 1

        record = dict(row)
        record["last_checked"] = _now()
        record["http_status"] = res.status or 0
        record["final_url"] = res.final_url
        record["status"] = status
        if res.ok:
            record["last_ok_at"] = _now()
        store.upsert_link(links_table, record)

    logger.info("links_checked", total=len(rows), **summary)
    return summary
