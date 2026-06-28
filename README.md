# mykb — persönlicher Wissensspeicher

Selbst gehosteter **Personal-Knowledge-Management-Speicher** mit semantischer
Suche. Eigene **Dokumente**, **Notizen**, **Web-Inhalte** und eine
**Linksammlung** werden mit Embeddings in **LanceDB** indexiert und über einen
**MCP-Server** im Alltag aus Claude (VSCode, Claude Desktop) nutzbar gemacht.

> 📖 **Dokumentation:** <https://kaijen.github.io/mykb/>
> (versioniert mit MkDocs + mike, veröffentlicht über GitHub Pages)

Projektkontext, Modellwahl und Konventionen stehen in [`CLAUDE.md`](CLAUDE.md).

## Was macht das Projekt?

Vier Quelltypen landen in einem gemeinsamen, semantisch durchsuchbaren Index
(Tabelle `documents`, Feld `source_type`):

- **document** — lokale Dateien (PDF, Markdown, Text)
- **note** — eigene Notizen (Markdown, Zettelkasten/Obsidian-Stil)
- **web** — abgerufene Web-Seiten (HTML → Text, eingebettet)
- **link** — Bookmarks mit Snapshot des Seiteninhalts und Erreichbarkeitsprüfung

Die Pipeline extrahiert Text, dedupliziert über einen SHA-256-Hash, zerlegt in
überlappende Chunks, bettet sie mit `Qwen3-Embedding-0.6B` (DE + EN nativ) ein
und schreibt sie **inkrementell** (Upsert über `uri` + `content_hash`) nach
LanceDB. Der MCP-Server stellt die Suche als Werkzeug für Claude bereit.

Der Stack läuft **lokal und ohne Cloud** (LanceDB ist serverless, dateibasiert).
Alle Modelle sind **kommerziell lizenzierbar** (Apache 2.0).

## Bookmarks: Linkwarden + mykb

Bookmarks werden nicht im Eigenbau erfasst, sondern in
[**Linkwarden**](https://github.com/linkwarden/linkwarden) (Browser-Extension,
Tags, Collections, Archivierung). mykb ist die Index-/MCP-Schicht darüber:

- `mykb links sync` zieht die Links per Linkwarden-API, übernimmt die Metadaten
  in die `links`-Tabelle und indexiert den Lesetext als `source_type = link`
  (semantisch durchsuchbar, überlebt Link-Rot dank Archiv).
- `mykb links check` prüft regelmäßig die Erreichbarkeit (Link-Rot) und
  aktualisiert den Status.

So bleibt das bequeme Erfassen/Archivieren bei Linkwarden, während Suche,
RAG-Qualität, Modell-Lizenz und MCP-Tools unter eigener Kontrolle bleiben.

## Von unterwegs erfassen (Tailscale)

Ein schlanker **Capture-Dienst** macht den Laptop über das bestehende
**Tailscale**-Netz erreichbar, um Dokumente und Links von überall zu übergeben:

```bash
python -m mykb capture          # Dienst auf 127.0.0.1:8765
tailscale serve --bg 8765       # im Tailnet als HTTPS veröffentlichen (nur Tailnet)

# von unterwegs übergeben
scripts/mykb-send.sh url  https://example.org "lesen"          # -> Linkwarden
scripts/mykb-send.sh file ~/paper.pdf document forschung        # -> Inbox

python -m mykb process          # Inbox verarbeiten: index + links sync
```

Übergaben landen in der **Inbox** (Datei → Quellordner, Link → Linkwarden); das
Embedding erledigt `mykb process` (z. B. per systemd-Timer). Zugriffsschutz über
die Tailnet-Identität, kein Token. Details: [docs/capture.md](docs/capture.md).

## Betriebsmodell: Erstellen vs. Abfragen

```
ERSTELLEN (Laptop, GPU)                     ABFRAGEN (VPS, CPU)
─────────────────────────                   ─────────────────────
python -m mykb index   (Dokumente/Notizen)  server/server.py (FastMCP, SSE)
python -m mykb web     (Web-Inhalte)          search_knowledge
python -m mykb links   (Linkwarden + Check)   find_links
        │                                      get_document_context
        ▼                                          ▲
   LanceDB (documents, links)  ───  Sync  ───────┘
   Qwen3-Embedding (FP16)           (rsync/S3, noch offen)
```

