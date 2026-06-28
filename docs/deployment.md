# Deployment

mykb läuft **Docker-first** auf zwei Maschinen — am Host ist nur Docker nötig
(am Laptop zusätzlich das **NVIDIA Container Toolkit** für die GPU). Bewusste
Trennung: **Erstellen** (Laptop, GPU) und **Abfragen** (VPS, CPU).

```mermaid
flowchart LR
    subgraph Laptop [Laptop · docker-compose.laptop.yml]
        CAP[capture] --> DOCS[(documents/notes)]
        CAP --> LWC[linkwarden]
        CAP -.Trigger.-> SCH
        SCH[scheduler · GPU<br/>mykb watch] --> LNC[(lance)]
        DOCS --> SCH
        LWC -->|links sync| SCH
        OLL[ollama] -.Anreicherung.-> SCH
    end
    SCH ==>|rsync nach jedem Lauf| LNV[(lance-Kopie)]
    subgraph VPS [VPS · docker-compose.yml]
        TR[traefik TLS] --> AU[authelia 2FA] --> MCP[mcp]
        LNV --> MCP
    end
    PH[Handy/Rechner] -->|Tailscale| CAP
    CL[Claude] <-->|SSE| TR
```

!!! danger "Alle Daten landen auf dem VPS"
    Der gesamte `lance`-Index wird auf den VPS gespiegelt — also können auch
    **private/vertrauliche Inhalte** remote liegen. Absicherung ist daher
    **Pflicht**: TLS, Authelia 2FA, Rate Limiting, Logging. Streng vertrauliche
    Dokumente im Zweifel in einer getrennten, lokalen Instanz halten.

## Laptop (Erstellen)

`docker-compose.laptop.yml` startet **capture**, **scheduler** (Embedding auf
der GPU), **ollama**, **linkwarden** (+postgres) und den **sync**-Sidecar.

```bash
cp deploy/.env.example deploy/.env     # Secrets, SSH_KEY, VPS_SSH_TARGET …

docker compose -f deploy/docker-compose.laptop.yml up -d --build
docker compose -f deploy/docker-compose.laptop.yml exec ollama ollama pull llama3.2

tailscale serve --bg 8765              # Capture im Tailnet veröffentlichen
```

- **capture** (CPU) nimmt Übergaben entgegen und setzt einen Trigger (siehe
  [Von unterwegs erfassen](capture.md)).
- **scheduler** (`mykb watch`, GPU) reagiert auf den Trigger (debounced) bzw. das
  Fallback-Intervall, verarbeitet die Inbox und spiegelt `lance` **direkt danach**
  per rsync zum VPS (`VPS_SSH_TARGET`). Ein separater sync-Container entfällt.

## VPS (Abfragen)

`docker-compose.yml` startet **Traefik + Authelia + MCP-Server**. Der
MCP-Container liest nur den gespiegelten `lance`-Index (read-only) und rechnet
auf CPU.

```bash
cp deploy/.env.example deploy/.env     # DOMAIN, ACME_EMAIL …
cp deploy/authelia/configuration.example.yml   deploy/authelia/configuration.yml
cp deploy/authelia/users_database.example.yml  deploy/authelia/users_database.yml
#   -> Secrets/Hashes setzen, default_policy bleibt deny

docker compose -f deploy/docker-compose.yml up -d --build
```

## Sicherheitsmerkmale

- **TLS erzwingen** — HTTP → HTTPS, Zertifikate via Let's Encrypt (ACME).
- **2FA** — Authelia-`default_policy` ist `deny`; der MCP-Router nutzt die
  `authelia@docker`-Middleware (`two_factor`).
- **Rate Limiting** — Authelia-`regulation` gegen Brute-Force.
- **Secrets** — über `deploy/.env` / Docker Secrets, nie im Repo.

## Sync (im scheduler)

Der `scheduler` spiegelt das `lance`-Verzeichnis per `rsync` über SSH zum VPS —
**direkt nach jedem `process`-Lauf**, also nie mitten in einen Schreibvorgang.
Voraussetzung: ein SSH-Key (`SSH_KEY`, als Datei gemountet) und das Ziel
`VPS_SSH_TARGET` (z. B. `user@vps:/srv/mykb/data/lance/`). Ohne `VPS_SSH_TARGET`
wird der Sync übersprungen.

!!! note "Ohne Docker"
    `deploy/systemd/` und `deploy/cron/` sind die **bare-metal-Alternative**
    (lokales venv) und für den reinen Docker-Betrieb nicht nötig.
