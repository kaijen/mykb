"""Tests für ``mykb.links`` — nur die leichten Teile.

Abgedeckt:
- ``Linkwarden.map_item``: Mapping von name/tags/collection/description/
  textContent auf unsere Felder, inkl. Fallbacks und Filterung leerer Tags.
- ``Linkwarden.create_link``: baut den korrekten Request-Body und ruft die
  Linkwarden-API über einen gemonkeypatchten ``httpx.Client`` auf.

Randbedingungen (siehe CLAUDE.md):
- Kein echter Netzaufruf, kein Ingestor / Embedder.
"""
from __future__ import annotations

import httpx
import pytest

from mykb.links import Linkwarden

# --- map_item ----------------------------------------------------------------


def test_map_item_voll() -> None:
    item = {
        "url": "https://example.org/a",
        "name": "Titel A",
        "tags": [{"name": "infosec"}, {"name": "lesen"}],
        "description": "eine Notiz",
        "collection": {"name": "Sammlung X"},
        "textContent": "Lesetext hier.",
        "createdAt": "2026-01-01T00:00:00Z",
    }
    out = Linkwarden.map_item(item)
    assert out == {
        "url": "https://example.org/a",
        "title": "Titel A",
        "tags": ["infosec", "lesen"],
        "note": "eine Notiz",
        "collection": "Sammlung X",
        "text": "Lesetext hier.",
        "added_at": "2026-01-01T00:00:00Z",
    }


def test_map_item_title_faellt_auf_url_zurueck() -> None:
    item = {"url": "https://example.org/b"}
    out = Linkwarden.map_item(item)
    assert out["title"] == "https://example.org/b"


def test_map_item_leere_und_fehlende_felder() -> None:
    out = Linkwarden.map_item({})
    assert out == {
        "url": "",
        "title": "",
        "tags": [],
        "note": "",
        "collection": "",
        "text": "",
        "added_at": "",
    }


def test_map_item_filtert_tags_ohne_namen() -> None:
    item = {
        "url": "https://example.org/c",
        "tags": [{"name": "a"}, {"name": ""}, {}, {"name": "b"}],
    }
    out = Linkwarden.map_item(item)
    assert out["tags"] == ["a", "b"]


def test_map_item_collection_null() -> None:
    # Manche Versionen liefern collection = null.
    item = {"url": "https://example.org/d", "collection": None}
    out = Linkwarden.map_item(item)
    assert out["collection"] == ""


# --- create_link -------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Erfasst Konstruktor- und post-Argumente statt echtem Netzverkehr."""

    captured: dict = {}

    def __init__(self, **kwargs) -> None:
        _FakeClient.captured["init"] = kwargs

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc) -> None:
        return None

    def post(self, url: str, json: dict) -> _FakeResponse:  # noqa: A002
        _FakeClient.captured["url"] = url
        _FakeClient.captured["json"] = json
        return _FakeResponse({"response": {"id": 42}})


@pytest.fixture
def patched_client(monkeypatch) -> type[_FakeClient]:
    _FakeClient.captured = {}
    monkeypatch.setattr(httpx, "Client", _FakeClient)
    return _FakeClient


@pytest.fixture
def lw(cfg, monkeypatch) -> Linkwarden:
    monkeypatch.setenv("LINKWARDEN_URL", "https://lw.example/")
    monkeypatch.setenv("LINKWARDEN_TOKEN", "geheim")
    return Linkwarden(cfg)


def test_create_link_voller_body(lw, patched_client) -> None:
    result = lw.create_link(
        "https://example.org/x",
        tags=["t1", "t2"],
        note="meine Notiz",
        collection="Sammlung",
    )

    cap = patched_client.captured
    # Endpoint und Trailing-Slash-Bereinigung der Base-URL.
    assert cap["url"] == "https://lw.example/api/v1/links"
    assert cap["json"] == {
        "url": "https://example.org/x",
        "description": "meine Notiz",
        "tags": [{"name": "t1"}, {"name": "t2"}],
        "collection": {"name": "Sammlung"},
    }
    # Auth-Header und Timeout an den Client durchgereicht.
    assert cap["init"]["headers"] == {"Authorization": "Bearer geheim"}
    assert cap["init"]["timeout"] == lw.cfg.http_timeout
    # Rückgabe ist der geparste JSON-Body.
    assert result == {"response": {"id": 42}}


def test_create_link_minimaler_body(lw, patched_client) -> None:
    lw.create_link("https://example.org/y")
    # Ohne tags/note/collection bleibt nur die URL übrig.
    assert patched_client.captured["json"] == {"url": "https://example.org/y"}


def test_create_link_leere_optionalfelder_weggelassen(lw, patched_client) -> None:
    lw.create_link("https://example.org/z", tags=[], note="", collection="")
    assert patched_client.captured["json"] == {"url": "https://example.org/z"}
