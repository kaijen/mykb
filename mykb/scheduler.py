"""Ereignisgesteuerte Verarbeitung ('mykb watch').

Statt fixem Intervall: Capture setzt eine Trigger-Datei, der Watcher verarbeitet
die Inbox kurz danach (debounced, um Bursts zu bündeln) und spiegelt den Index
**direkt im Anschluss** per rsync zum VPS — so wird nie mitten in einen
LanceDB-Schreibvorgang synchronisiert. Ein maximaler Abstand (`process_interval`)
dient als Fallback (hält u. a. die Link-Rot-Prüfung aktuell).

Die Entscheidungslogik (`should_process`) ist bewusst rein und damit testbar.
"""
from __future__ import annotations

import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import structlog

from .config import Config


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()

logger = structlog.get_logger()


class Trigger:
    """Trigger-Datei auf dem gemeinsamen State-Volume (capture ↔ scheduler)."""

    def __init__(self, path: str):
        self.path = Path(path)

    def fire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()

    def mtime(self) -> float | None:
        try:
            return self.path.stat().st_mtime
        except FileNotFoundError:
            return None

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


def should_process(
    now: float,
    trigger_mtime: float | None,
    last_run: float | None,
    debounce: float,
    max_interval: float,
) -> tuple[bool, str]:
    """Reine Entscheidung, ob jetzt verarbeitet werden soll. (bool, Grund)."""
    if trigger_mtime is not None:
        if now - trigger_mtime >= debounce:
            return True, "trigger"
        return False, "debounce"
    if last_run is None:
        return True, "initial"
    if now - last_run >= max_interval:
        return True, "interval"
    return False, "idle"


def _ssh_opt(cfg: Config) -> str:
    return f"ssh -i {cfg.ssh_key} -o StrictHostKeyChecking=accept-new"


def _rsync(cfg: Config) -> None:
    if not cfg.vps_ssh_target:
        return
    cmd = [
        "rsync",
        "-az",
        "--delete",
        "-e",
        _ssh_opt(cfg),
        f"{cfg.db_path}/",
        cfg.vps_ssh_target,
    ]
    logger.info("sync_start", target=cfg.vps_ssh_target)
    subprocess.run(cmd, check=True)
    logger.info("sync_done")


def pull_and_drain(cfg: Config) -> int:
    """Entfernte Queue ziehen (rsync, an der Quelle entfernen) und lokal drainen.

    Gibt die Anzahl übernommener Einträge zurück. Puffer für Laptop-Ausfall:
    Übergaben sammeln sich auf dem immer-erreichbaren Knoten und werden hier
    übernommen, sobald der Laptop wieder läuft.
    """
    from pathlib import Path

    from . import queue

    if cfg.queue_pull_source:
        Path(cfg.queue_dir).mkdir(parents=True, exist_ok=True)
        cmd = [
            "rsync",
            "-az",
            # nach erfolgreicher Übertragung an der Quelle löschen
            "--remove-source-files",
            "-e",
            _ssh_opt(cfg),
            cfg.queue_pull_source,
            f"{cfg.queue_dir}/",
        ]
        try:
            subprocess.run(cmd, check=True)
        except Exception as exc:  # VPS evtl. kurz nicht erreichbar
            logger.warning("queue_pull_failed", error=str(exc)[:200])
    return queue.drain(cfg)


def process_once(cfg: Config, ingestor) -> int:
    """Inbox einmal verarbeiten (Reuse des bereits geladenen Embedders)."""
    from . import links

    total = ingestor.ingest_path(cfg.docs_path, "document")
    total += ingestor.ingest_path(cfg.notes_path, "note")
    if links.Linkwarden(cfg).available():
        links.sync_from_linkwarden(cfg, ingestor=ingestor)
    return total


def watch(cfg: Config) -> None:
    """Endlosschleife: auf Trigger/Intervall reagieren, verarbeiten, syncen."""
    from .ingest import Ingestor

    trigger = Trigger(cfg.trigger_path)
    ingestor = Ingestor(cfg)  # Embedder einmal laden, über alle Läufe wiederverwenden
    last_run: float | None = None
    last_pull: float | None = None

    logger.info(
        "watch_start",
        trigger=cfg.trigger_path,
        debounce=cfg.process_debounce,
        interval=cfg.process_interval,
        queue=bool(cfg.queue_pull_source),
    )
    while True:
        now = time.time()

        # Queue vom immer-erreichbaren Knoten ziehen/drainen (eigener Takt).
        if cfg.queue_pull_source and (
            last_pull is None or now - last_pull >= cfg.queue_poll
        ):
            try:
                if pull_and_drain(cfg) > 0:
                    trigger.fire()  # gedrainte Einträge wie eine Übergabe behandeln
            except Exception as exc:  # defensiv: Watcher darf nicht sterben
                logger.error("queue_drain_failed", error=str(exc)[:200])
            last_pull = now

        trigger_mtime = trigger.mtime()
        run, reason = should_process(
            now, trigger_mtime, last_run, cfg.process_debounce, cfg.process_interval
        )
        if run:
            # Compare-and-clear: nur löschen, wenn der Trigger seit der Prüfung
            # nicht erneut gefeuert wurde — sonst ginge eine Übergabe verloren,
            # die genau in dieses Fenster fällt. Eine neuere Übergabe löst dann
            # im nächsten Zyklus aus. (process ist idempotent.)
            if trigger.mtime() == trigger_mtime:
                trigger.clear()
            logger.info("process_run", reason=reason)
            from . import status

            try:
                process_once(cfg, ingestor)
                status.write_state(cfg, last_process=_now_iso())
                _rsync(cfg)
                if cfg.vps_ssh_target:
                    status.write_state(cfg, last_sync=_now_iso())
            except Exception as exc:  # defensiv: der Watcher darf nicht sterben
                logger.error("process_failed", error=str(exc)[:200])
            last_run = time.time()
        time.sleep(cfg.watch_poll)
