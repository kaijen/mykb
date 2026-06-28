"""LanceDB-Zugriff: Verbindung, Tabellen, Upsert und Abfragen.

Upsert ist inkrementell über ``uri`` (documents) bzw. ``id`` (links):
bestehende Zeilen werden gelöscht und neu geschrieben. Ein Re-Index darf so den
Link-Status nicht verlieren — Liveness-Felder liegen in der separaten
``links``-Tabelle.
"""
from __future__ import annotations

import structlog

from . import schema
from .config import Config, DOCS_TABLE, LINKS_TABLE

logger = structlog.get_logger()

# Obergrenze für reine Metadaten-Scans (persönlicher Maßstab, unkritisch).
_MAX_SCAN = 1_000_000


def _sql_str(value: str) -> str:
    """Einfaches Escaping für String-Literale in LanceDB-Filtern."""
    return value.replace("'", "''")


def connect(cfg: Config):
    import lancedb

    return lancedb.connect(cfg.db_path)


def ensure_documents(db, dim: int):
    if DOCS_TABLE not in db.table_names():
        db.create_table(DOCS_TABLE, schema=schema.documents_schema(dim))
    return db.open_table(DOCS_TABLE)


def ensure_links(db):
    if LINKS_TABLE not in db.table_names():
        db.create_table(LINKS_TABLE, schema=schema.links_schema())
    return db.open_table(LINKS_TABLE)


# --- documents ---------------------------------------------------------------

def existing_hash(table, uri: str) -> str | None:
    """content_hash einer bereits indexierten Quelle, sonst None."""
    rows = (
        table.search()
        .where(f"uri = '{_sql_str(uri)}'")
        .select(["content_hash"])
        .limit(1)
        .to_list()
    )
    return rows[0]["content_hash"] if rows else None


def upsert_by_uri(table, uri: str, records: list[dict]) -> None:
    """Alle Chunks einer Quelle ersetzen (delete + add)."""
    table.delete(f"uri = '{_sql_str(uri)}'")
    if records:
        table.add(records)


def context_rows(table, uri: str, lo: int, hi: int) -> list[dict]:
    flt = (
        f"uri = '{_sql_str(uri)}' "
        f"AND chunk_index >= {lo} AND chunk_index <= {hi}"
    )
    rows = (
        table.search()
        .where(flt)
        .select(list(schema.DOC_FIELDS))
        .limit(hi - lo + 1)
        .to_list()
    )
    rows.sort(key=lambda r: r.get("chunk_index", 0))
    return rows


def search(table, vector, top_k: int, where: str | None = None) -> list[dict]:
    query = table.search(vector).limit(top_k).select(list(schema.DOC_FIELDS))
    if where:
        query = query.where(where, prefilter=True)
    return query.to_list()


def vector_for_uri(table, uri: str):
    """Repräsentativer Vektor einer Quelle (erster Chunk), sonst None."""
    rows = (
        table.search()
        .where(f"uri = '{_sql_str(uri)}'")
        .select(["vector"])
        .limit(1)
        .to_list()
    )
    return rows[0]["vector"] if rows else None


def related(table, uri: str, top_k: int) -> list[dict]:
    """Semantisch verwandte Inhalte zu ``uri`` (fabric-Stil „associations").

    Sucht über den Vektor der Quelle, schließt die Quelle selbst aus und gibt
    je Fundstelle (uri) nur den nächstgelegenen Chunk zurück.
    """
    vector = vector_for_uri(table, uri)
    if vector is None:
        return []
    rows = search(table, vector, top_k, where=f"uri != '{_sql_str(uri)}'")
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        ruri = row.get("uri", "")
        if ruri in seen:
            continue
        seen.add(ruri)
        out.append(row)
    return out


# --- links -------------------------------------------------------------------

def upsert_link(table, record: dict) -> None:
    table.delete(f"id = '{_sql_str(record['id'])}'")
    table.add([record])


def all_links(table) -> list[dict]:
    return (
        table.search().select(list(schema.LINK_FIELDS)).limit(_MAX_SCAN).to_list()
    )


def links_by_url(table) -> dict[str, dict]:
    """Mapping url -> Link-Metadaten (für find_links)."""
    return {r["url"]: r for r in all_links(table)}
