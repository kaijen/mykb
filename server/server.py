#!/usr/bin/env python3
"""
FastMCP-Server über den LanceDB-Wissensspeicher (Abfrageseite, VPS).

Tools:
  - search_knowledge        Semantische Suche über alle Quelltypen
  - find_links              Link-Snapshots durchsuchen + Bookmark-Status
  - get_document_context    Benachbarte Chunks einer Fundstelle

Das Query-Embedding nutzt den asymmetrischen Qwen3-Prefix aus
``mykb/embedder.py`` (geteilt mit der Ingestion). Optionales Reranking über
``RERANK_MODEL``.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import structlog

# Paket mykb auffindbar machen, wenn der Server direkt gestartet wird.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from mykb import store
from mykb.config import DOCS_TABLE, SOURCE_TYPES, load_config
from mykb.embedder import Embedder
from mykb.patterns import PATTERNS
from mykb.status import collect_status

logger = structlog.get_logger()

CFG = load_config()


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder(CFG)


@lru_cache(maxsize=1)
def get_db():
    return store.connect(CFG)


@lru_cache(maxsize=1)
def get_documents():
    db = get_db()
    if DOCS_TABLE not in db.table_names():
        return None
    return db.open_table(DOCS_TABLE)


class _Reranker:
    def __init__(self):
        from sentence_transformers import CrossEncoder

        logger.info("loading_reranker", model=CFG.rerank_model, device=CFG.rerank_device)
        self.model = CrossEncoder(
            CFG.rerank_model, device=CFG.rerank_device, trust_remote_code=True
        )

    def order(self, query: str, rows: list[dict]) -> list[dict]:
        if not rows:
            return rows
        scores = self.model.predict([(query, r["content"]) for r in rows])
        ranked = sorted(
            zip(rows, scores, strict=True), key=lambda rs: rs[1], reverse=True
        )
        return [r for r, _ in ranked]


@lru_cache(maxsize=1)
def get_reranker() -> _Reranker | None:
    if not CFG.rerank_model:
        return None
    try:
        return _Reranker()
    except Exception as exc:  # defensiv: Reranking optional, Suche läuft weiter
        logger.error("reranker_load_failed", error=str(exc))
        return None


def _quote_list(values: list[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def _run_search(query: str, where: str | None, limit: int | None) -> list[dict]:
    table = get_documents()
    if table is None:
        logger.warning("table_missing", table=DOCS_TABLE)
        return []

    qvec = get_embedder().encode_query(query)
    candidates = store.search(table, qvec, CFG.top_k, where=where)

    reranker = get_reranker()
    if reranker is not None:
        candidates = reranker.order(query, candidates)

    logger.info(
        "search",
        query_preview=query[:40],
        candidates=len(candidates),
        reranked=reranker is not None,
        filtered=bool(where),
    )
    return candidates[: (limit or CFG.return_k)]


mcp = FastMCP("mykb")


@mcp.tool()
def search_knowledge(
    query: str,
    source_types: list[str] | None = None,
    collection: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Semantische Suche über den persönlichen Wissensspeicher.

    Args:
        query: Suchanfrage in natürlicher Sprache (DE oder EN).
        source_types: optional auf ``document``/``note``/``web``/``link``
            einschränken.
        collection: optional auf eine Sammlung einschränken.
        limit: Anzahl Treffer (Default aus SEARCH_RETURN_K).
    """
    clauses: list[str] = []
    if source_types:
        valid = [s for s in source_types if s in SOURCE_TYPES]
        if valid:
            clauses.append(f"source_type IN ({_quote_list(valid)})")
    if collection:
        clauses.append("collection = '" + collection.replace("'", "''") + "'")
    where = " AND ".join(clauses) if clauses else None
    return _run_search(query, where, limit)


