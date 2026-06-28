"""Gemeinsame Test-Fixtures.

Randbedingungen (siehe CLAUDE.md / Testvorgaben):
- KEIN Import von ``mykb.server`` / ``server.server`` (braucht ``mcp``).
- NIEMALS einen echten ``Embedder`` instanziieren oder torch /
  sentence_transformers importieren. Für LanceDB werden Dummy-Vektoren kleiner
  Dimension benutzt (Standard: 4).
- Netzwerk (Linkwarden / httpx / Ollama) wird in den Tests gemonkeypatcht.
- Alle Pfade liegen unter ``tmp_path``.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mykb.config import Config

# Kleine Dimension für Dummy-Vektoren — vermeidet jeden echten Embedder.
DUMMY_DIM = 4


@pytest.fixture
def cfg(tmp_path) -> Config:
    """Config mit allen relevanten Pfaden unter ``tmp_path``.

    Verzeichnisse werden angelegt, damit Code, der ihre Existenz erwartet,
    nicht stolpert. ``db_path`` bleibt absichtlich uneröffnet (LanceDB legt es
    bei Bedarf selbst an).
    """
    db_path = tmp_path / "lance"
    state_dir = tmp_path / "state"
    queue_dir = state_dir / "queue"
    docs_path = tmp_path / "documents"
    notes_path = tmp_path / "notes"
    for p in (state_dir, queue_dir, docs_path, notes_path):
        p.mkdir(parents=True, exist_ok=True)

    return Config(
        db_path=str(db_path),
        docs_path=str(docs_path),
        notes_path=str(notes_path),
        state_dir=str(state_dir),
        queue_dir=str(queue_dir),
        device="cpu",
    )


@pytest.fixture
def docs_table(cfg):
    """Erstellt eine leere ``documents``-Tabelle kleiner Dimension.

    Gibt ``(db, table)`` zurück. Nutzt die echten Store-/Schema-Funktionen,
    damit die Felder exakt mit der Produktion übereinstimmen.
    """
    from mykb import store

    db = store.connect(cfg)
    table = store.ensure_documents(db, DUMMY_DIM)
    return db, table


@pytest.fixture
def make_doc():
    """Factory für ``documents``-Records mit allen Pflichtfeldern.

    Setzt sinnvolle Defaults inkl. ``summary`` und einem Dummy-Vektor der
    Dimension ``DUMMY_DIM``. Einzelne Felder lassen sich per kwargs überschreiben.
    """

    def _make(**overrides) -> dict:
        idx = overrides.get("chunk_index", 0)
        uri = overrides.get("uri", "doc://test")
        record = {
            "id": f"{uri}#{idx}",
            "source_type": "document",
            "collection": "",
            "tags": [],
            "title": "Test-Titel",
            "source": "test",
            "url": "",
            "content": "Beispielinhalt für den Test.",
            "summary": "",
            "uri": uri,
            "content_hash": "deadbeef",
            "chunk_index": idx,
            "n_chunks": 1,
            "pages": 0,
            "indexed_at": datetime.now(UTC).isoformat(),
            "vector": [0.0] * DUMMY_DIM,
        }
        record.update(overrides)
        # id konsistent zur evtl. überschriebenen uri/chunk_index halten,
        # sofern nicht explizit gesetzt.
        if "id" not in overrides:
            record["id"] = f"{record['uri']}#{record['chunk_index']}"
        return record

    return _make
