# CLAUDE.md

Projektkontext für Claude Code. Diese Datei wird bei jeder Session automatisch
geladen. Antworten und Kommentare auf Deutsch, deutsche typographische
Anführungszeichen.

## Zweck

**mykb** ist ein selbst gehosteter, persönlicher Wissensspeicher (Personal
Knowledge Management). Eigene Dokumente, Notizen, Web-Inhalte und eine
Linksammlung werden mit semantischen Embeddings in LanceDB indexiert und über
einen MCP-Server im Alltag aus Claude (VSCode, Claude Desktop) nutzbar gemacht.

Es werden vier Quelltypen verwaltet:

- **document** — lokale Dateien (PDF, Markdown, Text)
- **note** — eigene Notizen (Markdown, Zettelkasten/Obsidian-Stil)
- **web** — abgerufene Web-Inhalte (HTML → Text, eingebettet)
- **link** — Bookmarks mit Snapshot des Seiteninhalts und regelmäßiger
  Erreichbarkeitsprüfung (Link-Rot)

Einsatz auch im Consulting-Kontext, daher zählt die kommerzielle
Lizenzierbarkeit aller Modelle (Apache 2.0).

## Betriebsmodell: Erstellen vs. Abfragen

Bewusste Trennung der beiden Seiten:

- **Erstellen (Laptop, GPU):** Ingestion (Dokumente/Notizen/Web), Embedding
  (Qwen3, FP16), Pflege der Linksammlung und Link-Rot-Prüfung. Erzeugt die
  LanceDB-Dateien (`documents`, `links`). Erreichbar von unterwegs über das
  bestehende **Tailscale**-Netz: ein Capture-Dienst (`mykb capture`) nimmt
  Dateien und Links als Inbox entgegen (Datei → Quellordner, Link → Linkwarden),
  veröffentlicht via `tailscale serve` (nur Tailnet, kein Token). Verarbeitung
  per `mykb process`.
- **Abfragen (VPS, CPU):** Der MCP-Server beantwortet Queries. Er braucht
  denselben Embedder für das **Query-Embedding** (asymmetrisch). Qwen3-0.6B auf
  CPU ist für einzelne Queries schnell genug.

Entscheidung: **alle Daten** werden auf den VPS synchronisiert (kein
Sichtbarkeits-Flag). Damit ist die Absicherung des VPS (Authelia 2FA, TLS,
Rate Limiting) Pflicht — siehe „Sicherheit / Datenhaltung".

Der **Sync-Mechanismus** (rsync über SSH vs. Object Storage) ist noch offen.
Vorerst wird lokal gebaut und betrieben; LanceDB sind nur Dateien und damit
später leicht zu synchronisieren.

## Hardware

Lokaler Betrieb. GPU mit 4 GB VRAM, 64 GB System-RAM. Der VRAM ist der
Engpass, nicht der RAM. Daraus folgt die Arbeitsteilung:

- Embedding und Reranking laufen auf der GPU (knappes Budget, FP16).
- LLM-Summaries (Ollama) laufen auf CPU/RAM, um nicht um VRAM zu konkurrieren.
- Bei der Indexierung erst alle Embeddings (GPU), dann Summaries (CPU).

## Modellwahl

| Rolle | Modell | Lizenz | VRAM (FP16) | Begründung |
|---|---|---|---|---|
| Embedder | `Qwen/Qwen3-Embedding-0.6B` | Apache 2.0 | ~1,2 GB | DE+EN nativ, 32k Kontext, Matryoshka |
| Embedder (Qualität) | `boboliu/Qwen3-Embedding-4B-W4A16-G128` | Apache 2.0 | ~2,5 GB | bessere Treffer, dann Reranker auf CPU |
| Reranker | `Alibaba-NLP/gte-multilingual-reranker-base` | Apache 2.0 | ~0,6 GB | kommerziell nutzbar, multilingual |

Lizenzpolitik (gelockert): Für **selbst gehostete Tooling-Bibliotheken** sind
auch Copyleft-Lizenzen (z. B. trafilatura, GPLv3) in Ordnung — kein Vertrieb,
nur Eigenbetrieb. Bei **Modellen**, die in bezahlter Beratung Ergebnisse
liefern, bleibt eine kommerziell nutzbare Lizenz die Voreinstellung; ein
non-commercial Modell wie `jinaai/jina-reranker-v2-base-multilingual`
(cc-by-nc-4.0) ist nur als optionale Alternative für rein private Nutzung
gedacht. `all-MiniLM-L6-v2` bleibt ungenutzt (englisch only).

Qwen3 ist asymmetrisch: Queries bekommen einen Instruction-Prefix, Passages
nicht. Diese Logik steckt zentral in `mykb/embedder.py` und wird sowohl beim
Indexieren (Passages) als auch serverseitig (Query) genutzt.

## Stack

