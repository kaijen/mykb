"""Tests für ``mykb.collections`` (Auto-Sammlungen via Cosinus-Clustering).

Randbedingungen (siehe CLAUDE.md / conftest):
- Kein Import von ``mykb.server``/``server.server`` (braucht ``mcp``).
- Kein echter Embedder/torch — ausschließlich Dummy-Vektoren kleiner Dimension
  (``DUMMY_DIM``) über die Fixtures ``docs_table``/``make_doc``.
- Alle Pfade liegen unter ``tmp_path`` (via ``cfg``-Fixture).

Hinweis zu ``apply``: ``table.update`` ändert die Tabellenversion; LanceDB-
Handles sind versionsgebunden. Zur Prüfung wird die Tabelle daher über
``store.connect``/``open_table`` FRISCH geöffnet.
"""
from __future__ import annotations

import pytest

from mykb import collections, store
from mykb.config import DOCS_TABLE

from .conftest import DUMMY_DIM


def _vec(*vals: float) -> list[float]:
    """Dummy-Vektor der Dimension ``DUMMY_DIM`` (rechts mit 0.0 aufgefüllt)."""
    out = list(vals)[:DUMMY_DIM]
    return out + [0.0] * (DUMMY_DIM - len(out))


def _add_docs(table, make_doc, specs: list[dict]) -> None:
    table.add([make_doc(**spec) for spec in specs])


# --- _greedy_clusters --------------------------------------------------------

def test_greedy_clusters_two_groups():
    items = [
        {"vector": _vec(1.0, 0.0)},
        {"vector": _vec(0.99, 0.01)},
        {"vector": _vec(0.0, 1.0)},
        {"vector": _vec(0.01, 0.99)},
    ]
    clusters = collections._greedy_clusters(items, threshold=0.9)
    # Zwei orthogonale Richtungen → zwei Cluster mit je zwei Mitgliedern.
    assert len(clusters) == 2
    assert sorted(len(c) for c in clusters) == [2, 2]
    # Greedy: erstes Element ankert Cluster 0, das nahe Element folgt.
    assert clusters[0] == [0, 1]
    assert clusters[1] == [2, 3]


def test_greedy_clusters_handles_zero_vector():
    # Null-Vektor darf nicht durch Division crashen (norm-Schutz im Code).
    items = [{"vector": _vec(0.0, 0.0)}, {"vector": _vec(1.0, 0.0)}]
    clusters = collections._greedy_clusters(items, threshold=0.5)
    # Null-Vektor hat Cosinus 0 zu allem → eigenes Cluster.
    assert len(clusters) == 2


# --- _label ------------------------------------------------------------------

def test_label_uses_most_common_tag():
    items = [
        {"tags": ["infosec", "iso"], "title": "Doc A"},
        {"tags": ["infosec"], "title": "Doc B"},
    ]
    assert collections._label([0, 1], items) == "infosec"


def test_label_falls_back_to_first_title_word():
    items = [{"tags": [], "title": "ISO 27001 Annex"}]
    assert collections._label([0], items) == "ISO"


def test_label_fallback_when_no_tags_and_no_title():
    items = [{"tags": [], "title": ""}]
    assert collections._label([0], items) == "Sammlung"


# --- suggest -----------------------------------------------------------------

def test_suggest_empty_table_returns_empty(cfg):
    # Tabelle existiert noch nicht.
    assert collections.suggest(cfg) == []


def test_suggest_two_clusters(docs_table, make_doc, cfg):
    _, table = docs_table
    _add_docs(
        table,
        make_doc,
        [
            {"uri": "doc://a", "title": "Alpha", "tags": ["infosec"],
             "vector": _vec(1.0, 0.0)},
            {"uri": "doc://b", "title": "Beta", "tags": ["infosec"],
             "vector": _vec(0.98, 0.02)},
            {"uri": "doc://c", "title": "Gamma", "tags": ["recht"],
             "vector": _vec(0.0, 1.0)},
            {"uri": "doc://d", "title": "Delta", "tags": ["recht"],
             "vector": _vec(0.02, 0.98)},
        ],
    )
    out = collections.suggest(cfg, threshold=0.9)
    assert len(out) == 2
    # Nach Größe sortiert (beide gleich groß → beide zwei uris).
    assert all(len(c["uris"]) == 2 for c in out)
    # Labels aus dem häufigsten Tag je Cluster.
    labels = {c["label"] for c in out}
    assert labels == {"infosec", "recht"}
    # Cluster-uris korrekt zugeordnet.
    by_label = {c["label"]: set(c["uris"]) for c in out}
    assert by_label["infosec"] == {"doc://a", "doc://b"}
    assert by_label["recht"] == {"doc://c", "doc://d"}


