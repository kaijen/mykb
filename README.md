# mykb — Literatur-RAG

Selbst gehostete RAG-Pipeline für eine persönliche Fach-Literatursammlung
(Information Security, Risikomanagement). Die Sammlung wird in **LanceDB**
indexiert und über einen **MCP-Server** für Claude (VSCode, Claude Desktop)
durchsuchbar gemacht.

Projektkontext, Modellwahl und Konventionen sind in [`CLAUDE.md`](CLAUDE.md)
dokumentiert.

## Architektur

```
Quelldokumente (PDF/MD/TXT)
        │
        ▼
scripts/index_literature.py   ──►  LanceDB (data/lance)
   Qwen3-Embedding (GPU, FP16)        Tabellen: standards, risk_papers
        │
        ▼
server/server.py (FastMCP, SSE)  ◄── Claude (MCP-Client)
   Query-Embedding (asymmetrisch) + optionales Reranking
        │
        ▼
deploy/  Traefik (TLS) + Authelia (2FA)  für Remote-Betrieb
```

## Schnellstart

```bash
# 1. Abhängigkeiten
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Konfiguration
cp .env.example .env        # Pfade/Device anpassen

# 3. Quelldokumente ablegen
#    data/literatur/standards/   (ISO, BSI, NIST)
#    data/literatur/research/    (Risk-Paper)

# 4. Indexieren
python scripts/index_literature.py --target all

# 5. MCP-Server starten
python server/server.py
```

## Verzeichnisstruktur

| Pfad | Inhalt |
|---|---|
| `CLAUDE.md` | Projektkontext für Claude Code |
| `requirements.txt` | Python-Abhängigkeiten |
| `scripts/index_literature.py` | Indexierung in LanceDB (fertig) |
| `server/server.py` | MCP-Server mit Such-Tools |
| `deploy/` | Docker Compose, Traefik, Authelia |
| `data/literatur/` | Quelldokumente (read-only, nicht versioniert) |
| `data/lance/` | LanceDB-Index (generiert, nicht versioniert) |

## Konfiguration

Alle Parameter werden über Environment-Variablen gesteuert; siehe
[`.env.example`](.env.example) für die vollständige Liste mit Defaults.

## Status

Siehe Abschnitt „Offene Punkte" in [`CLAUDE.md`](CLAUDE.md). Kurz:

- [x] Indexierung in LanceDB
- [x] MCP-Server: `search_standards`, `search_risk_management`, `get_document_context`
- [ ] Reranking-Stufe (gte-multilingual-reranker)
- [ ] Hybrid-Retrieval (BGE-M3) prüfen
- [ ] `deploy/`: Traefik + Authelia produktiv
- [ ] Inkrementelles Indexieren (Upsert über `file_hash`)
