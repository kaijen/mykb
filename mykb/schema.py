"""LanceDB-Schemata und Projektionsfelder für ``documents`` und ``links``.

Das Vektorfeld ist eine fixed-size-Liste; die Dimension stammt zur Laufzeit aus
dem Embedder (Qwen3-0.6B: 1024, optional per ``EMBED_DIM`` gekürzt).
"""
from __future__ import annotations

import pyarrow as pa

# Felder ohne Vektor — für die Rückgabe an Clients (kein Embedding ausliefern).
DOC_FIELDS = (
    "id",
    "source_type",
    "collection",
    "tags",
    "title",
    "source",
    "url",
    "content",
    "summary",
    "uri",
    "content_hash",
    "chunk_index",
    "n_chunks",
    "pages",
    "indexed_at",
)

LINK_FIELDS = (
    "id",
    "url",
    "title",
    "tags",
    "note",
    "added_at",
    "last_checked",
    "status",
    "http_status",
    "final_url",
    "last_ok_at",
    "content_hash",
)


def documents_schema(dim: int) -> pa.Schema:
    return pa.schema(
        [
            ("id", pa.string()),
            ("source_type", pa.string()),
            ("collection", pa.string()),
            ("tags", pa.list_(pa.string())),
            ("title", pa.string()),
            ("source", pa.string()),
            ("url", pa.string()),
            ("content", pa.string()),
            ("summary", pa.string()),
            ("uri", pa.string()),
            ("content_hash", pa.string()),
            ("chunk_index", pa.int32()),
            ("n_chunks", pa.int32()),
            ("pages", pa.int32()),
            ("indexed_at", pa.string()),
            ("vector", pa.list_(pa.float32(), dim)),
        ]
    )


def links_schema() -> pa.Schema:
    return pa.schema(
        [
            ("id", pa.string()),
            ("url", pa.string()),
            ("title", pa.string()),
            ("tags", pa.list_(pa.string())),
            ("note", pa.string()),
            ("added_at", pa.string()),
            ("last_checked", pa.string()),
            ("status", pa.string()),
            ("http_status", pa.int32()),
            ("final_url", pa.string()),
            ("last_ok_at", pa.string()),
            ("content_hash", pa.string()),
        ]
    )
