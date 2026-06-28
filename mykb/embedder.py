"""Geteilter Qwen3-Embedder für Ingest (Passages) und Server (Query).

Asymmetrisch: Passages ohne Prefix, Queries mit Instruction-Prefix. Beide
Seiten MÜSSEN dasselbe Modell und dieselbe (ggf. per ``EMBED_DIM`` gekürzte)
Dimension verwenden, sonst sind die Vektoren nicht vergleichbar.
"""
from __future__ import annotations

import structlog

from .config import Config

logger = structlog.get_logger()

EMBED_MODEL = "Qwen/Qwen3-Embedding-0.6B"

# Instruction-Prefix nur queryseitig.
QUERY_INSTRUCTION = (
    "Given a search query, retrieve relevant passages from a personal "
    "knowledge base of documents, notes and saved web content"
)


class Embedder:
    def __init__(self, cfg: Config):
        from sentence_transformers import SentenceTransformer

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
        return self.model.encode(
            query,
            prompt=f"Instruct: {QUERY_INSTRUCTION}\nQuery: {query}",
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

    @property
    def dim(self) -> int:
        return self.model.get_sentence_embedding_dimension()
