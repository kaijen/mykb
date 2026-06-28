# Überblick

**mykb** ist eine selbst gehostete **RAG-Pipeline** (Retrieval-Augmented
Generation) für eine persönliche Fach-Literatursammlung aus den Bereichen
**Information Security** und **Risikomanagement**.

Die Sammlung wird mit semantischen Embeddings in **LanceDB** indexiert und über
einen **MCP-Server** direkt aus Claude (VSCode, Claude Desktop) durchsuchbar
gemacht — semantische Treffer statt Volltext-Grep, sprachübergreifend zwischen
Deutsch und Englisch.

!!! info "Kontext"
    Einsatz im Consulting-Kontext. Daher gilt: alle eingesetzten Modelle sind
    **kommerziell lizenzierbar** (Apache 2.0), der Stack läuft **lokal ohne
    Cloud**, und vertrauliche Dokumente bleiben lokal (siehe
    [Deployment](deployment.md)).

## Wie es funktioniert

Standards (ISO, BSI, NIST) und Risikomanagement-Literatur liegen als PDF-,
Markdown- oder Textdateien vor. Die Pipeline

1. **extrahiert** den Text, zerlegt ihn in überlappende Chunks und
   **dedupliziert** über einen SHA-256-Hash des Dateiinhalts,
2. **kodiert** jeden Chunk mit `Qwen3-Embedding-0.6B` (DE + EN nativ) zu einem
   Vektor,
3. **speichert** Vektoren samt Metadaten in zwei LanceDB-Tabellen
   (`standards`, `risk_papers`),
4. **stellt** die Suche über einen MCP-Server bereit, den Claude als Werkzeug
   nutzt.

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

## Warum semantische Suche?

Eine klassische Stichwortsuche findet „ISO 27001 Annex A.8" nur, wenn genau
diese Zeichenkette im Text steht. Die Embedding-Suche findet auch Passagen, die
dasselbe Konzept mit anderen Worten beschreiben (z. B. „Asset Management" oder
„Inventarisierung von Werten") — und das sprachübergreifend.

## Nächste Schritte

- [Installation](installation.md) — Umgebung einrichten
- [Indexierung](indexierung.md) — Dokumente in LanceDB überführen
- [MCP-Server](mcp-server.md) — Suche in Claude einbinden
- [Konfiguration](konfiguration.md) — Environment-Variablen
- [Deployment](deployment.md) — Remote-Betrieb mit TLS und 2FA
- [Architektur & Modelle](architektur.md) — Modellwahl und Hintergründe
