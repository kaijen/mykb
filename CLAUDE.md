# CLAUDE.md

Projektkontext für Claude Code. Diese Datei wird bei jeder Session automatisch
geladen. Antworten und Kommentare auf Deutsch, deutsche typographische
Anführungszeichen.

## Zweck

Selbst gehostete RAG-Pipeline für eine persönliche Fach-Literatursammlung
(Information Security, Risikomanagement). Die Sammlung wird in LanceDB
indexiert und über einen MCP-Server für Claude (VSCode, Claude Desktop)
durchsuchbar gemacht. Einsatz im Consulting-Kontext, daher zählt kommerzielle
Lizenzierbarkeit aller Modelle.

## Hardware

Lokaler Betrieb. GPU mit 4 GB VRAM, 64 GB System-RAM. Der VRAM ist der
Engpass, nicht der RAM. Daraus folgt die Arbeitsteilung:

- Embedding und Reranking laufen auf der GPU (knappes Budget, FP16).
- LLM-Summaries (Ollama) laufen auf CPU/RAM, um nicht um VRAM zu konkurrieren.
- Bei der Indexierung erst alle Embeddings (GPU), dann Summaries (CPU).

Ein späterer Umzug auf einen VPS ist vorgesehen (siehe `deploy/`), dann ggf.
CPU-only Inferenz mit kleineren Modellen.

## Modellwahl

| Rolle | Modell | Lizenz | VRAM (FP16) | Begründung |
|---|---|---|---|---|
| Embedder | `Qwen/Qwen3-Embedding-0.6B` | Apache 2.0 | ~1,2 GB | DE+EN nativ, 32k Kontext, Matryoshka |
| Embedder (Qualität) | `boboliu/Qwen3-Embedding-4B-W4A16-G128` | Apache 2.0 | ~2,5 GB | bessere Treffer, dann Reranker auf CPU |
| Reranker | `Alibaba-NLP/gte-multilingual-reranker-base` | Apache 2.0 | ~0,6 GB | kommerziell nutzbar, multilingual |

Bewusst NICHT verwendet: `jinaai/jina-reranker-v2-base-multilingual`
(cc-by-nc-4.0, non-commercial) und `all-MiniLM-L6-v2` (englisch only).

Qwen3 ist asymmetrisch: Queries bekommen einen Instruction-Prefix, Passages
nicht. Diese Logik steckt in `scripts/index_literature.py` (`Embedder`-Klasse)
und muss serverseitig beim Query-Embedding gespiegelt werden.

## Stack

- Vektor-DB: LanceDB (serverless, lokale Dateien, keine Cloud)
- Embeddings: sentence-transformers + Qwen3
- MCP-Server: FastMCP (Python), SSE-Transport für Remote-Zugriff
- Container: Docker Compose
- Reverse Proxy: Traefik (ACME/Let's Encrypt)
- Auth: Authelia (Forward Auth, 2FA) — Alternative Keycloak verworfen (zu schwer)
- Logging: structlog (JSON)

## Verzeichnisstruktur

```
literatur-rag/
├── CLAUDE.md                  # diese Datei
├── requirements.txt
├── scripts/
│   └── index_literature.py    # Indexierung in LanceDB (fertig)
├── server/                    # MCP-Server (TODO)
│   └── server.py
├── deploy/                    # Docker, Traefik, Authelia (TODO)
│   ├── docker-compose.yml
│   └── authelia/
└── data/
    ├── literatur/             # Quelldokumente (read-only gemountet)
    │   ├── standards/         # ISO, BSI, NIST  -> Tabelle "standards"
    │   └── research/          # Risk-Paper       -> Tabelle "risk_papers"
    └── lance/                 # LanceDB-Index (generiert)
```

## LanceDB-Schema

Tabelle `standards` und `risk_papers`, beide mit denselben Feldern:
`id, title, source, type, content, file_path, file_hash, chunk_index,
pages, vector`. Das Feld `type` klassifiziert per Dateiname
(iso/bsi/nist/sonstige bzw. bayesian/quantitative/frameworks).

Dimension wird aus dem Modell übernommen (Qwen3-0.6B: 1024, optional per
`EMBED_DIM` via Matryoshka gekürzt). Modellwechsel = neu indexieren.

## Befehle

```bash
# Abhängigkeiten
pip install -r requirements.txt

# Indexieren (alles / nur Standards / nur Research)
python scripts/index_literature.py --target all
python scripts/index_literature.py --target standards

# Mit gekürzter Embedding-Dimension (spart DB-Platz)
EMBED_DIM=512 python scripts/index_literature.py --target all

# CPU statt GPU erzwingen (z. B. für VPS-Test)
EMBED_DEVICE=cpu python scripts/index_literature.py
```

## Konfiguration (Environment)

`LANCE_DB_PATH`, `SOURCE_DOCS_PATH`, `EMBED_DEVICE` (cuda/cpu),
`EMBED_BATCH_SIZE`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `EMBED_DIM`.

## Offene Punkte

1. `server/server.py`: FastMCP-Server mit den Tools `search_standards`,
   `search_risk_management`, `get_document_context`. Query-Embedding muss den
   Qwen3-Instruction-Prefix nutzen (asymmetrisch, siehe Indexer).
2. Reranking-Stufe: Top-20 aus LanceDB holen, mit gte-reranker auf Top-5
   sortieren. Reranker-Device abhängig vom Embedder-Budget wählen.
3. Hybrid-Retrieval prüfen: bei Bedarf BGE-M3 statt Qwen3 für dense+sparse,
   um exakte Fachbegriffe (z. B. „ISO 27001 Annex A.8") besser zu treffen.
4. `deploy/`: Docker Compose mit Traefik-Labels und Authelia Forward-Auth.
5. Inkrementelles Indexieren: aktuell wird die Tabelle pro Lauf neu gebaut.
   Über `file_hash` ließe sich auf Upsert umstellen.

## Konventionen

- Python ab 3.11, Type Hints, `from __future__ import annotations`.
- Defensive Extraktion: eine fehlerhafte Datei darf den Lauf nicht abbrechen.
- Keine Klartext-Queries ins Log (nur gekürzt), keine Secrets ins Log.
- Secrets über Docker Secrets / Environment, nie im Repo.

## Sicherheit / Datenhaltung

Öffentliche Standards und eigene Analysen sind unkritisch. Client-spezifische
oder vertrauliche Dokumente gehören NICHT auf einen externen VPS, sondern
bleiben lokal oder in einer isolierten Instanz mit NDA-konformer Konfiguration.
Beim Remote-Betrieb gilt: TLS erzwingen, Authelia 2FA, Rate Limiting, Logging.
