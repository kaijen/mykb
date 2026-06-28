"""Tests für ``mykb.status`` (Betriebsstatus + Zustands-Persistenz).

Randbedingungen (siehe CLAUDE.md / conftest):
- Kein Import von ``mykb.server``/``server.server`` (braucht ``mcp``).
- Kein echter Embedder/torch — nur Dummy-Vektoren kleiner Dimension
  (``DUMMY_DIM``) über die Fixtures ``docs_table``/``make_doc``.
- Kein Netzwerk — ``collect_status`` liest nur lokal (LanceDB-Dateien, Queue,
  State-Datei).
- Alle Pfade liegen unter ``tmp_path`` (via ``cfg``-Fixture).
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mykb import queue, status, store
from mykb.config import DOCS_TABLE, LINKS_TABLE


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


# --- write_state / read_state ------------------------------------------------

def test_read_state_missing_returns_empty(cfg):
    # Keine State-Datei vorhanden -> leeres Dict, kein Crash.
    assert status.read_state(cfg) == {}


def test_write_state_then_read_roundtrip(cfg):
    status.write_state(cfg, last_process="2026-06-28T10:00:00+00:00")
    assert status.read_state(cfg) == {
        "last_process": "2026-06-28T10:00:00+00:00"
    }


def test_write_state_merges_existing_fields(cfg):
    status.write_state(cfg, last_process="p1")
    status.write_state(cfg, last_sync="s1")
    data = status.read_state(cfg)
    # Beide Felder bleiben erhalten (Merge, kein Überschreiben der ganzen Datei).
    assert data == {"last_process": "p1", "last_sync": "s1"}


def test_write_state_overwrites_same_key(cfg):
    status.write_state(cfg, last_process="alt")
    status.write_state(cfg, last_process="neu")
    assert status.read_state(cfg)["last_process"] == "neu"


def test_write_state_creates_parent_dir(tmp_path):
    from mykb.config import Config

    # state_dir existiert absichtlich noch nicht.
    missing = tmp_path / "fresh-state"
    cfg = Config(state_dir=str(missing), queue_dir=str(missing / "queue"))
    status.write_state(cfg, last_process="x")
    assert (missing / "last_run.json").is_file()
    assert status.read_state(cfg) == {"last_process": "x"}


def test_write_state_atomic_no_tmp_leftover(cfg):
    status.write_state(cfg, last_process="x")
    state_dir = Path(cfg.state_dir)
    # Atomar via temp + replace: keine .tmp-Reste.
    assert not list(state_dir.glob("*.tmp"))
    assert (state_dir / "last_run.json").is_file()


def test_read_state_corrupt_returns_empty(cfg):
    path = Path(cfg.state_dir) / "last_run.json"
    path.write_text("{ kein valides json", encoding="utf-8")
    # Defensive: kaputte Datei -> leeres Dict statt Exception.
    assert status.read_state(cfg) == {}


# --- collect_status: ohne Tabellen / leerer Zustand --------------------------

def test_collect_status_without_tables_is_robust(cfg):
    # db_path existiert (LanceDB-Verzeichnis leer), aber keine Tabellen.
    out = status.collect_status(cfg)
    assert "generated_at" in out
    # Keine documents/links-Schlüssel, da Tabellen fehlen, aber kein Crash.
    assert "documents" not in out
    assert "links" not in out
    assert out["queue_pending"] == 0
    assert out["last_process"] is None
    assert out["last_sync"] is None
    # Tabellen fehlen ist kein Fehler -> kein store_error.
    assert "store_error" not in out


# --- collect_status: documents-Counts ----------------------------------------

def test_collect_status_documents_counts(docs_table, make_doc, cfg):
    _, table = docs_table
    table.add(
        [
            make_doc(uri="doc://a", chunk_index=0, source_type="document"),
            make_doc(uri="doc://a", chunk_index=1, source_type="document"),
            make_doc(uri="note://n", chunk_index=0, source_type="note"),
        ]
    )
    out = status.collect_status(cfg)
    docs = out["documents"]
    assert docs["total_chunks"] == 3
    assert docs["total_sources"] == 2
    assert docs["sources_by_type"] == {"document": 1, "note": 1}


# --- collect_status: links by_status -----------------------------------------

def test_collect_status_links_by_status(cfg):
    db = store.connect(cfg)
    links_table = store.ensure_links(db)
    store.upsert_link(links_table, _make_link(id="l1", url="u1", status="ok"))
    store.upsert_link(links_table, _make_link(id="l2", url="u2", status="ok"))
    store.upsert_link(
        links_table, _make_link(id="l3", url="u3", status="broken")
    )

    out = status.collect_status(cfg)
    assert out["links"]["total"] == 3
    assert out["links"]["by_status"] == {"ok": 2, "broken": 1}


def test_collect_status_links_empty_table(cfg):
    db = store.connect(cfg)
    store.ensure_links(db)
    out = status.collect_status(cfg)
    assert out["links"] == {"total": 0, "by_status": {}}


# --- collect_status: queue_pending -------------------------------------------

def test_collect_status_queue_pending(cfg):
    queue.enqueue_url(cfg, "https://example.org/x")
    queue.enqueue_file(cfg, "a.md", b"inhalt", kind="note")
    out = status.collect_status(cfg)
    assert out["queue_pending"] == 2


# --- collect_status: last_process / last_sync aus State ----------------------

def test_collect_status_reads_state_fields(cfg):
    status.write_state(cfg, last_process="2026-06-28T09:00:00+00:00")
    status.write_state(cfg, last_sync="2026-06-28T09:05:00+00:00")
    out = status.collect_status(cfg)
    assert out["last_process"] == "2026-06-28T09:00:00+00:00"
    assert out["last_sync"] == "2026-06-28T09:05:00+00:00"


# --- collect_status: Store-Fehler wird abgefangen ----------------------------

def test_collect_status_store_error_is_caught(cfg, monkeypatch):
    def _boom(_cfg):
        raise RuntimeError("db kaputt")

    monkeypatch.setattr(store, "connect", _boom)
    out = status.collect_status(cfg)
    # Fehler landet als gekürzter store_error, restliche Felder bleiben gefüllt.
    assert "store_error" in out
    assert "db kaputt" in out["store_error"]
    assert out["queue_pending"] == 0
    assert out["last_process"] is None


# --- Zusammenspiel: voller Status --------------------------------------------

def test_collect_status_full(docs_table, make_doc, cfg):
    _, table = docs_table
    table.add([make_doc(uri="doc://a", source_type="document")])

    db = store.connect(cfg)
    links_table = store.ensure_links(db)
    store.upsert_link(links_table, _make_link(id="l1", url="u1", status="ok"))

    queue.enqueue_url(cfg, "https://example.org/x")
    status.write_state(cfg, last_process="p", last_sync="s")

    out = status.collect_status(cfg)
    assert out["documents"]["total_sources"] == 1
    assert out["links"]["by_status"] == {"ok": 1}
    assert out["queue_pending"] == 1
    assert out["last_process"] == "p"
    assert out["last_sync"] == "s"
    # generated_at ist ein ISO-Zeitstempel (parsebar).
    assert datetime.fromisoformat(out["generated_at"])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
