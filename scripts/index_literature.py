#!/usr/bin/env python3
"""
Indexiert eine Literatursammlung (PDF, Markdown, Text) in LanceDB.

Embedder: Qwen/Qwen3-Embedding-0.6B auf GPU (FP16).
Asymmetrisch: Passages ohne Prefix, Queries mit Instruction-Prefix.
Deduplizierung per SHA-256 über den Dateiinhalt.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

import lancedb
import structlog
from sentence_transformers import SentenceTransformer

logger = structlog.get_logger()

# Instruction-Prefix nur queryseitig. Dokumente werden ohne Prefix kodiert.
QUERY_INSTRUCTION = (
    "Given a search query, retrieve relevant passages from "
    "information security standards and risk management literature"
)

EMBED_MODEL = "Qwen/Qwen3-Embedding-0.6B"


@dataclass
class IndexerConfig:
    db_path: str = os.getenv("LANCE_DB_PATH", "/data/lance")
    source_path: str = os.getenv("SOURCE_DOCS_PATH", "/data/literatur")
    device: str = os.getenv("EMBED_DEVICE", "cuda")
    batch_size: int = int(os.getenv("EMBED_BATCH_SIZE", "32"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "500"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "50"))
    # Matryoshka: None nutzt die volle Dimension (1024). Kürzen spart DB-Platz.
    embed_dim: int | None = (
        int(os.environ["EMBED_DIM"]) if os.getenv("EMBED_DIM") else None
    )


@dataclass
class Document:
    file_path: Path
    content: str
    file_hash: str
    pages: int = 0


class Embedder:
    """Kapselt das Qwen3-Modell und die asymmetrische Kodierung."""

    def __init__(self, cfg: IndexerConfig):
        self.cfg = cfg
        logger.info("loading_model", model=EMBED_MODEL, device=cfg.device)
        self.model = SentenceTransformer(
            EMBED_MODEL,
            device=cfg.device,
            model_kwargs={"torch_dtype": "float16"},
            truncate_dim=cfg.embed_dim,
        )

    def encode_passages(self, texts: list[str]):
        return self.model.encode(
            texts,
            batch_size=self.cfg.batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        )

    def encode_query(self, query: str):
        # prompt setzt den Instruct-Prefix gemäß Qwen3-Konvention.
        return self.model.encode(
            query,
            prompt=f"Instruct: {QUERY_INSTRUCTION}\nQuery: {query}",
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

    @property
    def dim(self) -> int:
        return self.model.get_sentence_embedding_dimension()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def extract_pdf(path: Path) -> Document:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return Document(path, text, sha256_file(path), len(reader.pages))


def extract_text(path: Path) -> Document:
    text = path.read_text(encoding="utf-8", errors="replace")
    return Document(path, text, sha256_file(path))


def load_document(path: Path) -> Document | None:
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return extract_pdf(path)
        if suffix in {".md", ".txt", ".markdown"}:
            return extract_text(path)
    except Exception as exc:  # defensiv: einzelne Datei darf den Lauf nicht killen
        logger.error("extract_failed", file=str(path), error=str(exc))
    return None


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = max(size - overlap, 1)
    chunks = []
    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + size]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def classify_type(name: str) -> str:
    n = name.lower()
    if "iso" in n:
        return "iso"
    if "bsi" in n or "grundschutz" in n:
        return "bsi"
    if "nist" in n:
        return "nist"
    return "sonstige"


@dataclass
class IndexStats:
    files: int = 0
    skipped: int = 0
    chunks: int = 0
    seen_hashes: set[str] = field(default_factory=set)


def build_table(cfg: IndexerConfig, table_name: str, subdir: str):
    embedder = Embedder(cfg)
    db = lancedb.connect(cfg.db_path)
    source = Path(cfg.source_path) / subdir

    stats = IndexStats()
    records: list[dict] = []

    for path in sorted(source.glob("**/*")):
        if not path.is_file() or path.suffix.lower() not in {
            ".pdf",
            ".md",
            ".txt",
            ".markdown",
        }:
            continue

        doc = load_document(path)
        if doc is None:
            stats.skipped += 1
            continue
        if doc.file_hash in stats.seen_hashes:
            logger.info("duplicate_skipped", file=str(path))
            stats.skipped += 1
            continue
        stats.seen_hashes.add(doc.file_hash)
        stats.files += 1

        chunks = chunk_text(doc.content, cfg.chunk_size, cfg.chunk_overlap)
        if not chunks:
            continue

        vectors = embedder.encode_passages(chunks)
        doc_type = classify_type(path.name)

        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            records.append(
                {
                    "id": f"{doc.file_hash[:16]}_{i}",
                    "title": path.stem,
                    "source": path.name,
                    "type": doc_type,
                    "content": chunk,
                    "file_path": str(path),
                    "file_hash": doc.file_hash,
                    "chunk_index": i,
                    "pages": doc.pages,
                    "vector": vec.tolist(),
                }
            )
        stats.chunks += len(chunks)
        logger.info("indexed_file", file=path.name, chunks=len(chunks), type=doc_type)

    if not records:
        logger.warning("no_records", table=table_name, source=str(source))
        return

    if table_name in db.table_names():
        db.drop_table(table_name)
    db.create_table(table_name, records)

    logger.info(
        "table_built",
        table=table_name,
        files=stats.files,
        chunks=stats.chunks,
        skipped=stats.skipped,
        dim=embedder.dim,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Literatur in LanceDB indexieren")
    parser.add_argument(
        "--target",
        choices=["standards", "research", "all"],
        default="all",
        help="Welche Sammlung indexiert wird",
    )
    args = parser.parse_args()
    cfg = IndexerConfig()

    logger.info("indexing_start", target=args.target, config=cfg.__dict__)

    if args.target in {"standards", "all"}:
        build_table(cfg, "standards", "standards")
    if args.target in {"research", "all"}:
        build_table(cfg, "risk_papers", "research")

    logger.info("indexing_done")


if __name__ == "__main__":
    main()
