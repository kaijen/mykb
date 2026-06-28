# Planmäßige Verarbeitung (`mykb process`)

Zwei Vorlagen, um die [Inbox](../../docs/capture.md) regelmäßig zu verarbeiten
(lokale Quellen indexieren + Links aus Linkwarden ziehen).

## Empfehlung: systemd-Timer

**Auf einem Linux-Laptop ist der systemd-Timer die bessere Wahl** — vor allem
wegen `Persistent=true`: verpasste Läufe (Laptop war aus/schlief) werden beim
nächsten Hochfahren **nachgeholt**, sodass nichts in der Inbox liegen bleibt.
Dazu: Logging über journald, saubere Reihenfolge nach `tailscaled`, und derselbe
Mechanismus betreibt auch den dauerhaften Capture-Dienst. Cron kann das alles
nicht und ist nur der Fallback (Nicht-systemd-System).

### Dateien

| Datei | Zweck |
|---|---|
| `mykb-process.service` | Oneshot: ein `mykb process`-Lauf |
| `mykb-process.timer` | löst den Service stündlich aus (mit Nachholen) |
| `mykb-capture.service` | dauerhafter Capture-Dienst |

### Installation (User-Units)

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/mykb-*.service deploy/systemd/mykb-process.timer \
   ~/.config/systemd/user/

# Pfade in den Units prüfen (%h/mykb, %h/mykb/.venv, %h/mykb/.env)
systemctl --user daemon-reload

# Capture-Dienst dauerhaft + Verarbeitung stündlich
systemctl --user enable --now mykb-capture.service
systemctl --user enable --now mykb-process.timer

# Damit beides auch ohne aktive Login-Session läuft (Laptop muss wach sein):
loginctl enable-linger "$USER"

# Kontrolle
systemctl --user list-timers mykb-process.timer
journalctl --user -u mykb-process.service -f
```

Intervall ändern: in `mykb-process.timer` `OnCalendar=hourly` anpassen
(z. B. `*:0/15` für alle 15 Minuten), dann `systemctl --user daemon-reload`.

## Fallback: cron

Für Systeme ohne systemd. Der Wrapper `deploy/cron/mykb-process.sh` wechselt ins
Repo, lädt `.env` und das venv.

```bash
chmod +x deploy/cron/mykb-process.sh
crontab -e
```

```cron
# stündlich; Repo ggf. über MYKB_HOME setzen
0 * * * * MYKB_HOME=$HOME/mykb $HOME/mykb/deploy/cron/mykb-process.sh >> $HOME/mykb/data/process.log 2>&1
```

!!! Hinweis
    Cron **holt verpasste Läufe nicht nach** und startet den Capture-Dienst
    nicht — den müsste man separat dauerhaft laufen lassen.
