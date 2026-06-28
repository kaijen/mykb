# eval/ — Suchqualität messen (Issue #6)

Kleines Gerüst, um die Trefferqualität an **echten Daten** zu messen — gehört auf
die **Zielplattform** (gebauter Index + echter Embedder). Auf der Sandbox sinnlos.

## Vorgehen

```bash
# 1. Index muss existieren (auf dem Laptop)
python -m mykb index --source all

# 2. Query-Set anlegen
cp eval/queries.example.yaml eval/queries.yaml   # mit echten Anfragen füllen
pip install pyyaml

# 3. Baseline messen (ohne Reranker)
python eval/run_eval.py --queries eval/queries.yaml --json eval/baseline.json

# 4. Mit Reranker vergleichen
RERANK_MODEL=Alibaba-NLP/gte-multilingual-reranker-base \
  python eval/run_eval.py --queries eval/queries.yaml --rerank --json eval/reranked.json
```

## Metriken

- **Hit@k** — Anteil der Queries mit mindestens einem korrekten Treffer in den Top-k.
- **Recall@k** — Anteil der erwarteten Quellen, die in den Top-k auftauchen.
- **MRR** — mittlerer reziproker Rang des ersten korrekten Treffers.

`k` = `--k` bzw. `SEARCH_RETURN_K`.

## Was sich damit vergleichen lässt

- **Reranker an/aus** (billig, kein Neuaufbau): `--rerank`.
- **Embedding-Dimension** (`EMBED_DIM`) und **Top-k** (`SEARCH_TOP_K`).
- **Chunking-Varianten** (`CHUNK_SIZE`/`CHUNK_OVERLAP`): erfordern **Neuindexierung**,
  da Chunking zur Index-Zeit passiert — getrennte Indizes bauen und je messen.

## Hinweis
Such-/Rerank-Pfad spiegelt `server/server.py`, damit das Eval misst, was im Betrieb
passiert. Ergebnisse fließen als Entscheidung über die produktiven Defaults zurück
in #6.
