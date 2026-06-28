# Installation

## Voraussetzungen

- **Python ≥ 3.11**
- Für GPU-Betrieb: CUDA-fähige GPU. Das Referenz-Setup nutzt eine GPU mit
  **4 GB VRAM** (Engpass) und **64 GB System-RAM**. CPU-only ist möglich
  (langsamer, siehe [Konfiguration](konfiguration.md)).
- Optional: **Ollama** für die KI-Anreicherung (läuft auf CPU, siehe
  [KI-Features](ki-features.md)).
- Optional: **Linkwarden** als Bookmark-Frontend (siehe [Linksammlung](links.md)).
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
SOURCE_DOCS_PATH=./data/documents
NOTES_PATH=./data/notes
EMBED_DEVICE=cuda        # oder cpu
```

Die vollständige Parameterliste steht unter [Konfiguration](konfiguration.md).

## Quellen ablegen

Dateien in die vorgesehenen Ordner legen (unterstützt: `.pdf`, `.md`,
`.markdown`, `.txt`):

```
data/documents/   # lokale Dokumente -> source_type=document
data/notes/       # eigene Notizen    -> source_type=note
```

Ein Unterordner unter `documents/` bzw. `notes/` wird als `collection`
übernommen.

!!! warning "Daten werden nicht versioniert"
    `data/documents/`, `data/notes/` und `data/lance/` sind über `.gitignore`
    ausgeschlossen. Inhalte können privat sein — siehe
    [Deployment](deployment.md), Abschnitt Sicherheit.

## Modelle

Embedder (und optionaler Reranker) werden beim ersten Lauf automatisch von
Hugging Face geladen und lokal zwischengespeichert (`HF_HOME`). Kein manueller
Download nötig. Für die Anreicherung wird zusätzlich ein lokales
Ollama-Modell benötigt (z. B. `ollama pull llama3.2`).

Weiter mit [Inhalte erfassen](erfassen.md).