@mcp.tool()
def find_links(
    query: str, only_alive: bool = True, limit: int | None = None
) -> list[dict]:
    """Durchsucht gespeicherte Links (Snapshots) und liefert Bookmark-Metadaten
    inklusive Erreichbarkeitsstatus.

    Args:
        query: Suchanfrage in natürlicher Sprache.
        only_alive: bekannt tote Links (``broken``/``timeout``/``error``)
            ausblenden. Ungeprüfte (``unchecked``) und erreichbare (``ok``)
            Links werden zurückgegeben.
        limit: Anzahl Treffer (Default aus SEARCH_RETURN_K).
    """
    hits = _run_search(query, "source_type = 'link'", limit)

    db = get_db()
    meta = store.links_by_url(store.ensure_links(db))

    results: list[dict] = []
    for hit in hits:
        link = meta.get(hit.get("url", ""), {})
        status = link.get("status", "unchecked")
        # „alive" = nicht bekannt tot. Ungeprüfte (unchecked) Links bleiben
        # sichtbar — frisch synchronisierte Links wären sonst unauffindbar,
        # bis 'mykb links check' lief.
        if only_alive and status in {"broken", "timeout", "error"}:
            continue
        results.append(
            {
                "url": hit.get("url"),
                "title": hit.get("title"),
                "content": hit.get("content"),
                "tags": link.get("tags", []),
                "status": status,
                "last_checked": link.get("last_checked", ""),
            }
        )
    return results


@mcp.tool()
def find_related(uri: str, limit: int | None = None) -> list[dict]:
    """Semantisch verwandte Inhalte zu einem Element („associations").

    Liefert andere Dokumente/Notizen/Links zum selben Thema — nützlich, um von
    einer Fundstelle aus Zusammenhänge im Wissensspeicher zu entdecken.

    Args:
        uri: Quell-Kennung des Ausgangselements (Dateipfad oder URL).
        limit: Anzahl verwandter Elemente (Default aus SEARCH_RETURN_K).
    """
    table = get_documents()
    if table is None:
        return []
    rows = store.related(table, uri, CFG.top_k)
    return rows[: (limit or CFG.return_k)]


@mcp.tool()
def kb_status() -> dict:
    """Betrieblicher Status des Wissensspeichers: Bestände je Quelltyp,
    Link-Status, Queue-Rückstand sowie letzter Verarbeitungs-/Sync-Zeitpunkt.
    Spiegelt den Stand des Knotens, auf dem der Server läuft.
    """
    return collect_status(CFG)


@mcp.tool()
def recent_items(limit: int = 20, source_types: list[str] | None = None) -> list[dict]:
    """Zuletzt hinzugefügte Elemente (Timeline) über alle Quelltypen.

    Args:
        limit: maximale Anzahl Elemente.
        source_types: optional auf ``document``/``note``/``web``/``link``
            einschränken.
    """
    table = get_documents()
    if table is None:
        return []
    valid = [s for s in (source_types or []) if s in SOURCE_TYPES] or None
    return store.recent_items(table, limit, valid)


@mcp.tool()
def get_document_context(uri: str, chunk_index: int, window: int = 2) -> list[dict]:
    """Liefert benachbarte Chunks einer Fundstelle für mehr Kontext.

    Args:
        uri: Quell-Kennung aus einem Treffer (Dateipfad oder URL).
        chunk_index: mittlerer Chunk.
        window: Anzahl Chunks davor und danach.
    """
    table = get_documents()
    if table is None:
        return []
    lo = max(chunk_index - window, 0)
    hi = chunk_index + window
    return store.context_rows(table, uri, lo, hi)


def _register_patterns() -> None:
    """Kuratierte Patterns als MCP-Prompts bereitstellen.

    Jeder Prompt lädt den Volltext der angegebenen ``uri`` und hängt ihn an die
    Pattern-Anweisung an; Claude führt die Transformation aus.
    """

    def make(instruction: str):
        def prompt(uri: str) -> str:
            table = get_documents()
            text = store.document_text(table, uri) if table is not None else ""
            if not text:
                return f"{instruction}\n\n(Kein Inhalt zu uri={uri!r} gefunden.)"
            return f"{instruction}\n\n---\n{text}"

        return prompt

    for name, spec in PATTERNS.items():
        mcp.prompt(name=name, description=spec["description"])(make(spec["instruction"]))


_register_patterns()


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
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
