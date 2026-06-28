# Deployment

Für den Remote-Betrieb läuft der MCP-Server hinter **Traefik** (TLS/ACME) und
**Authelia** (Forward-Auth, 2FA). Das Verzeichnis `deploy/` enthält ein
kommentiertes **Gerüst**, das vor dem Produktivbetrieb anzupassen ist.

!!! danger "Vertrauliche Dokumente"
    Öffentliche Standards und eigene Analysen sind unkritisch.
    **Client-spezifische oder vertrauliche Dokumente gehören nicht auf einen
    externen VPS**, sondern bleiben lokal oder in einer isolierten,
    NDA-konformen Instanz. Im Remote-Betrieb gilt: TLS erzwingen, 2FA, Rate
    Limiting, Logging.

## Inhalt von `deploy/`

| Datei | Zweck |
|---|---|
| `Dockerfile` | Image für Indexer + MCP-Server |
| `docker-compose.yml` | Traefik + Authelia + MCP-Server |
| `authelia/configuration.example.yml` | Authelia-Config (Vorlage) |
| `authelia/users_database.example.yml` | Benutzerdatenbank (Vorlage) |

## Inbetriebnahme

```bash
cd deploy

# 1. Domain und ACME-E-Mail setzen
export DOMAIN=rag.example.com ACME_EMAIL=admin@example.com

# 2. Authelia konfigurieren (Secrets NICHT ins Repo)
cp authelia/configuration.example.yml   authelia/configuration.yml
cp authelia/users_database.example.yml  authelia/users_database.yml
#    -> Secrets/Hashes setzen, default_policy bleibt deny

# 3. Bauen und starten
docker compose up -d --build

# 4. Index befüllen (einmalig / nach Dokumentänderungen)
docker compose run --rm mcp python scripts/index_literature.py --target all
```

## Sicherheitsmerkmale

- **TLS erzwingen** — HTTP wird auf HTTPS umgeleitet, Zertifikate via
  Let's Encrypt (ACME).
- **2FA** — Authelia-`default_policy` ist `deny`; der MCP-Router nutzt die
  `authelia@docker`-Middleware (`two_factor`).
- **Rate Limiting** — Authelia-`regulation` gegen Brute-Force.
- **Secrets** — über Docker Secrets / Environment, nie im Repo.

## GPU im Container

Das Default-Image ist CPU-only. Für GPU-Betrieb ein CUDA-Basisimage wählen, das
nvidia-Runtime im Compose aktivieren und `EMBED_DEVICE=cuda` setzen.

## Spätere Migration auf einen VPS

Ein Umzug auf einen VPS ist vorgesehen — dann ggf. CPU-only-Inferenz mit
kleineren Modellen. Die Konfiguration ist dafür bereits über Environment-
Variablen entkoppelt (siehe [Konfiguration](konfiguration.md)).
