# Architektur & Modelle

## Hardware und Arbeitsteilung

Lokaler Betrieb auf einer GPU mit **4 GB VRAM** und **64 GB RAM**. Der **VRAM
ist der Engpass**, nicht der RAM. Daraus folgt:

- Embedding und Reranking laufen auf der **GPU** (knappes Budget, FP16).
- LLM-Summaries (Ollama) laufen auf **CPU/RAM**, um nicht um VRAM zu
  konkurrieren.
- Bei der Indexierung erst alle Embeddings (GPU), dann Summaries (CPU).

## Modellwahl

Im Consulting-Kontext zählt die **kommerzielle Lizenzierbarkeit**. Daher
ausschließlich Apache-2.0-Modelle:

| Rolle | Modell | Lizenz | VRAM (FP16) | Begründung |
|---|---|---|---|---|
| Embedder | `Qwen/Qwen3-Embedding-0.6B` | Apache 2.0 | ~1,2 GB | DE+EN nativ, 32k Kontext, Matryoshka |
| Embedder (Qualität) | `boboliu/Qwen3-Embedding-4B-W4A16-G128` | Apache 2.0 | ~2,5 GB | bessere Treffer, dann Reranker auf CPU |
| Reranker | `Alibaba-NLP/gte-multilingual-reranker-base` | Apache 2.0 | ~0,6 GB | kommerziell nutzbar, multilingual |

!!! warning "Bewusst nicht verwendet"
    `jinaai/jina-reranker-v2-base-multilingual` (cc-by-nc-4.0,
    non-commercial) und `all-MiniLM-L6-v2` (nur Englisch).

## Asymmetrisches Embedding

Qwen3 ist **asymmetrisch**: *Queries* bekommen einen Instruction-Prefix,
*Passages* nicht.

- Beim **Indexieren** (`Embedder.encode_passages`) werden Dokumente ohne Prefix
  kodiert.
- Beim **Suchen** (`server/server.py`) wird der Prefix gespiegelt:

  ```
  Instruct: Given a search query, retrieve relevant passages from
  information security standards and risk management literature
  Query: <die eigentliche Anfrage>
  ```

Beide Seiten nutzen dasselbe Modell und dieselbe (ggf. per `EMBED_DIM`
gekürzte) Dimension — sonst sind die Vektoren nicht vergleichbar.

## Stack

| Komponente | Technologie |
|---|---|
| Vektor-DB | LanceDB (serverless, lokale Dateien) |
| Embeddings | sentence-transformers + Qwen3 |
| MCP-Server | FastMCP (Python), SSE-Transport |
| Container | Docker Compose |
| Reverse Proxy | Traefik (ACME/Let's Encrypt) |
| Auth | Authelia (Forward-Auth, 2FA) |
| Logging | structlog (JSON) |

## Offene Punkte

1. **Reranking** produktiv schalten (Top-20 → Top-5 mit gte-reranker).
2. **Hybrid-Retrieval** prüfen: BGE-M3 (dense + sparse) für exakte Fachbegriffe
   wie „ISO 27001 Annex A.8".
3. **Deploy** mit Traefik + Authelia produktiv härten.
4. **Inkrementelles Indexieren**: statt Neuaufbau Upsert über `file_hash`.

Details und Begründungen stehen in der `CLAUDE.md` im Repository.