- Vektor-DB: LanceDB (serverless, lokale Dateien, keine Cloud)
- Embeddings: sentence-transformers + Qwen3
- Web-Extraktion: httpx + trafilatura (Hauptinhalt), BeautifulSoup als Fallback
- MCP-Server: FastMCP (Python), SSE-Transport für Remote-Zugriff
- Container: Docker Compose
- Reverse Proxy: Traefik (ACME/Let's Encrypt)
- Auth: Authelia (Forward Auth, 2FA) — Alternative Keycloak verworfen (zu schwer)
- Logging: structlog (JSON)

## Verzeichnisstruktur

```
mykb/
├── CLAUDE.md                  # diese Datei
├── requirements.txt
├── mykb/                      # Python-Paket (geteilte Logik)
│   ├── config.py              # Konfiguration aus Environment
│   ├── embedder.py            # Qwen3, asymmetrisch (Ingest + Server)
│   ├── schema.py              # LanceDB-Schemata (documents, links)
│   ├── extract.py             # PDF/MD/TXT + Web (HTML → Text)
│   ├── store.py               # LanceDB: connect, Upsert, Query
│   ├── ingest.py              # Dokumente/Notizen/Web → Tabelle documents
│   ├── links.py               # Linkwarden-Connector + Erreichbarkeitsprüfung
│   ├── enrich.py              # KI-Anreicherung (Ollama): summary + Auto-Tags
│   ├── collections.py         # Auto-Sammlungen (Clustering)
│   ├── patterns.py            # kuratierte Analyse-Prompts (MCP-Prompts)
│   ├── capture.py             # Capture-Dienst (Erfassen von unterwegs)
│   └── __main__.py            # CLI: index, web, links, process, capture ...
├── server/
│   └── server.py              # MCP-Server (Abfrageseite, VPS)
├── deploy/                    # Docker, Traefik, Authelia
├── docs/                      # MkDocs-Dokumentation
└── data/
    ├── documents/             # lokale Dokumente (document)
    ├── notes/                 # eigene Notizen (note)
    └── lance/                 # LanceDB-Index (documents, links)
```

## LanceDB-Schema

**Tabelle `documents`** (einheitlicher Inhaltsindex über alle Quelltypen):
`id, source_type, collection, tags, title, source, url, content, summary, uri,
content_hash, chunk_index, n_chunks, pages, indexed_at, vector`.

- `summary`: optionale KI-Zusammenfassung (nur mit `--enrich`/`ENRICH=1`)

- `source_type`: `document` | `note` | `web` | `link`
- `collection`: frei belegbare Sammlung (z. B. aus Unterordner oder beim
  Hinzufügen gesetzt)
- `uri`: stabile Quell-Kennung (Dateipfad bzw. URL) — Upsert-Schlüssel
- `content_hash`: SHA-256 über den Quellinhalt (Dedup / Änderungserkennung)

**Tabelle `links`** (Bookmark-Verwaltung):
`id, url, title, tags, note, added_at, last_checked, status, http_status,
final_url, last_ok_at, content_hash`.

- `status`: `ok` | `broken` | `redirect` | `timeout` | `error` | `unchecked`
- Der Seiten-Snapshot eines Links liegt als `source_type = link` in
  `documents` und ist damit semantisch durchsuchbar.

Dimension stammt aus dem Modell (Qwen3-0.6B: 1024, optional per `EMBED_DIM`
via Matryoshka gekürzt). Modellwechsel, Dimensions- oder Schema-Änderung
(z. B. neues Feld) = Tabelle neu aufbauen.

## Befehle

```bash
pip install -r requirements.txt

# Indexieren (alle lokalen Quellen / nur Dokumente / nur Notizen)
python -m mykb index --source all
python -m mykb index --source documents
python -m mykb index --source notes

# Web-Inhalt / Link aufnehmen (Snapshot wird abgerufen und indexiert)
python -m mykb add-url https://example.org/artikel --tags infosec,lesen --note "..."

# Linksammlung verwalten
python -m mykb links list
python -m mykb links list --broken
python -m mykb links check                     # Erreichbarkeit prüfen (Link-Rot)

# KI-Anreicherung beim Ingest (Zusammenfassung + Auto-Tags via Ollama)
python -m mykb index --source all --enrich

# Auto-Sammlungen (Themen-Cluster vorschlagen / anwenden)
python -m mykb collections --threshold 0.6
python -m mykb collections --apply

# Erfassen von unterwegs (Tailscale): Dienst starten, dann Inbox verarbeiten
python -m mykb capture                         # 127.0.0.1:8765 (tailscale serve davor)
python -m mykb process                         # index (documents+notes) + links sync

# Optionen analog zur Indexierung
EMBED_DIM=512 python -m mykb index --source all
EMBED_DEVICE=cpu python -m mykb index --source all

# MCP-Server (Abfrageseite)
python server/server.py
```

## Konfiguration (Environment)

`LANCE_DB_PATH`, `SOURCE_DOCS_PATH`, `NOTES_PATH`, `EMBED_DEVICE` (cuda/cpu),
`EMBED_BATCH_SIZE`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `EMBED_DIM`,
`MCP_HOST`, `MCP_PORT`, `CAPTURE_HOST`, `CAPTURE_PORT`,
`SEARCH_TOP_K`, `SEARCH_RETURN_K`,
`RERANK_MODEL`, `RERANK_DEVICE`,
`HTTP_TIMEOUT`, `HTTP_USER_AGENT`, `LINK_CHECK_CONCURRENCY`,
`ENRICH`, `OLLAMA_URL`, `OLLAMA_MODEL`, `ENRICH_MAX_CHARS`,
`LINKWARDEN_URL`, `LINKWARDEN_TOKEN`.

## MCP-Tools

1. `search_knowledge(query, source_types?, collection?, limit?)` — semantische
   Suche über `documents`, optional gefiltert nach Quelltyp/Sammlung.
2. `find_links(query, only_alive?, limit?)` — durchsucht Link-Snapshots und
   liefert Bookmark-Metadaten inkl. Erreichbarkeitsstatus.
3. `find_related(uri, limit?)` — semantisch verwandte Inhalte zu einem Element
   (fabric-Stil „associations"), zum Entdecken von Zusammenhängen.
4. `recent_items(limit?, source_types?)` — zuletzt hinzugefügte Elemente
   (Timeline).
5. `get_document_context(uri, chunk_index, window?)` — benachbarte Chunks einer
   Fundstelle für mehr Kontext.

Query-Embedding nutzt den Qwen3-Instruction-Prefix (asymmetrisch, siehe
`mykb/embedder.py`).

## MCP-Prompts (Patterns)

Kuratierte Analyse-Prompts (à la Daniel Miesslers „fabric"), in Claude auf eine
`uri` anwendbar — der Server lädt den Volltext und hängt ihn an die Anweisung
an: `summarize`, `extract_wisdom`, `extract_claims`, `action_items`
(siehe `mykb/patterns.py`).

## Offene Punkte

1. Reranking-Stufe produktiv: Top-K aus LanceDB, mit gte-reranker auf Top-N
   sortieren. Reranker-Device abhängig vom Embedder-Budget.
2. Hybrid-Retrieval prüfen: bei Bedarf BGE-M3 statt Qwen3 für dense+sparse,
   um exakte Fachbegriffe (z. B. „ISO 27001 Annex A.8") besser zu treffen.
3. VPS-Sync konkret festlegen (rsync über SSH vs. Object Storage/S3, aus dem
   der VPS LanceDB direkt liest) und automatisieren.
4. `deploy/`: Compose/Traefik/Authelia produktiv härten (alle Daten remote →
   Absicherung kritisch).
5. Web-Snapshots periodisch auffrischen. (Planmäßige Verarbeitung inkl.
   Link-Rot-Prüfung über `mykb process` ist umgesetzt — Vorlagen unter
   `deploy/systemd/` und `deploy/cron/`.)
6. Notizen-Quelle: optional Frontmatter/Tags aus Markdown übernehmen.

### Fabric-inspirierte Ausbaustufen (siehe fabric.so)

Leitidee von fabric.so: alles Gespeicherte wird inhaltlich „verstanden",
automatisch verschlagwortet/verknüpft und per Bedeutung durchsuchbar. Übertragen
auf mykb (lokaler LLM via Ollama, CPU — passt zur Hardware-Arbeitsteilung):

- [x] **KI-Anreicherung beim Ingest:** Zusammenfassung + Auto-Tags via Ollama
  (`mykb/enrich.py`, Feld `summary`, `--enrich`).
- [x] **Patterns (à la Daniel Miesslers „fabric"):** `summarize`,
  `extract_wisdom`, `extract_claims`, `action_items` als MCP-Prompts.
- [x] **Verwandtes/Assoziationen:** `find_related` (Vektor-Nachbarn).
- [x] **Auto-Sammlungen:** Themen-Clustering (`mykb/collections.py`,
  `mykb collections [--apply]`).
- [x] **Timeline:** `recent_items` über `indexed_at`.
- [ ] **Breitere Capture-Quellen:** Readwise-Highlights, YouTube-Transkripte,
  Bilder/Screenshots per OCR (bewusst zurückgestellt).
- [ ] Auto-Sammlungen über bloßes Cosinus-Clustering hinaus (z. B. LLM-Benennung
  der Cluster, k-Means).

## Konventionen

- Python ab 3.11, Type Hints, `from __future__ import annotations`.
- Geteilte Logik liegt im Paket `mykb/`; `scripts/` und `server/` sind dünn.
- Defensive Extraktion: eine fehlerhafte Datei/URL darf den Lauf nicht
  abbrechen.
- Inkrementell per Upsert über `uri` + `content_hash`; ein Re-Index darf den
  Link-Status nicht verlieren.
- Keine Klartext-Queries ins Log (nur gekürzt), keine Secrets ins Log.
- Secrets über Docker Secrets / Environment, nie im Repo.

## Sicherheit / Datenhaltung

Da **alle Daten** auf den VPS synchronisiert werden, können auch private oder
vertrauliche Inhalte remote liegen. Deshalb ist die Absicherung nicht optional:
TLS erzwingen, Authelia 2FA, Rate Limiting, Logging. Für streng vertrauliche
(z. B. NDA-gebundene) Dokumente weiterhin im Zweifel eine getrennte, lokale
Instanz nutzen statt sie auf einen erreichbaren VPS zu legen.
