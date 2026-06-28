"""Tests für ``mykb.config``.

Die Feld-Defaults der ``Config``-Dataclass werden beim Import des Moduls aus
``os.getenv`` ausgewertet (Klassenkörper, nicht im ``__init__``). Env-Overrides
testen wir daher über ``importlib.reload`` nach gesetztem ``os.environ``, nicht
durch erneutes ``Config()`` allein.

Randbedingungen (siehe CLAUDE.md): kein Import von ``mykb.server``, kein
Embedder/torch, kein Netzwerk. ``mykb.config`` ist abhängigkeitsfrei.
"""
from __future__ import annotations

import importlib

import pytest

import mykb.config as config_module
from mykb.config import (
    DOC_SUFFIXES,
    DOCS_TABLE,
    LINKS_TABLE,
    SOURCE_TYPES,
    Config,
    load_config,
)


@pytest.fixture
def reload_config(monkeypatch):
    """Lädt ``mykb.config`` mit aktuell gesetztem ``os.environ`` neu.

    Räumt nach dem Test wieder auf, damit der originale Modulzustand (Defaults
    ohne gesetzte Env-Variablen) für andere Tests erhalten bleibt.
    """

    def _reload():
        return importlib.reload(config_module)

    yield _reload
    # Sauber zurück auf den Default-Zustand (monkeypatch hat os.environ bereits
    # zurückgesetzt, wenn dieser Teardown läuft).
    importlib.reload(config_module)


def test_module_constants():
    assert DOCS_TABLE == "documents"
    assert LINKS_TABLE == "links"
    assert SOURCE_TYPES == ("document", "note", "web", "link")
    assert DOC_SUFFIXES == {".pdf", ".md", ".markdown", ".txt"}


def test_load_config_returns_config():
    cfg = load_config()
    assert isinstance(cfg, Config)


def test_load_config_defaults():
    cfg = load_config()
    # Pfade
    assert cfg.db_path == "./data/lance"
    assert cfg.docs_path == "./data/documents"
    assert cfg.notes_path == "./data/notes"
    # Embedding
    assert cfg.device == "cuda"
    assert cfg.batch_size == 32
    assert cfg.chunk_size == 500
    assert cfg.chunk_overlap == 50
    assert cfg.embed_dim is None
    # MCP-Server
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 8000
    # Capture
    assert cfg.capture_host == "127.0.0.1"
    assert cfg.capture_port == 8765
    assert cfg.capture_mode == "direct"
    # Queue
    assert cfg.queue_dir == "./data/state/queue"
    assert cfg.queue_pull_source == ""
    assert cfg.queue_poll == 60.0
    # Suche
    assert cfg.top_k == 20
    assert cfg.return_k == 5
    assert cfg.rerank_model is None
    assert cfg.rerank_device == "cpu"
    # Web / Link-Prüfung
    assert cfg.http_timeout == 20.0
    assert cfg.http_user_agent.startswith("mykb/")
    assert cfg.link_check_concurrency == 8
    # Scheduler
    assert cfg.state_dir == "./data/state"
    assert cfg.process_debounce == 30.0
    assert cfg.process_interval == 3600
    assert cfg.watch_poll == 5.0
    assert cfg.vps_ssh_target == ""
    assert cfg.ssh_key == "/key"
    # Enrich
    assert cfg.enrich is False
    assert cfg.ollama_url == "http://localhost:11434"
    assert cfg.ollama_model == "llama3.2"
    assert cfg.enrich_max_chars == 6000


def test_trigger_path_property():
    cfg = Config(state_dir="/some/state")
    assert cfg.trigger_path == "/some/state/capture.trigger"


def test_trigger_path_follows_state_dir():
    cfg = Config(state_dir="/var/run/mykb")
    assert cfg.trigger_path.endswith("capture.trigger")
    assert cfg.trigger_path.startswith("/var/run/mykb")


def test_embed_dim_none_when_unset():
    # Ohne EMBED_DIM bleibt das Feld None (volle Dimension).
    assert load_config().embed_dim is None


