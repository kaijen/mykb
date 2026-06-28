# Installation

## Voraussetzungen

- **Python ≥ 3.11**
- Für GPU-Betrieb: CUDA-fähige GPU. Das Referenz-Setup nutzt eine GPU mit
  **4 GB VRAM** (Engpass) und **64 GB System-RAM**. CPU-only ist möglich
  (langsamer, siehe [Konfiguration](konfiguration.md)).
- Optional für den Remote-Betrieb: Docker und Docker Compose.

## Einrichtung

```bash
# Repository klonen
git clone https://github.com/kaijen/mykb.git
cd mykb

# Virtuelle Umgebung
python -m venv .venv
source .venv/bin/activate

# Abhängigkeiten
pip install -r requirements.txt
```

## Konfiguration anlegen

```bash
cp .env.example .env
```

Anschließend in `.env` mindestens Pfade und Device prüfen:

```bash
LANCE_DB_PATH=./data/lance
SOURCE_DOCS_PATH=./data/literatur
EMBED_DEVICE=cuda        # oder cpu
```

Die vollständige Parameterliste steht unter [Konfiguration](konfiguration.md).

## Quelldokumente ablegen

Dokumente in die vorgesehenen Ordner legen (unterstützt: `.pdf`, `.md`, `.txt`,
`.markdown`):

```
data/literatur/standards/   # ISO, BSI, NIST   -> Tabelle "standards"
data/literatur/research/    # Risk-Paper        -> Tabelle "risk_papers"
```

!!! warning "Daten werden nicht versioniert"
    `data/literatur/` und `data/lance/` sind über `.gitignore` ausgeschlossen.
    Dokumente können vertraulich sein — siehe [Deployment](deployment.md),
    Abschnitt Sicherheit.

## Modelle

Die Embedding- und Reranker-Modelle werden beim ersten Lauf automatisch von
Hugging Face geladen und lokal zwischengespeichert (`HF_HOME`). Es ist kein
manueller Download nötig.

Weiter mit der [Indexierung](indexierung.md).
