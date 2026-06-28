# Smoke-Test (Zielplattform)

End-to-End-Checkliste für den ersten echten Durchlauf — bewusst manuell, weil GPU,
Modelle, Tailscale und die Dienste eine reale Umgebung brauchen.

## Voraussetzungen
- [ ] Laptop: Docker + NVIDIA Container Toolkit (`docker info | grep -i nvidia`)
- [ ] `deploy/.env` ausgefüllt (Secrets, `LINKWARDEN_TOKEN`, ggf. `VPS_SSH_TARGET`+`SSH_KEY`)

## Laptop hochfahren
- [ ] `docker compose -f deploy/docker-compose.laptop.yml up -d --build`
- [ ] `docker compose -f deploy/docker-compose.laptop.yml exec ollama ollama pull llama3.2`
- [ ] GPU sichtbar im Scheduler: `... exec scheduler nvidia-smi`
- [ ] Linkwarden erreichbar (`http://localhost:3000`), Access-Token erzeugt → in `.env`

## Capture → Verarbeitung → Suche
- [ ] Testdatei übergeben:
      `curl -X POST http://127.0.0.1:8765/capture/file -F kind=document -F file=@./test.pdf`
- [ ] Scheduler-Log zeigt zeitnah einen Lauf:
      `... logs -f scheduler` → `process_run reason=trigger` … `ingested`
- [ ] Suche findet es (eval-Runner als schnelle Probe):
      `python eval/run_eval.py --queries eval/queries.yaml` (oder eine 1-Zeilen-Query)
- [ ] Falls `VPS_SSH_TARGET` gesetzt: Log zeigt `sync_start`/`sync_done`

## Tailscale (von unterwegs)
- [ ] `tailscale serve --bg 8765`, dann `tailscale serve status` zeigt die URL
- [ ] Vom Handy/zweiten Gerät: `mykb-send.sh url …` bzw. `/capture/file` über die `ts.net`-URL

## VPS (Abfrageseite)
- [ ] `lance` ist per rsync angekommen (`ls .../data/lance`)
- [ ] `docker compose -f deploy/docker-compose.yml up -d --build`
- [ ] MCP-Endpoint hinter Traefik/Authelia erreichbar; in Claude als SSE-Server eintragen
- [ ] In Claude: `search_knowledge` / `find_links` liefern Treffer

## Bei Problemen zuerst prüfen
- `EMBED_DIM` muss auf Laptop **und** VPS gleich sein (sonst leere/falsche Treffer).
- Linkwarden-API-Felder/Endpoint ggf. an die installierte Version anpassen (`mykb/links.py`).
- Authelia `default_policy: deny` + Secrets gesetzt, sonst 401/Redirect-Schleife.
