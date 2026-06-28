"""Tests für ``mykb.queue`` (durable Datei-Queue).

Randbedingungen siehe ``tests/conftest.py``: kein Embedder/Netzwerk, alle Pfade
unter ``tmp_path`` (via ``cfg``-Fixture). Linkwarden wird über Klassen-Methoden
gemonkeypatcht — ``drain`` instanziiert ``links.Linkwarden(cfg)`` selbst.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mykb import links, queue


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# --- enqueue ---------------------------------------------------------------


def test_enqueue_url_writes_json_record(cfg):
    qid = queue.enqueue_url(
        cfg, "https://example.org/a", tags=["x", "y"], note="hi", collection="c"
    )
    qd = Path(cfg.queue_dir)
    jpath = qd / f"{qid}.json"
    assert jpath.exists()
    rec = _read_json(jpath)
    assert rec["type"] == "url"
    assert rec["id"] == qid
    assert rec["url"] == "https://example.org/a"
    assert rec["tags"] == ["x", "y"]
    assert rec["note"] == "hi"
    assert rec["collection"] == "c"
    assert "received_at" in rec


def test_enqueue_url_defaults(cfg):
    qid = queue.enqueue_url(cfg, "https://example.org/b")
    rec = _read_json(Path(cfg.queue_dir) / f"{qid}.json")
    assert rec["tags"] == []
    assert rec["note"] == ""
    assert rec["collection"] == ""


def test_enqueue_url_atomic_no_tmp_left(cfg):
    queue.enqueue_url(cfg, "https://example.org/c")
    qd = Path(cfg.queue_dir)
    assert list(qd.glob("*.tmp")) == []


def test_enqueue_file_writes_json_and_bin(cfg):
    data = b"hello world"
    qid = queue.enqueue_file(cfg, "notiz.md", data, kind="note", collection="proj")
    qd = Path(cfg.queue_dir)
    jpath = qd / f"{qid}.json"
    bpath = qd / f"{qid}.bin"
    assert jpath.exists() and bpath.exists()
    assert bpath.read_bytes() == data
    rec = _read_json(jpath)
    assert rec["type"] == "file"
    assert rec["filename"] == "notiz.md"
    assert rec["kind"] == "note"
    assert rec["collection"] == "proj"
    assert rec["blob"] == bpath.name


def test_enqueue_file_kind_defaults_to_document(cfg):
    qid = queue.enqueue_file(cfg, "x.pdf", b"data", kind="weird")
    rec = _read_json(Path(cfg.queue_dir) / f"{qid}.json")
    assert rec["kind"] == "document"


def test_enqueue_file_atomic_no_tmp_left(cfg):
    queue.enqueue_file(cfg, "a.txt", b"data")
    qd = Path(cfg.queue_dir)
    assert list(qd.glob("*.tmp")) == []


# --- list_pending ----------------------------------------------------------


def test_list_pending_returns_records(cfg):
    queue.enqueue_url(cfg, "https://example.org/a")
    queue.enqueue_file(cfg, "a.txt", b"data")
    pending = queue.list_pending(cfg)
    assert len(pending) == 2
    types = {r["type"] for r in pending}
    assert types == {"url", "file"}


def test_list_pending_missing_dir(cfg, tmp_path):
    cfg.queue_dir = str(tmp_path / "does-not-exist")
    assert queue.list_pending(cfg) == []


def test_list_pending_ignores_broken_json(cfg):
    queue.enqueue_url(cfg, "https://example.org/a")
    (Path(cfg.queue_dir) / "broken.json").write_text("{ not json", encoding="utf-8")
    pending = queue.list_pending(cfg)
    assert len(pending) == 1
    assert pending[0]["type"] == "url"


# --- drain: file -----------------------------------------------------------


def test_drain_file_to_docs_inbox(cfg, monkeypatch):
    monkeypatch.setattr(links.Linkwarden, "available", lambda self: True)
    qid = queue.enqueue_file(cfg, "report.pdf", b"PDF", kind="document")
    n = queue.drain(cfg)
    assert n == 1
    target = Path(cfg.docs_path) / "report.pdf"
    assert target.read_bytes() == b"PDF"
    # Eintrag und Blob aufgeräumt.
    qd = Path(cfg.queue_dir)
    assert not (qd / f"{qid}.json").exists()
    assert not (qd / f"{qid}.bin").exists()


def test_drain_file_note_to_notes_inbox(cfg, monkeypatch):
    monkeypatch.setattr(links.Linkwarden, "available", lambda self: True)
    queue.enqueue_file(cfg, "gedanke.md", b"# Notiz", kind="note")
    queue.drain(cfg)
    assert (Path(cfg.notes_path) / "gedanke.md").read_bytes() == b"# Notiz"


def test_drain_file_with_collection_subdir(cfg, monkeypatch):
    monkeypatch.setattr(links.Linkwarden, "available", lambda self: True)
    queue.enqueue_file(cfg, "a.txt", b"data", collection="sub")
    queue.drain(cfg)
    assert (Path(cfg.docs_path) / "sub" / "a.txt").read_bytes() == b"data"


# --- drain: url ------------------------------------------------------------


def test_drain_url_to_linkwarden(cfg, monkeypatch):
    calls: list[dict] = []

    def fake_create_link(self, url, tags=None, note="", collection=""):
        calls.append(
            {"url": url, "tags": tags, "note": note, "collection": collection}
        )
        return {"ok": True}

    monkeypatch.setattr(links.Linkwarden, "available", lambda self: True)
    monkeypatch.setattr(links.Linkwarden, "create_link", fake_create_link)

    qid = queue.enqueue_url(
        cfg, "https://example.org/a", tags=["t"], note="n", collection="col"
    )
    n = queue.drain(cfg)
    assert n == 1
    assert calls == [
        {"url": "https://example.org/a", "tags": ["t"], "note": "n", "collection": "col"}
    ]
    assert not (Path(cfg.queue_dir) / f"{qid}.json").exists()


def test_drain_url_without_linkwarden_stays(cfg, monkeypatch):
    """Ohne erreichbares Linkwarden bleibt der URL-Eintrag für einen Retry."""
    called = []
    monkeypatch.setattr(links.Linkwarden, "available", lambda self: False)
    monkeypatch.setattr(
        links.Linkwarden,
        "create_link",
        lambda self, *a, **k: called.append(1),
    )
    qid = queue.enqueue_url(cfg, "https://example.org/a")
    n = queue.drain(cfg)
    assert n == 0
    assert called == []
    # Eintrag bleibt liegen.
    assert (Path(cfg.queue_dir) / f"{qid}.json").exists()


def test_drain_url_no_linkwarden_keeps_file_progress(cfg, monkeypatch):
    """Datei-Einträge werden auch dann übernommen, wenn Linkwarden fehlt."""
    monkeypatch.setattr(links.Linkwarden, "available", lambda self: False)
    url_id = queue.enqueue_url(cfg, "https://example.org/a")
    file_id = queue.enqueue_file(cfg, "a.txt", b"data")
    n = queue.drain(cfg)
    assert n == 1
    assert (Path(cfg.queue_dir) / f"{url_id}.json").exists()
    assert not (Path(cfg.queue_dir) / f"{file_id}.json").exists()
    assert (Path(cfg.docs_path) / "a.txt").read_bytes() == b"data"


# --- drain: robustness -----------------------------------------------------


def test_drain_missing_dir(cfg, tmp_path):
    cfg.queue_dir = str(tmp_path / "nope")
    assert queue.drain(cfg) == 0


def test_drain_ignores_broken_json(cfg, monkeypatch):
    monkeypatch.setattr(links.Linkwarden, "available", lambda self: True)
    (Path(cfg.queue_dir) / "broken.json").write_text("{ nope", encoding="utf-8")
    queue.enqueue_file(cfg, "ok.txt", b"x")
    n = queue.drain(cfg)
    assert n == 1
    # Kaputter Eintrag bleibt unberührt liegen.
    assert (Path(cfg.queue_dir) / "broken.json").exists()


# --- _safe_name ------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("normal.txt", "normal.txt"),
        ("../../etc/passwd", "passwd"),
        ("/abs/path/file.md", "file.md"),
        ("a/b/c.pdf", "c.pdf"),
        (".hidden", "hidden"),
        ("", "upload.bin"),
        (None, "upload.bin"),
        ("   ", "upload.bin"),
    ],
)
def test_safe_name(raw, expected):
    assert queue._safe_name(raw) == expected


def test_enqueue_file_sanitizes_traversal_filename(cfg, monkeypatch):
    monkeypatch.setattr(links.Linkwarden, "available", lambda self: True)
    queue.enqueue_file(cfg, "../../evil.txt", b"data")
    queue.drain(cfg)
    # Landet flach in der Inbox, nicht außerhalb.
    assert (Path(cfg.docs_path) / "evil.txt").read_bytes() == b"data"
    assert not (Path(cfg.docs_path).parent.parent / "evil.txt").exists()
