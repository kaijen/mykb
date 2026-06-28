"""Durable Datei-Queue als Puffer, falls der Laptop nicht verfügbar ist.

Annahme läuft auf einem immer-erreichbaren Knoten (z. B. VPS, im Tailnet): der
Capture-Dienst im Modus ``queue`` legt Übergaben hier ab. Der Laptop zieht die
Queue (rsync) und ``drain``t sie in die lokale Inbox bzw. nach Linkwarden; das
eigentliche Embedding macht danach der normale Lauf.

Format: ein Eintrag = eine ``<id>.json`` (Metadaten); Datei-Uploads zusätzlich
ein ``<id>.bin`` (Inhalt). Geschrieben wird atomar (temp + ``os.replace``), und
die ``.json`` wird **zuletzt** geschrieben — ein Eintrag gilt erst mit
vorhandener ``.json`` als vollständig. ``drain`` entfernt einen Eintrag erst
nach erfolgreicher Übernahme; bei Fehlern bleibt er für den nächsten Versuch.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog

from .config import Config

logger = structlog.get_logger()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(name: str | None) -> str:
    base = Path(name or "").name.strip().lstrip(".")
    return base or "upload.bin"


def _qdir(cfg: Config) -> Path:
    d = Path(cfg.queue_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_json(path: Path, rec: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def enqueue_url(
    cfg: Config,
    url: str,
    tags: list[str] | None = None,
    note: str = "",
    collection: str = "",
) -> str:
    qid = uuid.uuid4().hex
    rec = {
        "type": "url",
        "id": qid,
        "url": url,
        "tags": tags or [],
        "note": note or "",
        "collection": collection or "",
        "received_at": _now(),
    }
    _write_json(_qdir(cfg) / f"{qid}.json", rec)
    logger.info("queued_url", id=qid, url=url[:80])
    return qid


def enqueue_file(
    cfg: Config,
    filename: str,
    data: bytes,
    kind: str = "document",
    collection: str = "",
) -> str:
    qid = uuid.uuid4().hex
    qd = _qdir(cfg)
    blob = qd / f"{qid}.bin"
    tmp = blob.with_suffix(".bin.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, blob)  # Inhalt zuerst, vollständig
    rec = {
        "type": "file",
        "id": qid,
        "filename": _safe_name(filename),
        "kind": "note" if kind == "note" else "document",
        "collection": collection or "",
        "blob": blob.name,
        "received_at": _now(),
    }
    _write_json(qd / f"{qid}.json", rec)  # Metadaten zuletzt -> Eintrag komplett
    logger.info("queued_file", id=qid, filename=rec["filename"], bytes=len(data))
    return qid


def list_pending(cfg: Config) -> list[dict]:
    qd = Path(cfg.queue_dir)
    if not qd.exists():
        return []
    out: list[dict] = []
    for p in sorted(qd.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # unvollständig/kaputt -> ignorieren
            continue
    return out


def drain(cfg: Config) -> int:
    """Queue in die lokale Inbox/Linkwarden übernehmen. Gibt die Anzahl der
    erfolgreich übernommenen Einträge zurück."""
    from . import links

    qd = Path(cfg.queue_dir)
    if not qd.exists():
        return 0

    lw = links.Linkwarden(cfg)
    count = 0
    for jpath in sorted(qd.glob("*.json")):
        try:
            rec = json.loads(jpath.read_text(encoding="utf-8"))
        except Exception:
            continue
        try:
            if rec["type"] == "url":
                if not lw.available():
                    logger.warning("drain_url_no_linkwarden", id=rec.get("id"))
                    continue  # später erneut versuchen
                lw.create_link(
                    rec["url"],
                    tags=rec.get("tags") or [],
                    note=rec.get("note", ""),
                    collection=rec.get("collection", ""),
                )
            elif rec["type"] == "file":
                blob = qd / rec["blob"]
                root = Path(cfg.notes_path if rec.get("kind") == "note" else cfg.docs_path)
                target_dir = root / rec["collection"] if rec.get("collection") else root
                target_dir.mkdir(parents=True, exist_ok=True)
                (target_dir / rec["filename"]).write_bytes(blob.read_bytes())
                blob.unlink(missing_ok=True)
            else:
                logger.warning("drain_unknown_type", id=rec.get("id"))
                continue
            jpath.unlink(missing_ok=True)
            count += 1
        except Exception as exc:  # Eintrag bleibt für den nächsten Versuch
            logger.error("drain_item_failed", id=rec.get("id"), error=str(exc)[:200])

    if count:
        logger.info("queue_drained", items=count)
    return count
