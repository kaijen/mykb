# Konfiguration

Alle Parameter werden über **Environment-Variablen** gesteuert. Vorlage:
[`.env.example`](https://github.com/kaijen/mykb/blob/main/.env.example).

## Pfade

| Variable | Default | Bedeutung |
|---|---|---|
| `LANCE_DB_PATH` | `./data/lance` | Speicherort des LanceDB-Index |
| `SOURCE_DOCS_PATH` | `./data/documents` | Wurzel der lokalen Dokumente |
| `NOTES_PATH` | `./data/notes` | Wurzel der eigenen Notizen |

## Embedding / Indexierung

| Variable | Default | Bedeutung |
|---|---|---|
| `EMBED_DEVICE` | `cuda` | `cuda` (GPU, FP16) oder `cpu` |
| `EMBED_BATCH_SIZE` | `32` | Batchgröße beim Kodieren; bei VRAM-Mangel senken |
| `CHUNK_SIZE` | `500` | Chunk-Länge in Wörtern |
| `CHUNK_OVERLAP` | `50` | Überlappung in Wörtern |
| `EMBED_DIM` | _(leer)_ | Matryoshka-Kürzung; leer = volle Dimension (1024) |

## MCP-Server

| Variable | Default | Bedeutung |
|---|---|---|
| `MCP_HOST` | `0.0.0.0` | Bind-Adresse |
| `MCP_PORT` | `8000` | Port (SSE) |
| `SEARCH_TOP_K` | `20` | Kandidaten aus LanceDB (vor Reranking) |
| `SEARCH_RETURN_K` | `5` | zurückgegebene Treffer |
| `RERANK_MODEL` | _(leer)_ | Reranker-Modell; leer = Reranking aus |
| `RERANK_DEVICE` | `cpu` | Device des Rerankers |

## KI-Anreicherung (Ollama)

| Variable | Default | Bedeutung |
|---|---|---|
| `ENRICH` | `0` | `1` aktiviert Zusammenfassung + Auto-Tags beim Ingest |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama-Endpoint |
| `OLLAMA_MODEL` | `llama3.2` | verwendetes LLM |
| `ENRICH_MAX_CHARS` | `6000` | Eingabetext für die Anreicherung kürzen |

## Web / Linkwarden

| Variable | Default | Bedeutung |
|---|---|---|
| `HTTP_TIMEOUT` | `20` | Timeout (s) für Web-Abruf und Link-Prüfung |
| `HTTP_USER_AGENT` | `mykb/0.1 …` | User-Agent |
| `LINK_CHECK_CONCURRENCY` | `8` | parallele Prüfungen (reserviert) |
| `LINKWARDEN_URL` | _(leer)_ | Basis-URL der Linkwarden-Instanz |
| `LINKWARDEN_TOKEN` | _(leer)_ | API-Token (Secret, nicht ins Repo) |

!!! tip "VRAM-Budget"
    Der VRAM (4 GB) ist der Engpass. Bewährte Aufteilung: Embedding/Reranking
    auf der GPU, LLM-Anreicherung (Ollama) auf CPU/RAM. Reicht der VRAM nicht
    für Embedder **und** Reranker, den Reranker mit `RERANK_DEVICE=cpu` betreiben.

## Konsistenz beachten

`EMBED_DEVICE`, `EMBED_DIM` und das Embedding-Modell müssen bei **Ingestion**
und **Server** zusammenpassen. Wird beim Indexieren `EMBED_DIM=512` genutzt,
muss der Server denselben Wert sehen — sonst sind Query- und Passage-Vektoren
unterschiedlich dimensioniert.

Weiter mit dem [Deployment](deployment.md).
