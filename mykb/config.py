"""Zentrale Konfiguration aus Environment-Variablen.

Eine einzige Quelle der Wahrheit für Ingest, Linksammlung und MCP-Server.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Tabellennamen in LanceDB.
DOCS_TABLE = "documents"
LINKS_TABLE = "links"

# Erlaubte Quelltypen für documents.source_type.
SOURCE_TYPES = ("document", "note", "web", "link")

# Unterstützte Dateiendungen für lokale Quellen.
DOC_SUFFIXES = {".pdf", ".md", ".markdown", ".txt"}


@dataclass
class Config:
    # --- Pfade ---
    db_path: str = os.getenv("LANCE_DB_PATH", "./data/lance")
    docs_path: str = os.getenv("SOURCE_DOCS_PATH", "./data/documents")
    notes_path: str = os.getenv("NOTES_PATH", "./data/notes")

    # --- Embedding ---
    device: str = os.getenv("EMBED_DEVICE", "cuda")
    batch_size: int = int(os.getenv("EMBED_BATCH_SIZE", "32"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "500"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "50"))
    # Matryoshka: None nutzt die volle Dimension (1024). Kürzen spart DB-Platz.
    embed_dim: int | None = (
        int(os.environ["EMBED_DIM"]) if os.getenv("EMBED_DIM") else None
    )

    # --- MCP-Server ---
    host: str = os.getenv("MCP_HOST", "0.0.0.0")
    port: int = int(os.getenv("MCP_PORT", "8000"))
    top_k: int = int(os.getenv("SEARCH_TOP_K", "20"))
    return_k: int = int(os.getenv("SEARCH_RETURN_K", "5"))
    rerank_model: str | None = os.getenv("RERANK_MODEL") or None
    rerank_device: str = os.getenv("RERANK_DEVICE", "cpu")

    # --- Web / Link-Prüfung ---
    http_timeout: float = float(os.getenv("HTTP_TIMEOUT", "20"))
    http_user_agent: str = os.getenv(
        "HTTP_USER_AGENT",
        "mykb/0.1 (+https://github.com/kaijen/mykb)",
    )
    link_check_concurrency: int = int(os.getenv("LINK_CHECK_CONCURRENCY", "8"))


def load_config() -> Config:
    return Config()
