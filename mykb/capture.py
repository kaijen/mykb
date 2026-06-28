"""Capture-Dienst: Dokumente und Links von unterwegs an den Laptop übergeben.

Erreichbar über das bestehende Tailscale-Netz. Der Dienst bindet an localhost;
die Tailnet-Veröffentlichung (HTTPS via MagicDNS, nur Tailnet-Mitglieder)
übernimmt ``tailscale serve`` — daher kein eigener Token (Zugriffsschutz über
die Tailnet-Identität/ACLs).

Bewusst „Inbox": Übergaben werden nur entgegengenommen (Datei in die
Quellordner ablegen bzw. Link an Linkwarden), die schwere GPU-Arbeit
(Embedding) erledigt ein späterer ``mykb process``-Lauf.
"""
# Ausnahme von der Projektkonvention: KEIN `from __future__ import annotations`.
# FastAPI kann mit PEP-563-Stringannotationen ``UploadFile`` in
# Endpoint-Signaturen nicht auflösen. Python 3.11 versteht ``str | None`` nativ.
import os
from pathlib import Path

import structlog

from .config import Config

logger = structlog.get_logger()


def _safe_name(name: str | None) -> str:
    """Dateinamen entschärfen (kein Pfad-Traversal)."""
    base = Path(name or "").name.strip().lstrip(".")
    return base or "upload.bin"


def create_app(cfg: Config):
    from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
    from pydantic import BaseModel

    from .scheduler import Trigger

    app = FastAPI(title="mykb capture", version="0.1.0")
    trigger = Trigger(cfg.trigger_path)
    queue_mode = cfg.capture_mode == "queue"

    class UrlIn(BaseModel):
        url: str
        tags: list[str] | None = None
        note: str | None = None
        collection: str | None = None

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/status")
    def status() -> dict:
        """Bestände, Queue-Rückstand, letzte Verarbeitung/Sync (für die PWA)."""
        from .status import collect_status

        return collect_status(cfg)

    @app.post("/capture/url", status_code=202)
    def capture_url(
        item: UrlIn,
        who: str | None = Header(default=None, alias="Tailscale-User-Login"),
    ) -> dict:
        """URL übergeben. queue-Modus: durabel einreihen. direct-Modus: an
        Linkwarden, mykb zieht sie via 'links sync'."""
        if queue_mode:
            from . import queue

            qid = queue.enqueue_url(
                cfg,
                item.url,
                tags=item.tags,
                note=item.note or "",
                collection=item.collection or "",
            )
            logger.info("captured_url", who=who, url=item.url[:80], queued=qid)
            return {"status": "queued", "target": "queue", "id": qid}

        from .links import Linkwarden

        lw = Linkwarden(cfg)
        if not lw.available():
            raise HTTPException(
                503, "Linkwarden nicht konfiguriert (LINKWARDEN_URL/TOKEN)"
            )
        try:
            lw.create_link(
                item.url,
                tags=item.tags or [],
                note=item.note or "",
                collection=item.collection or "",
            )
        except Exception as exc:  # defensiv: Detail nicht nach außen geben
            logger.error("capture_url_failed", error=str(exc)[:200])
            raise HTTPException(502, "Linkwarden-Aufruf fehlgeschlagen") from exc

        trigger.fire()  # zeitnahe Verarbeitung durch den Watcher anstoßen
        logger.info("captured_url", who=who, url=item.url[:80])
        return {"status": "queued", "target": "linkwarden", "url": item.url}

    @app.post("/capture/file", status_code=202)
    async def capture_file(
        file: UploadFile = File(...),
        kind: str = Form("document"),
        collection: str = Form(""),
        who: str | None = Header(default=None, alias="Tailscale-User-Login"),
    ) -> dict:
        """Datei übergeben. queue-Modus: durabel einreihen. direct-Modus: in den
        Quellordner (Inbox); Indexierung folgt durch den Watcher."""
        data = await file.read()

        if queue_mode:
            from . import queue

            qid = queue.enqueue_file(
                cfg, file.filename, data, kind=kind, collection=collection
            )
            logger.info("captured_file", who=who, queued=qid, bytes=len(data))
            return {"status": "queued", "target": "queue", "id": qid}

        root = Path(cfg.notes_path if kind == "note" else cfg.docs_path)
        target_dir = root / collection if collection else root
        target_dir.mkdir(parents=True, exist_ok=True)

        # Atomar schreiben: temp + os.replace, damit der Watcher nie eine
        # partielle Datei indexiert (er liest dieselben Quellordner).
        dest = target_dir / _safe_name(file.filename)
        tmp = dest.with_name(dest.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dest)

        trigger.fire()  # zeitnahe Verarbeitung durch den Watcher anstoßen
        logger.info("captured_file", who=who, path=str(dest), bytes=len(data))
        return {"status": "queued", "target": "inbox", "path": str(dest)}

    return app


def serve(cfg: Config) -> None:
    import uvicorn

    logger.info("capture_start", host=cfg.capture_host, port=cfg.capture_port)
    uvicorn.run(create_app(cfg), host=cfg.capture_host, port=cfg.capture_port)
