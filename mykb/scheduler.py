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
from pathlib import Path

import structlog

from .config import Config

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


def _rsync(cfg: Config) -> None:
    if not cfg.vps_ssh_target:
        return
    cmd = [
        "rsync",
        "-az",
        "--delete",
        "-e",
        f"ssh -i {cfg.ssh_key} -o StrictHostKeyChecking=accept-new",
        f"{cfg.db_path}/",
        cfg.vps_ssh_target,
    ]
    logger.info("sync_start", target=cfg.vps_ssh_target)
    subprocess.run(cmd, check=True)
    logger.info("sync_done")


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

    logger.info(
        "watch_start",
        trigger=cfg.trigger_path,
        debounce=cfg.process_debounce,
        interval=cfg.process_interval,
    )
    while True:
        now = time.time()
        run, reason = should_process(
            now, trigger.mtime(), last_run, cfg.process_debounce, cfg.process_interval
        )
        if run:
            # Vor dem Lauf löschen, damit Übergaben während der Verarbeitung den
            # nächsten Zyklus erneut auslösen (process ist idempotent).
            trigger.clear()
            logger.info("process_run", reason=reason)
            try:
                process_once(cfg, ingestor)
                _rsync(cfg)
            except Exception as exc:  # defensiv: der Watcher darf nicht sterben
                logger.error("process_failed", error=str(exc)[:200])
            last_run = time.time()
        time.sleep(cfg.watch_poll)
