# Indexierung

Das Skript `scripts/index_literature.py` überführt die Quelldokumente in
LanceDB. Pro Lauf wird die Zieltabelle neu gebaut.

## Befehle

```bash
# Alles indexieren (Standards + Research)
python scripts/index_literature.py --target all

# Nur eine Sammlung
python scripts/index_literature.py --target standards
python scripts/index_literature.py --target research

# Embedding-Dimension kürzen (Matryoshka, spart DB-Platz)
EMBED_DIM=512 python scripts/index_literature.py --target all

# CPU statt GPU erzwingen (z. B. für VPS-Test)
EMBED_DEVICE=cpu python scripts/index_literature.py
```

## Ablauf

1. **Einlesen** — alle unterstützten Dateien unter `SOURCE_DOCS_PATH/<subdir>`
   werden eingelesen (PDF via `pypdf`, Text direkt).
2. **Deduplizieren** — über den SHA-256-Hash des Dateiinhalts; identische
   Dateien werden übersprungen.
3. **Chunking** — wortbasiert mit `CHUNK_SIZE` und `CHUNK_OVERLAP`.
4. **Embedding** — Passages werden **ohne** Instruction-Prefix kodiert
   (asymmetrisch, siehe [Architektur](architektur.md)).
5. **Schreiben** — Tabelle wird (neu) angelegt und befüllt.

!!! note "Defensive Extraktion"
    Eine fehlerhafte Datei bricht den Lauf nicht ab — sie wird geloggt und
    übersprungen (`skipped`).

## Klassifizierung

Das Feld `type` wird aus dem Dateinamen abgeleitet:

| Sammlung | Werte für `type` |
|---|---|
| `standards` | `iso`, `bsi`, `nist`, `sonstige` |
| `risk_papers` | `bayesian`, `quantitative`, `frameworks` |

## LanceDB-Schema

Beide Tabellen (`standards`, `risk_papers`) haben dieselben Felder:

| Feld | Bedeutung |
|---|---|
| `id` | `<hash16>_<chunk-index>` |
| `title` | Dateiname ohne Endung |
| `source` | Dateiname |
| `type` | Klassifizierung (siehe oben) |
| `content` | Chunk-Text |
| `file_path` | Pfad der Quelldatei |
| `file_hash` | SHA-256 des Dateiinhalts |
| `chunk_index` | Position des Chunks im Dokument |
| `pages` | Seitenanzahl (PDF) |
| `vector` | Embedding |

!!! warning "Modellwechsel = neu indexieren"
    Die Vektordimension stammt aus dem Modell (Qwen3-0.6B: 1024, optional per
    `EMBED_DIM` gekürzt). Wer Modell oder Dimension ändert, muss neu
    indexieren — sonst passen Query- und Passage-Vektoren nicht zusammen.

Weiter mit dem [MCP-Server](mcp-server.md).