Beide Seiten nutzen denselben **asymmetrischen** Qwen3-Embedder
(`mykb/embedder.py`): Passages ohne Prefix, Queries mit Instruction-Prefix.
Entscheidung: **alle Daten** werden auf den VPS synchronisiert — die Absicherung
(Authelia 2FA, TLS, Rate Limiting) ist daher Pflicht. Der konkrete
Sync-Mechanismus ist noch offen.

## Schnellstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Pfade/Device/Linkwarden anpassen

# Quellen ablegen
#   data/documents/   (PDF/MD/TXT)
#   data/notes/       (Markdown)

# Indexieren (optional mit KI-Anreicherung: Zusammenfassung + Auto-Tags)
python -m mykb index --source all
python -m mykb index --source all --enrich     # benötigt laufendes Ollama

# Web-Seite aufnehmen
python -m mykb web https://example.org/artikel --tags infosec,lesen

# Auto-Sammlungen (Themen-Cluster vorschlagen / anwenden)
python -m mykb collections
python -m mykb collections --apply

# Linksammlung (benötigt LINKWARDEN_URL + LINKWARDEN_TOKEN)
python -m mykb links sync
python -m mykb links check
python -m mykb links list --broken

# MCP-Server (Abfrageseite)
python server/server.py
```

### MCP-Server in Claude einbinden

Der Server spricht **SSE** auf `MCP_HOST:MCP_PORT` (Default `0.0.0.0:8000`).
Im MCP-Client als SSE-Endpoint eintragen:

```json
{ "mcpServers": { "mykb": { "url": "http://localhost:8000/sse" } } }
```

## MCP-Tools

| Tool | Zweck |
|---|---|
| `search_knowledge(query, source_types?, collection?, limit?)` | semantische Suche über alle Quelltypen, optional gefiltert |
| `find_links(query, only_alive?, limit?)` | Link-Snapshots durchsuchen + Bookmark-Status (Erreichbarkeit) |
| `find_related(uri, limit?)` | semantisch verwandte Inhalte zu einem Element (fabric-Stil „associations") |
| `recent_items(limit?, source_types?)` | zuletzt hinzugefügte Elemente (Timeline) |
| `get_document_context(uri, chunk_index, window?)` | benachbarte Chunks einer Fundstelle |

**MCP-Prompts (Patterns):** `summarize`, `extract_wisdom`, `extract_claims`,
`action_items` — kuratierte Analyse-Prompts, in Claude auf eine `uri` anwendbar
(der Server hängt den Volltext an die Anweisung an).

## Verzeichnisstruktur

| Pfad | Inhalt |
|---|---|
| `mykb/` | Python-Paket (geteilte Logik: Embedder, Ingest, Links, Store) |
| `mykb/__main__.py` | CLI (`python -m mykb`) |
| `server/server.py` | MCP-Server (Abfrageseite) |
| `deploy/` | Docker Compose, Traefik, Authelia |
| `docs/` | MkDocs-Dokumentation |
| `data/documents/`, `data/notes/` | Quellen (nicht versioniert) |
| `data/lance/` | LanceDB-Index (generiert, nicht versioniert) |

## Konfiguration

Alles über Environment-Variablen; siehe [`.env.example`](.env.example)
(Pfade, Device, Chunking, Embedding-Dimension, Server, Reranking, HTTP,
Linkwarden).

## Status

- [x] Einheitlicher Index (documents) für document/note/web/link
- [x] Inkrementelles Upsert über `uri` + `content_hash`
- [x] Web-Ingestion (HTML → Text)
- [x] Linkwarden-Connector + Link-Rot-Prüfung
- [x] Bessere Web-Extraktion (trafilatura, bs4-Fallback)
- [x] MCP-Server: `search_knowledge`, `find_links`, `find_related`, `recent_items`, `get_document_context`
- [x] KI-Anreicherung beim Ingest (Zusammenfassung + Auto-Tags via Ollama) — fabric-inspiriert
- [x] „Patterns" als MCP-Prompts (summarize, extract_wisdom, …)
- [x] Auto-Sammlungen (Themen-Clustering) + Timeline
- [ ] Breitere Capture-Quellen (Readwise, YouTube-Transkripte, OCR)
- [ ] Reranking-Stufe (gte-multilingual-reranker) produktiv
- [ ] VPS-Sync festlegen (rsync vs. S3) und automatisieren
- [ ] `deploy/` produktiv härten (alle Daten remote → Absicherung kritisch)
- [ ] Planmäßige Link-Prüfung (Cron/systemd-Timer)
