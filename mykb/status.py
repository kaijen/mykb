"""Betrieblicher Status: Bestände, Queue-Rückstand, letzte Verarbeitung/Sync.

Datenquelle für `mykb status` (CLI), das MCP-Statustool und die PWA (`GET
/status`). Best-effort: was lokal erreichbar ist, wird berichtet; Fehlendes
erscheint als 0/null.

Der Watcher schreibt nach jedem Lauf/Sync einen kleinen Zustand
(`STATE_DIR/last_run.json`), den der Status hier ausliest.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import structlog

from .config import DOCS_TABLE, LINKS_TABLE, Config

logger = structlog.get_logger()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_path(cfg: Config) -> Path:
    return Path(cfg.state_dir) / "last_run.json"


def read_state(cfg: Config) -> dict:
    try:
        return json.loads(_state_path(cfg).read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_state(cfg: Config, **fields) -> None:
    """Zustand mergen und atomar schreiben (z. B. last_process, last_sync)."""
    path = _state_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = read_state(cfg)
    data.update(fields)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def collect_status(cfg: Config) -> dict:
    from . import queue, store

    out: dict = {"generated_at": _now()}

    try:
        db = store.connect(cfg)
        names = db.table_names()
        if DOCS_TABLE in names:
            out["documents"] = store.counts(db.open_table(DOCS_TABLE))
        if LINKS_TABLE in names:
            rows = store.all_links(db.open_table(LINKS_TABLE))
            by_status: dict[str, int] = {}
            for r in rows:
                s = r.get("status", "unchecked")
                by_status[s] = by_status.get(s, 0) + 1
            out["links"] = {"total": len(rows), "by_status": by_status}
    except Exception as exc:  # Index evtl. (noch) nicht erreichbar
        out["store_error"] = str(exc)[:200]

    out["queue_pending"] = len(queue.list_pending(cfg))

    state = read_state(cfg)
    out["last_process"] = state.get("last_process")
    out["last_sync"] = state.get("last_sync")
    return out
