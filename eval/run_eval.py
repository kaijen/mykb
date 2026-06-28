#!/usr/bin/env python3
"""Eval-Gerüst für die Suchqualität (Issue #6).

Läuft auf der **Zielplattform** gegen einen bereits gebauten LanceDB-Index
(echter Qwen3-Embedder, GPU oder CPU). Misst Recall@k, Hit@k und MRR über ein
kuratiertes Query-Set und erlaubt den Vergleich Reranker an/aus.

    pip install pyyaml                       # nur fürs Eval
    python eval/run_eval.py --queries eval/queries.yaml
    python eval/run_eval.py --queries eval/queries.yaml --rerank
    python eval/run_eval.py --queries eval/queries.yaml --k 10 --json out.json

Die Such- und Rerank-Logik spiegelt bewusst die des MCP-Servers
(`server/server.py`), damit das Eval misst, was im Betrieb passiert.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Paket mykb auffindbar machen, wenn das Skript direkt gestartet wird.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# --- Metriken (rein, testbar) -----------------------------------------------

def _hit_haystack(hit: dict) -> str:
    return " ".join(
        str(hit.get(f, "")) for f in ("uri", "title", "url", "source")
    ).lower()


def first_match_rank(expected_item: str, retrieved: list[dict], k: int) -> int | None:
    """1-basierter Rang des ersten Treffers in den Top-k, der ``expected_item``
    (Teilstring in uri/title/url/source) enthält; sonst None."""
    needle = expected_item.lower()
    for rank, hit in enumerate(retrieved[:k], start=1):
        if needle in _hit_haystack(hit):
            return rank
    return None


def query_metrics(expected: list[str], retrieved: list[dict], k: int) -> dict:
    """Hit@k, Recall@k und Reciprocal Rank für eine einzelne Query."""
    if not expected:
        return {"hit": 0.0, "recall": 0.0, "rr": 0.0}
    ranks = [first_match_rank(e, retrieved, k) for e in expected]
    found = [r for r in ranks if r is not None]
    recall = len(found) / len(expected)
    hit = 1.0 if found else 0.0
    rr = (1.0 / min(found)) if found else 0.0
    return {"hit": hit, "recall": recall, "rr": rr}


def aggregate(per_query: list[dict]) -> dict:
    """Mittelwerte über alle Queries."""
    n = len(per_query)
    if n == 0:
        return {"queries": 0, "hit@k": 0.0, "recall@k": 0.0, "mrr": 0.0}
    return {
        "queries": n,
        "hit@k": sum(m["hit"] for m in per_query) / n,
        "recall@k": sum(m["recall"] for m in per_query) / n,
        "mrr": sum(m["rr"] for m in per_query) / n,
    }


# --- Such-Setup (braucht echte Abhängigkeiten + Index) ----------------------

def load_queries(path: str) -> list[dict]:
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("Query-Datei muss eine Liste von Einträgen sein.")
    return data


def _quote_list(values: list[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def build_searcher(cfg, rerank: bool):
    """Liefert eine search(query, source_types)-Funktion analog zum Server."""
    from mykb import store
    from mykb.config import DOCS_TABLE, SOURCE_TYPES
    from mykb.embedder import Embedder

    embedder = Embedder(cfg)
    db = store.connect(cfg)
    if DOCS_TABLE not in db.table_names():
        raise SystemExit(f"Tabelle '{DOCS_TABLE}' fehlt — erst indexieren.")
    table = db.open_table(DOCS_TABLE)

    reranker = None
    if rerank and cfg.rerank_model:
        from sentence_transformers import CrossEncoder

        reranker = CrossEncoder(
            cfg.rerank_model, device=cfg.rerank_device, trust_remote_code=True
        )

    def search(query: str, source_types: list[str] | None) -> list[dict]:
        qvec = embedder.encode_query(query)
        where = None
        if source_types:
            valid = [s for s in source_types if s in SOURCE_TYPES]
            if valid:
                where = f"source_type IN ({_quote_list(valid)})"
        cands = store.search(table, qvec, cfg.top_k, where=where)
        if reranker is not None and cands:
            scores = reranker.predict([(query, c["content"]) for c in cands])
            cands = [
                c
                for c, _ in sorted(
                    zip(cands, scores, strict=True),
                    key=lambda cs: cs[1],
                    reverse=True,
                )
            ]
        return cands

    return search


def main() -> None:
    parser = argparse.ArgumentParser(description="Suchqualität evaluieren (#6)")
    parser.add_argument("--queries", required=True, help="YAML mit query/expected/...")
    parser.add_argument(
        "--k", type=int, default=None, help="Top-k (Default SEARCH_RETURN_K)"
    )
    parser.add_argument("--rerank", action="store_true", help="Reranker einschalten")
    parser.add_argument("--json", help="Ergebnis zusätzlich als JSON hierhin schreiben")
    args = parser.parse_args()

    from mykb.config import load_config

    cfg = load_config()
    k = args.k or cfg.return_k
    queries = load_queries(args.queries)
    search = build_searcher(cfg, args.rerank)

    per_query: list[dict] = []
    rows: list[dict] = []
    for entry in queries:
        q = entry["query"]
        expected = entry.get("expected", [])
        retrieved = search(q, entry.get("source_types"))
        m = query_metrics(expected, retrieved, k)
        per_query.append(m)
        rows.append({"query": q, **{kk: round(vv, 3) for kk, vv in m.items()}})
        print(f"[{m['hit']:.0f}] recall={m['recall']:.2f} rr={m['rr']:.2f}  {q[:60]}")

    summary = aggregate(per_query)
    summary["k"] = k
    summary["rerank"] = bool(args.rerank)
    print("\n== Zusammenfassung ==")
    print(
        f"queries={summary['queries']}  k={k}  rerank={summary['rerank']}  "
        f"hit@k={summary['hit@k']:.3f}  recall@k={summary['recall@k']:.3f}  "
        f"mrr={summary['mrr']:.3f}"
    )

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {"summary": summary, "per_query": rows},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