def test_suggest_sorted_by_size(docs_table, make_doc, cfg):
    _, table = docs_table
    _add_docs(
        table,
        make_doc,
        [
            # Großes Cluster (drei nahe Vektoren).
            {"uri": "doc://a", "vector": _vec(1.0, 0.0)},
            {"uri": "doc://b", "vector": _vec(0.99, 0.01)},
            {"uri": "doc://c", "vector": _vec(0.98, 0.02)},
            # Einzelnes, orthogonales Cluster.
            {"uri": "doc://z", "vector": _vec(0.0, 1.0)},
        ],
    )
    out = collections.suggest(cfg, threshold=0.9)
    assert len(out) == 2
    # Größtes Cluster zuerst.
    assert len(out[0]["uris"]) == 3
    assert len(out[1]["uris"]) == 1


def test_suggest_excludes_link_snapshots(docs_table, make_doc, cfg):
    _, table = docs_table
    _add_docs(
        table,
        make_doc,
        [
            {"uri": "doc://a", "source_type": "document",
             "vector": _vec(1.0, 0.0)},
            # Link-Snapshot: muss aus document_vectors ausgeschlossen sein.
            {"uri": "link://x", "source_type": "link",
             "vector": _vec(1.0, 0.0)},
        ],
    )
    out = collections.suggest(cfg, threshold=0.9)
    all_uris = {u for c in out for u in c["uris"]}
    assert "link://x" not in all_uris
    assert all_uris == {"doc://a"}


def test_suggest_only_first_chunk_per_source(docs_table, make_doc, cfg):
    _, table = docs_table
    _add_docs(
        table,
        make_doc,
        [
            {"uri": "doc://a", "chunk_index": 0, "vector": _vec(1.0, 0.0)},
            # Folge-Chunk (chunk_index != 0) zählt nicht als eigene Quelle.
            {"uri": "doc://a", "chunk_index": 1, "vector": _vec(0.0, 1.0)},
        ],
    )
    out = collections.suggest(cfg, threshold=0.9)
    all_uris = [u for c in out for u in c["uris"]]
    assert all_uris == ["doc://a"]


# --- apply -------------------------------------------------------------------

def test_apply_sets_collection(docs_table, make_doc, cfg):
    _, table = docs_table
    _add_docs(
        table,
        make_doc,
        [
            {"uri": "doc://a", "chunk_index": 0, "collection": "",
             "vector": _vec(1.0, 0.0)},
            {"uri": "doc://a", "chunk_index": 1, "collection": "",
             "vector": _vec(1.0, 0.0)},
            {"uri": "doc://b", "chunk_index": 0, "collection": "",
             "vector": _vec(0.99, 0.01)},
        ],
    )
    suggestions = [{"label": "Thema-X", "uris": ["doc://a", "doc://b"]}]
    count = collections.apply(cfg, suggestions)
    # apply zählt je uri (nicht je Chunk).
    assert count == 2

    # Handles sind versionsgebunden: frisch öffnen für die Prüfung.
    fresh = store.connect(cfg).open_table(DOCS_TABLE)
    rows = (
        fresh.search()
        .where("uri = 'doc://a' OR uri = 'doc://b'")
        .select(["uri", "collection"])
        .to_list()
    )
    # Alle Chunks beider Quellen tragen jetzt die Sammlung.
    assert {r["collection"] for r in rows} == {"Thema-X"}
    assert len(rows) == 3


def test_suggest_then_apply_roundtrip(docs_table, make_doc, cfg):
    _, table = docs_table
    _add_docs(
        table,
        make_doc,
        [
            {"uri": "doc://a", "tags": ["infosec"], "vector": _vec(1.0, 0.0)},
            {"uri": "doc://b", "tags": ["infosec"], "vector": _vec(0.99, 0.01)},
        ],
    )
    suggestions = collections.suggest(cfg, threshold=0.9)
    assert len(suggestions) == 1
    assert suggestions[0]["label"] == "infosec"

    collections.apply(cfg, suggestions)

    fresh = store.connect(cfg).open_table(DOCS_TABLE)
    rows = fresh.search().select(["collection"]).to_list()
    assert {r["collection"] for r in rows} == {"infosec"}


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
