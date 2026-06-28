"""Ingestion lokaler Dokumente, Notizen und einzelner Web-Inhalte in
``documents``. Inkrementell per Upsert über ``uri`` + ``content_hash``.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog

from . import extract, store, web
from .chunking import chunk_text
from .config import DOC_SUFFIXES, Config
from .embedder import Embedder
from .enrich import Enricher

logger = structlog.get_logger()


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Ingestor:
    """Hält Embedder + offene ``documents``-Tabelle für mehrere Quellen."""

    def __init__(self, cfg: Config, embedder: Embedder | None = None):
        self.cfg = cfg
        self.embedder = embedder or Embedder(cfg)
        self.enricher = Enricher(cfg) if cfg.enrich else None
        self.db = store.connect(cfg)
        self.table = store.ensure_documents(self.db, self.embedder.dim)

    def _build_records(
        self,
        *,
        source_type: str,
        uri: str,
        title: str,
        source: str,
        url: str,
        collection: str,
        tags: list[str],
        summary: str,
        content_hash: str,
        pages: int,
        chunks: list[str],
        vectors,
    ) -> list[dict]:
        ts = _now()
        n = len(chunks)
        records: list[dict] = []
        uri_key = extract.sha256_text(uri)[:16]
        for i, (chunk, vec) in enumerate(zip(chunks, vectors, strict=True)):
            records.append(
                {
                    # id quellenstabil aus uri (nicht content_hash) -> global
                    # eindeutig, auch wenn zwei Quellen denselben Inhalt haben.
                    "id": f"{uri_key}_{i}",
                    "source_type": source_type,
                    "collection": collection,
                    "tags": tags,
                    "title": title,
                    "source": source,
                    "url": url,
                    "content": chunk,
                    "summary": summary,
                    "uri": uri,
                    "content_hash": content_hash,
                    "chunk_index": i,
                    "n_chunks": n,
                    "pages": pages,
                    "indexed_at": ts,
                    "vector": vec.tolist(),
                }
            )
        return records

    def ingest_text(
        self,
        *,
        source_type: str,
        uri: str,
        title: str,
        source: str,
        url: str,
        collection: str,
        tags: list[str],
        text: str,
        content_hash: str,
        pages: int = 0,
    ) -> int:
        """Eine Quelle (bereits extrahiert) inkrementell indexieren.

        Gibt die Anzahl geschriebener Chunks zurück; 0, wenn unverändert oder
        leer.
        """
        if store.existing_hash(self.table, uri) == content_hash:
            logger.info("unchanged_skip", uri=uri)
            return 0

        chunks = chunk_text(text, self.cfg.chunk_size, self.cfg.chunk_overlap)
        if not chunks:
            logger.warning("empty_after_chunk", uri=uri)
            store.upsert_by_uri(self.table, uri, [])  # evtl. alte Chunks entfernen
            return 0

        # KI-Anreicherung (optional): Zusammenfassung + automatische Schlagworte.
        summary = ""
        if self.enricher is not None:
            enr = self.enricher.enrich(text)
            summary = enr.summary
            if enr.tags:
                # eigene Tags zuerst, Auto-Tags ergänzen (dedupliziert).
                merged = list(tags)
                for t in enr.tags:
                    if t not in merged:
                        merged.append(t)
                tags = merged

        vectors = self.embedder.encode_passages(chunks)
        records = self._build_records(
            source_type=source_type,
            uri=uri,
            title=title,
            source=source,
            url=url,
            collection=collection,
            tags=tags,
            summary=summary,
            content_hash=content_hash,
            pages=pages,
            chunks=chunks,
            vectors=vectors,
        )
        store.upsert_by_uri(self.table, uri, records)
        logger.info("ingested", uri=uri, chunks=len(chunks), source_type=source_type)
        return len(chunks)

    def ingest_path(self, root: str | Path, source_type: str) -> int:
        """Alle unterstützten Dateien unter ``root`` indexieren."""
        root = Path(root)
        if not root.exists():
            logger.warning("path_missing", path=str(root))
            return 0

        seen: set[str] = set()
        total = 0
        for path in sorted(root.glob("**/*")):
            if not path.is_file() or path.suffix.lower() not in DOC_SUFFIXES:
                continue
            ex = extract.load_file(path)
            if ex is None:
                continue
            if ex.content_hash in seen:
                logger.info("duplicate_skipped", file=str(path))
                continue
            seen.add(ex.content_hash)
            # Unterordner unterhalb der Wurzel wird zur Sammlung.
            collection = path.parent.name if path.parent != root else ""
            total += self.ingest_text(
                source_type=source_type,
                uri=str(path),
                title=ex.title,
                source=path.name,
                url="",
                collection=collection,
                tags=[],
                text=ex.text,
                content_hash=ex.content_hash,
                pages=ex.pages,
            )
        return total

    def ingest_url(
        self,
        url: str,
        *,
        collection: str = "",
        tags: list[str] | None = None,
        source_type: str = "web",
    ) -> dict | None:
        """Eine einzelne Web-Seite abrufen, extrahieren und indexieren."""
        res = web.fetch(url, self.cfg)
        if not res.ok or not res.html:
            logger.error("fetch_failed", url=url, status=res.status, error=res.error)
            return None
        text, title = extract.html_to_text(res.html)
        if not text.strip():
            logger.warning("no_text", url=url)
            return None
        content_hash = extract.sha256_text(text)
        self.ingest_text(
            source_type=source_type,
            uri=url,
            title=title or url,
            source=res.final_url,
            url=url,
            collection=collection,
            tags=tags or [],
            text=text,
            content_hash=content_hash,
        )
        return {"url": url, "title": title, "final_url": res.final_url}
