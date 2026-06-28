# deploy/

Remote-Betrieb des MCP-Servers hinter **Traefik** (TLS/ACME) und **Authelia**
(Forward-Auth, 2FA). Dieses Verzeichnis ist ein **Gerüst** — vor dem
Produktivbetrieb anpassen.

## Inhalt

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

# 4. Index befüllen (einmalig / nach Änderungen)
docker compose run --rm mcp python -m mykb index --source all
```

## Hinweise

- **TLS erzwingen**: HTTP wird in `docker-compose.yml` auf HTTPS umgeleitet.
- **2FA**: Authelia-`default_policy` ist `deny`, der MCP-Router nutzt die
  `authelia@docker`-Middleware (`two_factor`).
- **GPU**: Das Default-Image ist CPU-only. Für GPU ein CUDA-Basisimage wählen
  und im Compose das nvidia-Runtime aktivieren; `EMBED_DEVICE=cuda` setzen.
- **Vertraulichkeit**: Client-spezifische Dokumente gehören nicht auf einen
  öffentlichen VPS (siehe `CLAUDE.md`, Abschnitt „Sicherheit / Datenhaltung").
