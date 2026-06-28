# data/

Daten-Wurzel der Pipeline. **Inhalte hier werden nicht versioniert** (siehe
`.gitignore`), nur die Verzeichnisstruktur über `.gitkeep`-Platzhalter.

```
data/
├── literatur/          # Quelldokumente (read-only gemountet)
│   ├── standards/      # ISO, BSI, NIST   -> LanceDB-Tabelle "standards"
│   └── research/       # Risk-Paper        -> LanceDB-Tabelle "risk_papers"
└── lance/              # LanceDB-Index (generiert, wird beim Indexieren befüllt)
```

## Quelldokumente

Unterstützte Formate: `.pdf`, `.md`, `.txt`, `.markdown`. Die Klassifizierung
(`type`) erfolgt anhand des Dateinamens (iso/bsi/nist/sonstige bzw.
bayesian/quantitative/frameworks).

## Sicherheit

Öffentliche Standards und eigene Analysen sind unkritisch. Client-spezifische
oder vertrauliche Dokumente gehören **nicht** auf einen externen VPS, sondern
bleiben lokal oder in einer isolierten, NDA-konformen Instanz. Siehe
`CLAUDE.md`, Abschnitt „Sicherheit / Datenhaltung".
