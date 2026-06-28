# data/

Daten-Wurzel der Pipeline. **Inhalte hier werden nicht versioniert** (siehe
`.gitignore`), nur die Verzeichnisstruktur über `.gitkeep`-Platzhalter.

```
data/
├── documents/         # lokale Dateien (PDF/MD/TXT)  -> source_type=document
├── notes/             # eigene Notizen (Markdown)     -> source_type=note
└── lance/             # LanceDB-Index (generiert: Tabellen documents, links)
```

Web-Inhalte (`source_type=web`) und Link-Snapshots (`source_type=link`) liegen
nur im Index, nicht als Dateien hier. Ein Unterordner unter `documents/` bzw.
`notes/` wird als `collection` übernommen.

## Formate

Unterstützt: `.pdf`, `.md`, `.markdown`, `.txt`. Deduplizierung über den
SHA-256-Hash des Inhalts; Re-Index ist inkrementell (Upsert über `uri` +
`content_hash`).

## Sicherheit

Es werden **alle Daten** auf den VPS synchronisiert (Entscheidung, siehe
`CLAUDE.md`). Damit können auch private Inhalte remote liegen — Absicherung
(TLS, Authelia 2FA, Rate Limiting) ist Pflicht. Streng vertrauliche
(z. B. NDA-gebundene) Dokumente im Zweifel in einer getrennten lokalen Instanz
halten.