@pytest.mark.parametrize(
    ("env", "attr", "expected"),
    [
        ({"LANCE_DB_PATH": "/x/lance"}, "db_path", "/x/lance"),
        ({"SOURCE_DOCS_PATH": "/x/docs"}, "docs_path", "/x/docs"),
        ({"NOTES_PATH": "/x/notes"}, "notes_path", "/x/notes"),
        ({"EMBED_DEVICE": "cpu"}, "device", "cpu"),
        ({"EMBED_BATCH_SIZE": "8"}, "batch_size", 8),
        ({"CHUNK_SIZE": "256"}, "chunk_size", 256),
        ({"CHUNK_OVERLAP": "16"}, "chunk_overlap", 16),
        ({"EMBED_DIM": "512"}, "embed_dim", 512),
        ({"MCP_HOST": "127.0.0.1"}, "host", "127.0.0.1"),
        ({"MCP_PORT": "9001"}, "port", 9001),
        ({"CAPTURE_HOST": "0.0.0.0"}, "capture_host", "0.0.0.0"),
        ({"CAPTURE_PORT": "9999"}, "capture_port", 9999),
        ({"CAPTURE_MODE": "queue"}, "capture_mode", "queue"),
        ({"QUEUE_PULL_SOURCE": "vps:/q"}, "queue_pull_source", "vps:/q"),
        ({"QUEUE_POLL": "15"}, "queue_poll", 15.0),
        ({"SEARCH_TOP_K": "40"}, "top_k", 40),
        ({"SEARCH_RETURN_K": "7"}, "return_k", 7),
        ({"RERANK_MODEL": "some/reranker"}, "rerank_model", "some/reranker"),
        ({"RERANK_DEVICE": "cuda"}, "rerank_device", "cuda"),
        ({"HTTP_TIMEOUT": "5"}, "http_timeout", 5.0),
        ({"HTTP_USER_AGENT": "custom-ua"}, "http_user_agent", "custom-ua"),
        ({"LINK_CHECK_CONCURRENCY": "3"}, "link_check_concurrency", 3),
        ({"STATE_DIR": "/x/state"}, "state_dir", "/x/state"),
        ({"PROCESS_DEBOUNCE": "10"}, "process_debounce", 10.0),
        ({"PROCESS_INTERVAL": "120"}, "process_interval", 120),
        ({"WATCH_POLL": "2"}, "watch_poll", 2.0),
        ({"VPS_SSH_TARGET": "user@vps:/path"}, "vps_ssh_target", "user@vps:/path"),
        ({"SSH_KEY": "/secrets/id"}, "ssh_key", "/secrets/id"),
        ({"OLLAMA_URL": "http://ollama:11434"}, "ollama_url", "http://ollama:11434"),
        ({"OLLAMA_MODEL": "qwen2.5"}, "ollama_model", "qwen2.5"),
        ({"ENRICH_MAX_CHARS": "1234"}, "enrich_max_chars", 1234),
    ],
)
def test_env_override(monkeypatch, reload_config, env, attr, expected):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    mod = reload_config()
    cfg = mod.load_config()
    assert getattr(cfg, attr) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("Yes", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("", False),
        ("nope", False),
    ],
)
def test_enrich_flag_parsing(monkeypatch, reload_config, value, expected):
    monkeypatch.setenv("ENRICH", value)
    mod = reload_config()
    assert mod.load_config().enrich is expected


def test_queue_dir_derives_from_state_dir(monkeypatch, reload_config):
    # Ohne QUEUE_DIR wird queue_dir aus STATE_DIR abgeleitet.
    monkeypatch.setenv("STATE_DIR", "/x/state")
    monkeypatch.delenv("QUEUE_DIR", raising=False)
    mod = reload_config()
    cfg = mod.load_config()
    assert cfg.queue_dir == "/x/state/queue"


def test_queue_dir_explicit_overrides_state_dir(monkeypatch, reload_config):
    monkeypatch.setenv("STATE_DIR", "/x/state")
    monkeypatch.setenv("QUEUE_DIR", "/custom/queue")
    mod = reload_config()
    cfg = mod.load_config()
    assert cfg.queue_dir == "/custom/queue"
