"""Tests für ``mykb.scheduler`` (ereignisgesteuerte Verarbeitung, 'mykb watch').

Randbedingungen siehe ``tests/conftest.py``: kein Import von ``mykb.server``,
kein Embedder/torch, kein Netzwerk. Alle Pfade liegen unter ``tmp_path`` (via
``cfg``-Fixture). ``watch()`` wird bewusst NICHT aufgerufen (Endlosschleife);
getestet wird die reine ``should_process``-Logik, die ``Trigger``-Datei-API und
``pull_and_drain`` mit gemonkeypatchtem ``subprocess.run`` und ``queue.drain``.
"""
from __future__ import annotations

import os
from pathlib import Path

from mykb import queue, scheduler

# --- should_process: alle Zweige ------------------------------------------


def test_should_process_trigger_nach_debounce() -> None:
    # Trigger liegt vor und die Ruhezeit ist abgelaufen -> verarbeiten.
    run, reason = scheduler.should_process(
        now=100.0, trigger_mtime=60.0, last_run=None, debounce=30.0, max_interval=3600.0
    )
    assert run is True
    assert reason == "trigger"


def test_should_process_trigger_genau_debounce_grenze() -> None:
    # now - trigger_mtime == debounce -> >= greift, verarbeiten.
    run, reason = scheduler.should_process(
        now=90.0, trigger_mtime=60.0, last_run=None, debounce=30.0, max_interval=3600.0
    )
    assert run is True
    assert reason == "trigger"


def test_should_process_debounce_noch_nicht_abgelaufen() -> None:
    # Trigger liegt vor, aber Ruhezeit noch nicht erreicht -> warten.
    run, reason = scheduler.should_process(
        now=80.0, trigger_mtime=60.0, last_run=None, debounce=30.0, max_interval=3600.0
    )
    assert run is False
    assert reason == "debounce"


def test_should_process_initial_ohne_trigger_ohne_last_run() -> None:
    # Kein Trigger, noch nie gelaufen -> initialer Lauf.
    run, reason = scheduler.should_process(
        now=100.0, trigger_mtime=None, last_run=None, debounce=30.0, max_interval=3600.0
    )
    assert run is True
    assert reason == "initial"


def test_should_process_interval_fallback() -> None:
    # Kein Trigger, aber max_interval seit last_run überschritten -> Fallback-Lauf.
    run, reason = scheduler.should_process(
        now=4000.0,
        trigger_mtime=None,
        last_run=300.0,
        debounce=30.0,
        max_interval=3600.0,
    )
    assert run is True
    assert reason == "interval"


def test_should_process_interval_genau_grenze() -> None:
    # now - last_run == max_interval -> >= greift, verarbeiten.
    run, reason = scheduler.should_process(
        now=3700.0,
        trigger_mtime=None,
        last_run=100.0,
        debounce=30.0,
        max_interval=3600.0,
    )
    assert run is True
    assert reason == "interval"


def test_should_process_idle() -> None:
    # Kein Trigger, kürzlich gelaufen, Intervall nicht erreicht -> nichts tun.
    run, reason = scheduler.should_process(
        now=500.0,
        trigger_mtime=None,
        last_run=300.0,
        debounce=30.0,
        max_interval=3600.0,
    )
    assert run is False
    assert reason == "idle"


def test_should_process_trigger_hat_vorrang_vor_idle() -> None:
    # Auch wenn last_run frisch ist: ein abgelaufener Trigger gewinnt.
    run, reason = scheduler.should_process(
        now=500.0,
        trigger_mtime=400.0,
        last_run=480.0,
        debounce=30.0,
        max_interval=3600.0,
    )
    assert run is True
    assert reason == "trigger"


# --- Trigger: fire / mtime / clear ----------------------------------------


def test_trigger_mtime_none_wenn_nicht_vorhanden(tmp_path) -> None:
    t = scheduler.Trigger(str(tmp_path / "sub" / "capture.trigger"))
    assert t.mtime() is None


def test_trigger_fire_legt_datei_und_eltern_an(tmp_path) -> None:
    # fire() muss auch fehlende Elternverzeichnisse anlegen.
    path = tmp_path / "state" / "nested" / "capture.trigger"
    t = scheduler.Trigger(str(path))
    t.fire()
    assert path.exists()
    assert isinstance(t.mtime(), float)


def test_trigger_clear_entfernt_datei(tmp_path) -> None:
    path = tmp_path / "capture.trigger"
    t = scheduler.Trigger(str(path))
    t.fire()
    assert path.exists()
    t.clear()
    assert not path.exists()
    assert t.mtime() is None


def test_trigger_clear_ist_missing_ok(tmp_path) -> None:
    # clear() auf eine nicht existente Datei darf nicht werfen.
    t = scheduler.Trigger(str(tmp_path / "capture.trigger"))
    t.clear()  # darf keinen FileNotFoundError auslösen
    assert t.mtime() is None


def test_trigger_fire_aktualisiert_mtime(tmp_path) -> None:
    path = tmp_path / "capture.trigger"
    t = scheduler.Trigger(str(path))
    t.fire()
    first = t.mtime()
    # mtime explizit nach vorn setzen und erneut feuern (touch aktualisiert mtime).
    os.utime(path, (first - 100, first - 100))
    assert t.mtime() == first - 100
    t.fire()
    assert t.mtime() > first - 100


# --- pull_and_drain --------------------------------------------------------


def test_pull_and_drain_ohne_pull_source_nur_drain(cfg, monkeypatch) -> None:
    # Ohne queue_pull_source darf kein rsync laufen, nur queue.drain.
    cfg.queue_pull_source = ""

    calls: list = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        raise AssertionError("subprocess.run darf ohne pull_source nicht laufen")

    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)

    monkeypatch.setattr(queue, "drain", lambda c: 3)

    assert scheduler.pull_and_drain(cfg) == 3
    assert calls == []


def test_pull_and_drain_mit_pull_source_ruft_rsync_und_drain(cfg, monkeypatch) -> None:
    cfg.queue_pull_source = "vps:/queue/"

    runs: list = []

    def fake_run(cmd, **kwargs):
        runs.append((cmd, kwargs))

    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)

    monkeypatch.setattr(queue, "drain", lambda c: 5)

    assert scheduler.pull_and_drain(cfg) == 5
    assert len(runs) == 1
    cmd, kwargs = runs[0]
    assert cmd[0] == "rsync"
    assert "--remove-source-files" in cmd
    assert cmd[-2] == cfg.queue_pull_source
    assert cmd[-1] == f"{cfg.queue_dir}/"
    assert kwargs.get("check") is True
    # Zielverzeichnis wurde angelegt.
    assert Path(cfg.queue_dir).is_dir()


def test_pull_and_drain_rsync_fehler_wird_geschluckt(cfg, monkeypatch) -> None:
    # Ein fehlgeschlagener Pull (VPS kurz weg) darf drain nicht verhindern.
    cfg.queue_pull_source = "vps:/queue/"

    def fake_run(cmd, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)

    monkeypatch.setattr(queue, "drain", lambda c: 2)

    assert scheduler.pull_and_drain(cfg) == 2
