# mykb — Literatur-RAG

Selbst gehostete **RAG-Pipeline** (Retrieval-Augmented Generation) für eine
persönliche Fach-Literatursammlung aus den Bereichen **Information Security**
und **Risikomanagement**. Die Sammlung wird mit semantischen Embeddings in
**LanceDB** indexiert und über einen **MCP-Server** direkt aus Claude (VSCode,
Claude Desktop) durchsuchbar gemacht.

> 📖 **Vollständige Dokumentation:** <https://kaijen.github.io/mykb/>
> (versioniert mit MkDocs + mike, veröffentlicht über GitHub Pages)

Projektkontext, Modellwahl und Konventionen sind in [`CLAUDE.md`](CLAUDE.md)
dokumentiert.

## Was macht das Projekt?

Standards (ISO, BSI, NIST) und Risikomanagement-Literatur liegen als PDF-,
Markdown- oder Textdateien vor. Die Pipeline

1. **extrahiert** den Text, zerlegt ihn in überlappende Chunks und
   **dedupliziert** über einen SHA-256-Hash des Dateiinhalts,
2. **kodiert** jeden Chunk mit dem mehrsprachigen Embedding-Modell
   `Qwen3-Embedding-0.6B` (DE + EN nativ) zu einem Vektor,
3. **speichert** Vektoren samt Metadaten in zwei LanceDB-Tabellen
   (`standards`, `risk_papers`),
4. **stellt** die Suche über einen MCP-Server bereit, den Claude als Werkzeug
   nutzt — semantische Treffer statt Volltext-Grep.

Der gesamte Stack läuft **lokal und ohne Cloud** (LanceDB ist serverless,
dateibasiert). Alle eingesetzten Modelle sind **kommerziell lizenzierbar**
(Apache 2.0), da das Projekt im Consulting-Kontext eingesetzt wird.

### Warum semantische Suche?

Ein klassisches Stichwortsuche findet „ISO 27001 Annex A.8" nur, wenn genau
diese Zeichenkette im Text steht. Die Embedding-Suche findet auch Passagen, die
dasselbe Konzept mit anderen Worten beschreiben (z. B. „Asset Management" oder
„Inventarisierung von Werten") — sprachübergreifend zwischen Deutsch und
Englisch.

## Architektur

```
Quelldokumente (PDF/MD/TXT)
        │
        ▼
scripts/index_literature.py   ──►  LanceDB (data/lance)
   Qwen3-Embedding (GPU, FP16)        Tabellen: standards, risk_papers
        │
        ▼
server/server.py (FastMCP, SSE)  ◄── Claude (MCP-Client)
   Query-Embedding (asymmetrisch) + optionales Reranking
        │
        ▼
deploy/  Traefik (TLS) + Authelia (2FA)  für Remote-Betrieb
```

**Asymmetrisches Embedding (wichtig):** Qwen3 erwartet, dass *Queries* einen
Instruction-Prefix bekommen, *Passages* hingegen nicht. Diese Logik steckt im
Indexer (`Embedder`) und wird im MCP-Server beim Query-Embedding gespiegelt.
Beide Seiten müssen dasselbe Modell und dieselbe (ggf. per `EMBED_DIM`
gekürzte) Dimension nutzen, sonst sind die Vektoren nicht vergleichbar.

## Schnellstart

```bash
# 1. Abhängigkeiten
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Konfiguration
cp .env.example .env        # Pfade/Device anpassen

# 3. Quelldokumente ablegen
#    data/literatur/standards/   (ISO, BSI, NIST)
#    data/literatur/research/    (Risk-Paper)

# 4. Indexieren
python scripts/index_literature.py --target all

# 5. MCP-Server starten
python server/server.py
```

### MCP-Server in Claude einbinden

Der Server spricht **SSE** auf `MCP_HOST:MCP_PORT` (Default `0.0.0.0:8000`).
In der MCP-Client-Konfiguration (z. B. VSCode `settings.json` oder Claude
Desktop) als SSE-Endpoint `http://localhost:8000/sse` eintragen. Claude erhält
dann die drei Werkzeuge `search_standards`, `search_risk_management` und
`get_document_context`.

## Nutzung

| Aufgabe | Befehl |
|---|---|
| Alles indexieren | `python scripts/index_literature.py --target all` |
| Nur Standards | `python scripts/index_literature.py --target standards` |
| Nur Research | `python scripts/index_literature.py --target research` |
| Embedding-Dim kürzen | `EMBED_DIM=512 python scripts/index_literature.py --target all` |
| CPU erzwingen | `EMBED_DEVICE=cpu python scripts/index_literature.py` |
| Server starten | `python server/server.py` |

Die **MCP-Tools** im Detail:

- **`search_standards(query, limit?)`** — semantische Suche in ISO/BSI/NIST.
- **`search_risk_management(query, limit?)`** — semantische Suche in der
  Risikomanagement-Literatur.
- **`get_document_context(file_hash, chunk_index, window?, table?)`** — holt die
  benachbarten Chunks eines Treffers, um mehr Kontext um eine Fundstelle zu
  bekommen.

## Verzeichnisstruktur

| Pfad | Inhalt |
|---|---|
| `CLAUDE.md` | Projektkontext für Claude Code |
| `requirements.txt` | Python-Abhängigkeiten |
| `scripts/index_literature.py` | Indexierung in LanceDB (fertig) |
| `server/server.py` | MCP-Server mit Such-Tools |
| `deploy/` | Docker Compose, Traefik, Authelia |
| `docs/` | MkDocs-Dokumentationsquellen |
| `data/literatur/` | Quelldokumente (read-only, nicht versioniert) |
| `data/lance/` | LanceDB-Index (generiert, nicht versioniert) |

## Konfiguration

Alle Parameter werden über Environment-Variablen gesteuert; siehe
[`.env.example`](.env.example) für die vollständige Liste mit Defaults
(Pfade, Device, Chunking, Embedding-Dimension, Server-Port, Reranking).

## Dokumentation bauen

```bash
pip install -r docs/requirements.txt
mkdocs serve            # lokale Vorschau auf http://127.0.0.1:8000
```

Veröffentlicht wird automatisch: Ein **Git-Tag `v*` auf `main`** stößt den
Workflow [`.github/workflows/docs.yml`](.github/workflows/docs.yml) an, der die
Doku mit **mike** versioniert nach `gh-pages` deployt.

## Status

Siehe Abschnitt „Offene Punkte" in [`CLAUDE.md`](CLAUDE.md). Kurz:

- [x] Indexierung in LanceDB
- [x] MCP-Server: `search_standards`, `search_risk_management`, `get_document_context`
- [x] Dokumentation (MkDocs + mike, GitHub Pages)
- [ ] Reranking-Stufe (gte-multilingual-reranker)
- [ ] Hybrid-Retrieval (BGE-M3) prüfen
- [ ] `deploy/`: Traefik + Authelia produktiv
- [ ] Inkrementelles Indexieren (Upsert über `file_hash`)
