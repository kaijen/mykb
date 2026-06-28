# MCP-Server

`server/server.py` stellt den LanceDB-Index als **MCP-Server** (FastMCP,
SSE-Transport) bereit. Claude bindet ihn als Werkzeug ein und kann die Sammlung
semantisch durchsuchen.

## Starten

```bash
python server/server.py
```

Der Server lauscht auf `MCP_HOST:MCP_PORT` (Default `0.0.0.0:8000`) und bietet
den SSE-Endpoint unter `/sse` an.

## In Claude einbinden

In der MCP-Client-Konfiguration (VSCode `settings.json` oder Claude Desktop)
einen SSE-Server eintragen:

```json
{
  "mcpServers": {
    "literatur-rag": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

Im Remote-Betrieb steht statt `localhost` die über Traefik veröffentlichte
Domain (mit TLS und Authelia davor, siehe [Deployment](deployment.md)).

## Tools

### `search_standards(query, limit?)`

Semantische Suche in den Information-Security-Standards (ISO, BSI, NIST).

- `query` — Suchanfrage in natürlicher Sprache (DE oder EN)
- `limit` — Anzahl Treffer (Default aus `SEARCH_RETURN_K`)

### `search_risk_management(query, limit?)`

Semantische Suche in der Risikomanagement-Literatur. Gleiche Parameter.

### `get_document_context(file_hash, chunk_index, window?, table?)`

Holt die benachbarten Chunks eines Dokuments für mehr Kontext um eine
Fundstelle.

- `file_hash` — SHA-256 aus einem Suchtreffer
- `chunk_index` — mittlerer Chunk
- `window` — Anzahl Chunks davor und danach (Default 2)
- `table` — `standards` oder `risk_papers`

## Wie die Suche abläuft

1. Das **Query-Embedding** wird mit dem Qwen3-Instruction-Prefix erzeugt
   (asymmetrisch, gespiegelt aus dem Indexer — siehe
   [Architektur](architektur.md)).
2. LanceDB liefert die Top-`SEARCH_TOP_K` Kandidaten per Vektorsuche.
3. **Optional:** Ist `RERANK_MODEL` gesetzt, sortiert ein Cross-Encoder die
   Kandidaten um (defensiv: schlägt das Laden fehl, läuft die Suche ohne
   Reranking weiter).
4. Die Top-`SEARCH_RETURN_K` Treffer werden zurückgegeben — ohne den Vektor.

!!! note "Performance"
    Die Modelle werden erst beim ersten Tool-Aufruf geladen (langer Start,
    knappes VRAM-Budget) und danach zwischengespeichert.

## Datenschutz im Log

Queries werden nur **gekürzt** geloggt (Vorschau), niemals als Klartext. Logs
sind strukturiert (JSON über `structlog`).

Weiter mit der [Konfiguration](konfiguration.md).
