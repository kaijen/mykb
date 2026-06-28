"""Tests für ``mykb.store`` (LanceDB-Zugriff).

Randbedingungen (siehe CLAUDE.md / conftest):
- Kein Import von ``mykb.server``/``server.server`` (braucht ``mcp``).
- Kein echter Embedder/torch — ausschließlich Dummy-Vektoren kleiner Dimension
  (``DUMMY_DIM``) über die Fixtures ``docs_table``/``make_doc``.
- Alle Pfade liegen unter ``tmp_path`` (via ``cfg``-Fixture).

Hinweis zu ``set_collection``: ``table.update`` ändert die Tabellenversion;
LanceDB-Handles sind versionsgebunden. Zur Prüfung wird die Tabelle daher
über ``store.connect``/``open_table`` FRISCH geöffnet.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mykb import schema, store
from mykb.config import DOCS_TABLE, LINKS_TABLE

from .conftest import DUMMY_DIM


def _vec(seed: float) -> list[float]:
    """Deterministischer Dummy-Vektor der Dimension ``DUMMY_DIM``."""
    return [seed, seed, seed, seed][:DUMMY_DIM] + [0.0] * max(0, DUMMY_DIM - 4)


def _add_docs(table, make_doc, specs: list[dict]) -> None:
    """Mehrere Records bequem hinzufügen."""
    table.add([make_doc(**spec) for spec in specs])


# --- ensure_documents / ensure_links -----------------------------------------

def test_ensure_documents_creates_and_is_idempotent(cfg):
    db = store.connect(cfg)
    assert DOCS_TABLE not in db.table_names()
    table = store.ensure_documents(db, DUMMY_DIM)
    assert DOCS_TABLE in db.table_names()
    assert table.count_rows() == 0
    # Zweiter Aufruf legt nicht neu an, sondern öffnet die bestehende Tabelle.
    again = store.ensure_documents(db, DUMMY_DIM)
    assert again.count_rows() == 0
    # Schema enthält ein Vektorfeld der erwarteten Dimension.
    names = [f.name for f in table.schema]
    assert "vector" in names
    assert "uri" in names


def test_ensure_links_creates_and_is_idempotent(cfg):
    db = store.connect(cfg)
    assert LINKS_TABLE not in db.table_names()
    table = store.ensure_links(db)
    assert LINKS_TABLE in db.table_names()
    again = store.ensure_links(db)
    assert again.count_rows() == 0
    names = [f.name for f in table.schema]
    assert "url" in names
    assert "status" in names


# --- existing_hash -----------------------------------------------------------

def test_existing_hash_found_and_missing(docs_table, make_doc):
    _, table = docs_table
    table.add([make_doc(uri="doc://a", content_hash="hash-a")])
    assert store.existing_hash(table, "doc://a") == "hash-a"
    assert store.existing_hash(table, "doc://missing") is None


# --- upsert_by_uri -----------------------------------------------------------

def test_upsert_by_uri_replaces_old_chunks(docs_table, make_doc):
    _, table = docs_table
    # Erst zwei Chunks der Quelle.
    _add_docs(
        table,
        make_doc,
        [
            {"uri": "doc://a", "chunk_index": 0, "content": "alt-0"},
            {"uri": "doc://a", "chunk_index": 1, "content": "alt-1"},
        ],
    )
    # Andere Quelle bleibt unberührt.
    table.add([make_doc(uri="doc://b", content="b-0")])

    new = [make_doc(uri="doc://a", chunk_index=0, content="neu-0")]
    store.upsert_by_uri(table, "doc://a", new)

    a_rows = (
        table.search().where("uri = 'doc://a'").select(["content"]).to_list()
    )
    assert [r["content"] for r in a_rows] == ["neu-0"]
    # doc://b unverändert vorhanden.
    assert store.existing_hash(table, "doc://b") == "deadbeef"


def test_upsert_by_uri_empty_records_only_deletes(docs_table, make_doc):
    _, table = docs_table
    table.add([make_doc(uri="doc://a")])
    store.upsert_by_uri(table, "doc://a", [])
    assert store.existing_hash(table, "doc://a") is None
    assert table.count_rows() == 0


# --- context_rows ------------------------------------------------------------

def test_context_rows_range_order_and_no_vector(docs_table, make_doc):
    _, table = docs_table
    # Absichtlich unsortiert eingefügt.
    _add_docs(
        table,
        make_doc,
        [
            {"uri": "doc://a", "chunk_index": 3},
            {"uri": "doc://a", "chunk_index": 1},
            {"uri": "doc://a", "chunk_index": 0},
            {"uri": "doc://a", "chunk_index": 2},
            {"uri": "doc://other", "chunk_index": 0},
        ],
    )
    rows = store.context_rows(table, "doc://a", 1, 3)
    assert [r["chunk_index"] for r in rows] == [1, 2, 3]
    # Nur DOC_FIELDS, kein Vektor.
    assert "vector" not in rows[0]
    assert set(rows[0].keys()) <= set(schema.DOC_FIELDS)


# --- search ------------------------------------------------------------------

def test_search_returns_results_without_vector(docs_table, make_doc):
    _, table = docs_table
    _add_docs(
        table,
        make_doc,
        [
            {"uri": "doc://a", "vector": _vec(0.1)},
            {"uri": "doc://b", "vector": _vec(0.9)},
        ],
    )
    rows = store.search(table, _vec(0.1), top_k=10)
    assert rows
    assert "vector" not in rows[0]
    uris = {r["uri"] for r in rows}
    assert {"doc://a", "doc://b"} <= uris


def test_search_with_where_filter(docs_table, make_doc):
    _, table = docs_table
    _add_docs(
        table,
        make_doc,
        [
            {"uri": "doc://a", "source_type": "document", "vector": _vec(0.1)},
            {"uri": "web://b", "source_type": "web", "vector": _vec(0.2)},
        ],
    )
    rows = store.search(
        table, _vec(0.1), top_k=10, where="source_type = 'web'"
    )
    assert rows
    assert {r["source_type"] for r in rows} == {"web"}
    assert {r["uri"] for r in rows} == {"web://b"}


# --- vector_for_uri ----------------------------------------------------------

def test_vector_for_uri(docs_table, make_doc):
    _, table = docs_table
    table.add([make_doc(uri="doc://a", chunk_index=0, vector=_vec(0.5))])
    vec = store.vector_for_uri(table, "doc://a")
    assert vec is not None
    assert list(vec) == _vec(0.5)
    assert store.vector_for_uri(table, "doc://missing") is None


# --- related -----------------------------------------------------------------

def test_related_excludes_uri_and_dedupes(docs_table, make_doc):
    _, table = docs_table
    # Quelle a (zwei Chunks) plus weitere Quellen.
    _add_docs(
        table,
        make_doc,
        [
            {"uri": "doc://a", "chunk_index": 0, "vector": _vec(0.10)},
            {"uri": "doc://a", "chunk_index": 1, "vector": _vec(0.11)},
            {"uri": "doc://b", "chunk_index": 0, "vector": _vec(0.12)},
            {"uri": "doc://b", "chunk_index": 1, "vector": _vec(0.13)},
            {"uri": "doc://c", "chunk_index": 0, "vector": _vec(0.50)},
        ],
    )
    rows = store.related(table, "doc://a", top_k=10)
    uris = [r["uri"] for r in rows]
    # Quelle selbst ausgeschlossen.
    assert "doc://a" not in uris
    # Je uri nur einmal (b erscheint trotz zweier Chunks nur einmal).
    assert len(uris) == len(set(uris))
    assert "doc://b" in uris


def test_related_missing_uri_returns_empty(docs_table, make_doc):
    _, table = docs_table
    table.add([make_doc(uri="doc://a")])
    assert store.related(table, "doc://missing", top_k=5) == []


# --- counts ------------------------------------------------------------------

def test_counts_distinct_sources_and_total_chunks(docs_table, make_doc):
    _, table = docs_table
    _add_docs(
        table,
        make_doc,
        [
            {"uri": "doc://a", "chunk_index": 0, "source_type": "document"},
            {"uri": "doc://a", "chunk_index": 1, "source_type": "document"},
            {"uri": "note://n", "chunk_index": 0, "source_type": "note"},
            {"uri": "web://w", "chunk_index": 0, "source_type": "web"},
            {"uri": "web://w", "chunk_index": 1, "source_type": "web"},
        ],
    )
    c = store.counts(table)
    assert c["total_chunks"] == 5
    # distinct Quellen (uri): a, n, w
    assert c["total_sources"] == 3
    assert c["sources_by_type"] == {"document": 1, "note": 1, "web": 1}


# --- recent_items ------------------------------------------------------------

def test_recent_items_newest_first_unique_uri(docs_table, make_doc):
    _, table = docs_table
    base = datetime(2026, 1, 1, tzinfo=UTC)
    _add_docs(
        table,
        make_doc,
        [
            {
                "uri": "doc://old",
                "indexed_at": base.replace(day=1).isoformat(),
            },
            {
                "uri": "doc://new",
                "chunk_index": 0,
                "indexed_at": base.replace(day=3).isoformat(),
            },
            {
                "uri": "doc://new",
                "chunk_index": 1,
                "indexed_at": base.replace(day=3).isoformat(),
            },
            {
                "uri": "doc://mid",
                "indexed_at": base.replace(day=2).isoformat(),
            },
        ],
    )
    rows = store.recent_items(table, limit=10)
    uris = [r["uri"] for r in rows]
    # Neueste zuerst, jede uri nur einmal.
    assert uris == ["doc://new", "doc://mid", "doc://old"]
    assert "vector" not in rows[0]


def test_recent_items_limit(docs_table, make_doc):
    _, table = docs_table
    base = datetime(2026, 1, 1, tzinfo=UTC)
    _add_docs(
        table,
        make_doc,
        [
            {"uri": f"doc://{i}", "indexed_at": base.replace(day=i).isoformat()}
            for i in range(1, 6)
        ],
    )
    rows = store.recent_items(table, limit=2)
    assert [r["uri"] for r in rows] == ["doc://5", "doc://4"]


def test_recent_items_source_type_filter(docs_table, make_doc):
    _, table = docs_table
    base = datetime(2026, 1, 1, tzinfo=UTC)
    _add_docs(
        table,
        make_doc,
        [
            {
                "uri": "doc://d",
                "source_type": "document",
                "indexed_at": base.replace(day=1).isoformat(),
            },
            {
                "uri": "note://n",
                "source_type": "note",
                "indexed_at": base.replace(day=2).isoformat(),
            },
        ],
    )
    rows = store.recent_items(table, limit=10, source_types=["note"])
    assert [r["uri"] for r in rows] == ["note://n"]


# --- document_text -----------------------------------------------------------

def test_document_text_joins_in_chunk_order(docs_table, make_doc):
    _, table = docs_table
    _add_docs(
        table,
        make_doc,
        [
            {"uri": "doc://a", "chunk_index": 2, "content": "drei"},
            {"uri": "doc://a", "chunk_index": 0, "content": "eins"},
            {"uri": "doc://a", "chunk_index": 1, "content": "zwei"},
            {"uri": "doc://other", "chunk_index": 0, "content": "fremd"},
        ],
    )
    assert store.document_text(table, "doc://a") == "eins\nzwei\ndrei"


def test_document_text_missing_uri_empty(docs_table, make_doc):
    _, table = docs_table
    table.add([make_doc(uri="doc://a")])
    assert store.document_text(table, "doc://missing") == ""


# --- set_collection ----------------------------------------------------------

def test_set_collection_updates_all_chunks(docs_table, make_doc, cfg):
    _, table = docs_table
    _add_docs(
        table,
        make_doc,
        [
            {"uri": "doc://a", "chunk_index": 0, "collection": ""},
            {"uri": "doc://a", "chunk_index": 1, "collection": ""},
            {"uri": "doc://b", "chunk_index": 0, "collection": ""},
        ],
    )
    store.set_collection(table, "doc://a", "Thema-X")

    # Handles sind versionsgebunden: frisch öffnen für die Prüfung.
    db2 = store.connect(cfg)
    fresh = db2.open_table(DOCS_TABLE)
    a_rows = (
        fresh.search()
        .where("uri = 'doc://a'")
        .select(["collection", "chunk_index"])
        .to_list()
    )
    assert {r["collection"] for r in a_rows} == {"Thema-X"}
    assert len(a_rows) == 2
    # Andere Quelle bleibt leer.
    b_rows = (
        fresh.search().where("uri = 'doc://b'").select(["collection"]).to_list()
    )
    assert {r["collection"] for r in b_rows} == {""}


# --- links: upsert_link / links_by_url / all_links ---------------------------

def _make_link(**overrides) -> dict:
    record = {
        "id": "lnk-1",
        "url": "https://example.org/a",
        "title": "Beispiel",
        "tags": [],
        "note": "",
        "added_at": datetime.now(UTC).isoformat(),
        "last_checked": "",
        "status": "unchecked",
        "http_status": 0,
        "final_url": "",
        "last_ok_at": "",
        "content_hash": "",
    }
    record.update(overrides)
    return record


def test_upsert_link_replaces_by_id(cfg):
    db = store.connect(cfg)
    table = store.ensure_links(db)
    store.upsert_link(table, _make_link(id="lnk-1", status="unchecked"))
    store.upsert_link(table, _make_link(id="lnk-1", status="ok"))
    rows = store.all_links(table)
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert "vector" not in rows[0]
    assert set(rows[0].keys()) <= set(schema.LINK_FIELDS)


def test_links_by_url_maps_url_to_record(cfg):
    db = store.connect(cfg)
    table = store.ensure_links(db)
    store.upsert_link(
        table, _make_link(id="lnk-1", url="https://a.example", status="ok")
    )
    store.upsert_link(
        table,
        _make_link(id="lnk-2", url="https://b.example", status="broken"),
    )
    mapping = store.links_by_url(table)
    assert set(mapping) == {"https://a.example", "https://b.example"}
    assert mapping["https://a.example"]["status"] == "ok"
    assert mapping["https://b.example"]["status"] == "broken"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
