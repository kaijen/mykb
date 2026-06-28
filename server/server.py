#!/usr/bin/env python3
"""
FastMCP-Server über den LanceDB-Index der Literatursammlung.

Stellt drei Tools bereit:
  - search_standards          Semantische Suche in Tabelle "standards"
  - search_risk_management    Semantische Suche in Tabelle "risk_papers"
  - get_document_context      Benachbarte Chunks eines Dokuments holen

Das Query-Embedding spiegelt die asymmetrische Qwen3-Konvention aus
``scripts/index_literature.py``: Passages werden ohne Prefix kodiert, Queries
mit Instruction-Prefix. Beide Seiten MÜSSEN dasselbe Modell und dieselbe
(ggf. per ``EMBED_DIM`` gekürzte) Dimension verwenden — sonst sind die
Vektoren nicht vergleichbar.

Optional lässt sich über ``RERANK_MODEL`` eine Cross-Encoder-Reranking-Stufe
zuschalten: Top-K aus LanceDB holen, neu sortieren, Top-N zurückgeben.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

import structlog
from mcp.server.fastmcp import FastMCP

logger = structlog.get_logger()

# Muss identisch zum Indexer sein (siehe scripts/index_literature.py).
EMBED_MODEL = "Qwen/Qwen3-Embedding-0.6B"
QUERY_INSTRUCTION = (
    "Given a search query, retrieve relevant passages from "
    "information security standards and risk management literature"
)

# Felder, die wir an den Client zurückgeben (Vektor wird bewusst weggelassen).
RESULT_FIELDS = (
    "id",
    "title",
    "source",
    "type",
    "content",
    "file_path",
    "file_hash",
    "chunk_index",
    "pages",
)


@dataclass
class ServerConfig:
    db_path: str = os.getenv("LANCE_DB_PATH", "/data/lance")
    device: str = os.getenv("EMBED_DEVICE", "cuda")
    embed_dim: int | None = (
        int(os.environ["EMBED_DIM"]) if os.getenv("EMBED_DIM") else None
    )
    host: str = os.getenv("MCP_HOST", "0.0.0.0")
    port: int = int(os.getenv("MCP_PORT", "8000"))
    # Wie viele Kandidaten LanceDB liefert (vor optionalem Reranking).
    top_k: int = int(os.getenv("SEARCH_TOP_K", "20"))
    # Wie viele Treffer am Ende zurückgehen.
    return_k: int = int(os.getenv("SEARCH_RETURN_K", "5"))
    rerank_model: str | None = os.getenv("RERANK_MODEL") or None
    rerank_device: str = os.getenv("RERANK_DEVICE", "cpu")


CFG = ServerConfig()


class QueryEmbedder:
    """Kodiert Queries mit dem Qwen3-Instruction-Prefix (asymmetrisch)."""

    def __init__(self, cfg: ServerConfig):
        from sentence_transformers import SentenceTransformer

        logger.info("loading_model", model=EMBED_MODEL, device=cfg.device)
        self.model = SentenceTransformer(
            EMBED_MODEL,
            device=cfg.device,
            model_kwargs={"torch_dtype": "float16"},
            truncate_dim=cfg.embed_dim,
        )

    def encode(self, query: str):
        return self.model.encode(
            query,
            prompt=f"Instruct: {QUERY_INSTRUCTION}\nQuery: {query}",
            normalize_embeddings=True,
            convert_to_numpy=True,
        )


class Reranker:
    """Optionaler Cross-Encoder. Sortiert (query, passage)-Paare um."""

    def __init__(self, cfg: ServerConfig):
        from sentence_transformers import CrossEncoder

        logger.info("loading_reranker", model=cfg.rerank_model, device=cfg.rerank_device)
        self.model = CrossEncoder(
            cfg.rerank_model,
            device=cfg.rerank_device,
            trust_remote_code=True,
        )

    def order(self, query: str, rows: list[dict]) -> list[dict]:
        if not rows:
            return rows
        scores = self.model.predict([(query, r["content"]) for r in rows])
        ranked = sorted(zip(rows, scores), key=lambda rs: rs[1], reverse=True)
        return [r for r, _ in ranked]


# Modelle erst beim ersten Tool-Aufruf laden (langer Start, knappes VRAM).
@lru_cache(maxsize=1)
def get_embedder() -> QueryEmbedder:
    return QueryEmbedder(CFG)


@lru_cache(maxsize=1)
def get_reranker() -> Reranker | None:
    if not CFG.rerank_model:
        return None
    try:
        return Reranker(CFG)
    except Exception as exc:  # defensiv: Reranking ist optional, Suche läuft weiter
        logger.error("reranker_load_failed", error=str(exc))
        return None


@lru_cache(maxsize=1)
def get_db():
    import lancedb

    return lancedb.connect(CFG.db_path)


def _project(row: dict) -> dict:
    """Nur die Client-relevanten Felder, ohne den Vektor."""
    return {k: row.get(k) for k in RESULT_FIELDS}


def _search(table_name: str, query: str, limit: int | None) -> list[dict]:
    """Vektorsuche + optionales Reranking gegen eine Tabelle."""
    return_k = limit or CFG.return_k
    db = get_db()
    if table_name not in db.table_names():
        logger.warning("table_missing", table=table_name)
        return []

    qvec = get_embedder().encode(query)
    table = db.open_table(table_name)
    # Mehr Kandidaten holen, falls ein Reranker nachsortiert.
    candidates = table.search(qvec).limit(CFG.top_k).to_list()

    reranker = get_reranker()
    if reranker is not None:
        candidates = reranker.order(query, candidates)

    # Query nur gekürzt loggen (keine Klartext-Queries, siehe Konventionen).
    logger.info(
        "search",
        table=table_name,
        query_preview=query[:40],
        candidates=len(candidates),
        reranked=reranker is not None,
    )
    return [_project(r) for r in candidates[:return_k]]


mcp = FastMCP("literatur-rag")


@mcp.tool()
def search_standards(query: str, limit: int | None = None) -> list[dict]:
    """Durchsucht Information-Security-Standards (ISO, BSI, NIST).

    Args:
        query: Suchanfrage in natürlicher Sprache (DE oder EN).
        limit: Anzahl der Treffer (Default aus SEARCH_RETURN_K).
    """
    return _search("standards", query, limit)


@mcp.tool()
def search_risk_management(query: str, limit: int | None = None) -> list[dict]:
    """Durchsucht die Risikomanagement-Literatur (Risk-Paper).

    Args:
        query: Suchanfrage in natürlicher Sprache (DE oder EN).
        limit: Anzahl der Treffer (Default aus SEARCH_RETURN_K).
    """
    return _search("risk_papers", query, limit)


@mcp.tool()
def get_document_context(
    file_hash: str,
    chunk_index: int,
    window: int = 2,
    table: str = "standards",
) -> list[dict]:
    """Liefert benachbarte Chunks eines Dokuments für mehr Kontext.

    Holt die Chunks ``chunk_index - window`` bis ``chunk_index + window``
    desselben Dokuments (identifiziert über ``file_hash``), nach
    ``chunk_index`` sortiert.

    Args:
        file_hash: SHA-256 des Quelldokuments (aus einem Suchtreffer).
        chunk_index: Mittlerer Chunk, um den herum Kontext geholt wird.
        window: Anzahl Chunks vor und nach dem mittleren Chunk.
        table: "standards" oder "risk_papers".
    """
    db = get_db()
    if table not in db.table_names():
        logger.warning("table_missing", table=table)
        return []

    lo = max(chunk_index - window, 0)
    hi = chunk_index + window
    safe_hash = file_hash.replace("'", "")  # simple Escaping für den Filter
    rows = (
        db.open_table(table)
        .search()
        .where(
            f"file_hash = '{safe_hash}' "
            f"AND chunk_index >= {lo} AND chunk_index <= {hi}"
        )
        .limit(2 * window + 1)
        .to_list()
    )
    rows.sort(key=lambda r: r.get("chunk_index", 0))
    return [_project(r) for r in rows]


def main() -> None:
    logger.info(
        "server_start",
        db_path=CFG.db_path,
        host=CFG.host,
        port=CFG.port,
        rerank=bool(CFG.rerank_model),
    )
    mcp.settings.host = CFG.host
    mcp.settings.port = CFG.port
    # SSE-Transport für Remote-Zugriff (hinter Traefik/Authelia, siehe deploy/).
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
