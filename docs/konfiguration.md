# Konfiguration

Alle Parameter werden über **Environment-Variablen** gesteuert. Vorlage:
[`.env.example`](https://github.com/kaijen/mykb/blob/main/.env.example).

## Pfade

| Variable | Default | Bedeutung |
|---|---|---|
| `LANCE_DB_PATH` | `/data/lance` | Speicherort des LanceDB-Index |
| `SOURCE_DOCS_PATH` | `/data/literatur` | Wurzel der Quelldokumente |

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

!!! tip "VRAM-Budget"
    Der VRAM (4 GB) ist der Engpass. Bewährte Aufteilung: Embedding/Reranking
    auf der GPU, LLM-Summaries (Ollama) auf CPU/RAM. Reicht der VRAM nicht für
    Embedder **und** Reranker, den Reranker mit `RERANK_DEVICE=cpu` betreiben.

## Konsistenz beachten

`EMBED_DEVICE`, `EMBED_DIM` und das Embedding-Modell müssen bei **Indexierung**
und **Server** zusammenpassen. Wird beim Indexieren `EMBED_DIM=512` genutzt,
muss der Server denselben Wert sehen — sonst sind Query- und Passage-Vektoren
unterschiedlich dimensioniert.

Weiter mit dem [Deployment](deployment.md).
