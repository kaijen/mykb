"""Regression: ``sync_from_linkwarden`` darf den Link-Rot-Status bewahren.

Sichert das HIGH-Finding aus dem Review ab: ein erneuter Sync darf die von
``check_links`` geschriebenen Liveness-Felder nicht auf ``unchecked``
zurücksetzen, aber Metadaten sehr wohl aktualisieren.
"""
from __future__ import annotations


class _FakeIngestor:
    """Ersetzt den echten Ingestor (kein Embedder) — nutzt nur ``.db``."""

    def __init__(self, db):
        self.db = db

    def ingest_text(self, **kwargs) -> int:  # no-op
        return 0


def test_sync_preserves_liveness_fields(cfg, monkeypatch):
    from mykb import extract, links, store

    db = store.connect(cfg)
    table = store.ensure_links(db)
    url = "https://example.org/a"
    lid = extract.sha256_text(url)[:16]

    # Bereits geprüfter Link (Status ok).
    store.upsert_link(
        table,
        {
            "id": lid,
            "url": url,
            "title": "alt",
            "tags": [],
            "note": "",
            "added_at": "",
            "last_checked": "2026-06-28T00:00:00+00:00",
            "status": "ok",
            "http_status": 200,
            "final_url": url,
            "last_ok_at": "2026-06-28T00:00:00+00:00",
            "content_hash": "x",
        },
    )

    monkeypatch.setattr(links.Linkwarden, "available", lambda self: True)
    monkeypatch.setattr(
        links.Linkwarden,
        "fetch_links",
        lambda self: [
            {
                "url": url,
                "name": "neuer Titel",
                "tags": [],
                "description": "",
                "collection": {},
                "textContent": "Inhalt",
                "createdAt": "",
            }
        ],
    )

    links.sync_from_linkwarden(cfg, ingestor=_FakeIngestor(db))

    row = store.links_by_url(store.ensure_links(store.connect(cfg)))[url]
    # Liveness bewahrt …
    assert row["status"] == "ok"
    assert row["http_status"] == 200
    assert row["last_ok_at"] == "2026-06-28T00:00:00+00:00"
    # … Metadaten aktualisiert.
    assert row["title"] == "neuer Titel"
