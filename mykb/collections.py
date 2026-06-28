"""Auto-Sammlungen: themenbasiertes Clustering der Dokumentvektoren.

Erste, bewusst dependency-leichte Stufe (numpy, deterministisch): pro Quelle
ein repräsentativer Vektor, greedy Cosinus-Clustering über einen Schwellwert,
Benennung über das häufigste vorhandene Tag (sonst erstes Titelwort).

``suggest`` schlägt nur vor; ``apply`` schreibt die Sammlung in die Tabelle
(setzt das Feld ``collection``, ohne neu zu embedden).
"""
from __future__ import annotations

from collections import Counter

import structlog

from . import store
from .config import DOCS_TABLE, Config

logger = structlog.get_logger()


def _greedy_clusters(items: list[dict], threshold: float) -> list[list[int]]:
    import numpy as np

    vecs = np.asarray([it["vector"] for it in items], dtype="float32")
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs = vecs / norms

    n = len(items)
    assigned = [-1] * n
    clusters: list[list[int]] = []
    for i in range(n):
        if assigned[i] != -1:
            continue
        cid = len(clusters)
        assigned[i] = cid
        members = [i]
        sims = vecs @ vecs[i]
        for j in range(i + 1, n):
            if assigned[j] == -1 and sims[j] >= threshold:
                assigned[j] = cid
                members.append(j)
        clusters.append(members)
    return clusters


def _label(members: list[int], items: list[dict]) -> str:
    counter: Counter[str] = Counter()
    for m in members:
        for tag in items[m].get("tags") or []:
            counter[tag] += 1
    if counter:
        return counter.most_common(1)[0][0]
    title = items[members[0]].get("title") or "Sammlung"
    return title.split()[0] if title.split() else "Sammlung"


def suggest(cfg: Config, threshold: float = 0.6) -> list[dict]:
    db = store.connect(cfg)
    if DOCS_TABLE not in db.table_names():
        return []
    table = db.open_table(DOCS_TABLE)
    items = store.document_vectors(table)
    if not items:
        return []

    out: list[dict] = []
    for members in _greedy_clusters(items, threshold):
        out.append(
            {
                "label": _label(members, items),
                "uris": [items[m]["uri"] for m in members],
                "titles": [items[m].get("title", "") for m in members],
            }
        )
    out.sort(key=lambda c: len(c["uris"]), reverse=True)
    return out


def apply(cfg: Config, suggestions: list[dict]) -> int:
    db = store.connect(cfg)
    table = db.open_table(DOCS_TABLE)
    count = 0
    for sug in suggestions:
        for uri in sug["uris"]:
            store.set_collection(table, uri, sug["label"])
            count += 1
    logger.info("collections_applied", sources=count, clusters=len(suggestions))
    return count
