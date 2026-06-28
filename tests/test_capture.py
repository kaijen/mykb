"""Tests für ``mykb.capture`` (FastAPI Capture-Dienst, Inbox/Queue).

Randbedingungen (siehe CLAUDE.md / conftest):
- Kein Import von ``mykb.server``/``server.server`` (braucht ``mcp``).
- Kein echter Embedder/torch — der Capture-Dienst embeddet nicht selbst.
- Kein Netzwerk — Linkwarden ist im direct-Modus über fehlende
  ``LINKWARDEN_URL``/``LINKWARDEN_TOKEN`` (Env) bewusst nicht verfügbar.
- Alle Pfade liegen unter ``tmp_path`` (via ``cfg``-Fixture).
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mykb import capture


@pytest.fixture(autouse=True)
def _no_linkwarden_env(monkeypatch):
    """Linkwarden ist standardmäßig nicht konfiguriert (Env leer)."""
    monkeypatch.delenv("LINKWARDEN_URL", raising=False)
    monkeypatch.delenv("LINKWARDEN_TOKEN", raising=False)


@pytest.fixture
def client(cfg):
    """TestClient im direct-Modus (Standard)."""
    return TestClient(capture.create_app(cfg))


@pytest.fixture
def queue_cfg(cfg):
    return replace(cfg, capture_mode="queue")


@pytest.fixture
def queue_client(queue_cfg):
    return TestClient(capture.create_app(queue_cfg))


# --- _safe_name --------------------------------------------------------------

def test_safe_name_strips_path():
    assert capture._safe_name("../../etc/passwd") == "passwd"


def test_safe_name_empty_fallback():
    assert capture._safe_name("") == "upload.bin"
    assert capture._safe_name(None) == "upload.bin"


def test_safe_name_strips_leading_dots():
    assert capture._safe_name(".bashrc") == "bashrc"


# --- /health -----------------------------------------------------------------

def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --- /status -----------------------------------------------------------------

def test_status_contains_queue_pending(client):
    resp = client.get("/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "queue_pending" in body
    assert body["queue_pending"] == 0
    assert "generated_at" in body


# --- direct-Modus: /capture/file --------------------------------------------

def test_capture_file_direct_writes_to_inbox(client, cfg):
    resp = client.post(
        "/capture/file",
        files={"file": ("notiz.md", b"hallo welt", "text/markdown")},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["target"] == "inbox"

    dest = Path(cfg.docs_path) / "notiz.md"
    assert dest.is_file()
    assert dest.read_bytes() == b"hallo welt"
    assert body["path"] == str(dest)


def test_capture_file_direct_note_goes_to_notes(client, cfg):
    resp = client.post(
        "/capture/file",
        files={"file": ("n.md", b"x", "text/markdown")},
        data={"kind": "note"},
    )
    assert resp.status_code == 202
    assert (Path(cfg.notes_path) / "n.md").is_file()


def test_capture_file_direct_collection_subdir(client, cfg):
    resp = client.post(
        "/capture/file",
        files={"file": ("a.txt", b"y", "text/plain")},
        data={"collection": "infosec"},
    )
    assert resp.status_code == 202
    assert (Path(cfg.docs_path) / "infosec" / "a.txt").is_file()


def test_capture_file_direct_sanitizes_filename(client, cfg):
    resp = client.post(
        "/capture/file",
        files={"file": ("../../evil.txt", b"z", "text/plain")},
    )
    assert resp.status_code == 202
    dest = Path(cfg.docs_path) / "evil.txt"
    assert dest.is_file()
    # Kein Traversal aus dem Quellordner heraus.
    assert not (Path(cfg.docs_path).parent / "evil.txt").exists()


def test_capture_file_direct_fires_trigger(client, cfg):
    assert not Path(cfg.trigger_path).exists()
    resp = client.post(
        "/capture/file",
        files={"file": ("t.txt", b"q", "text/plain")},
    )
    assert resp.status_code == 202
    # Watcher-Trigger wurde gesetzt.
    assert Path(cfg.trigger_path).is_file()


# --- direct-Modus: /capture/url ----------------------------------------------

def test_capture_url_direct_without_linkwarden_503(client):
    resp = client.post("/capture/url", json={"url": "https://example.org/a"})
    assert resp.status_code == 503


# --- queue-Modus: /capture/url -----------------------------------------------

def test_capture_url_queue_enqueues(queue_client, queue_cfg):
    from mykb import queue

    resp = queue_client.post(
        "/capture/url",
        json={"url": "https://example.org/q", "tags": ["a"], "note": "n"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["target"] == "queue"
    assert "id" in body

    pending = queue.list_pending(queue_cfg)
    assert len(pending) == 1
    rec = pending[0]
    assert rec["type"] == "url"
    assert rec["url"] == "https://example.org/q"
    assert rec["tags"] == ["a"]
    assert rec["note"] == "n"


def test_capture_url_queue_no_trigger(queue_client, queue_cfg):
    # Im Queue-Modus zieht der Laptop später; kein lokaler Trigger.
    queue_client.post("/capture/url", json={"url": "https://example.org/q"})
    assert not Path(queue_cfg.trigger_path).exists()


# --- queue-Modus: /capture/file ----------------------------------------------

def test_capture_file_queue_enqueues(queue_client, queue_cfg):
    from mykb import queue

    resp = queue_client.post(
        "/capture/file",
        files={"file": ("doc.txt", b"inhalt", "text/plain")},
        data={"kind": "document", "collection": "c1"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["target"] == "queue"
    assert "id" in body

    pending = queue.list_pending(queue_cfg)
    assert len(pending) == 1
    rec = pending[0]
    assert rec["type"] == "file"
    assert rec["filename"] == "doc.txt"
    assert rec["kind"] == "document"
    assert rec["collection"] == "c1"

    # Inbox bleibt unberührt — Datei liegt nur in der Queue als Blob.
    blob = Path(queue_cfg.queue_dir) / rec["blob"]
    assert blob.read_bytes() == b"inhalt"
    assert not (Path(queue_cfg.docs_path) / "doc.txt").exists()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
