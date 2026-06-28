"""Kuratierte „Patterns" (wiederverwendbare Analyse-Prompts), inspiriert von
Daniel Miesslers „fabric". Werden als MCP-Prompts bereitgestellt und auf den
Volltext einer ``uri`` angewandt — Claude führt die Transformation aus.

Jeder Eintrag: ``description`` (für die Prompt-Auswahl) und ``instruction``
(die eigentliche Anweisung, der der Dokumenttext angehängt wird).
"""
from __future__ import annotations

PATTERNS: dict[str, dict[str, str]] = {
    "summarize": {
        "description": "Prägnante Zusammenfassung des Dokuments",
        "instruction": (
            "Fasse das folgende Dokument prägnant zusammen: ein Satz Kernaussage, "
            "danach 3–5 Stichpunkte mit den wichtigsten Inhalten. Antworte auf "
            "Deutsch."
        ),
    },
    "extract_wisdom": {
        "description": "Kernideen, Erkenntnisse und Empfehlungen herausziehen",
        "instruction": (
            "Extrahiere aus dem folgenden Dokument die wertvollsten Erkenntnisse. "
            "Gliedere in: KERNIDEEN, ERKENNTNISSE, KONKRETE EMPFEHLUNGEN, "
            "ZITATE (wörtlich, falls vorhanden). Antworte auf Deutsch."
        ),
    },
    "extract_claims": {
        "description": "Überprüfbare Behauptungen extrahieren und einordnen",
        "instruction": (
            "Liste die zentralen, überprüfbaren Behauptungen des Dokuments auf. "
            "Markiere je Behauptung, ob sie belegt, plausibel oder fragwürdig "
            "wirkt, und nenne fehlende Belege. Antworte auf Deutsch."
        ),
    },
    "action_items": {
        "description": "Konkrete To-dos / nächste Schritte ableiten",
        "instruction": (
            "Leite aus dem folgenden Dokument konkrete, umsetzbare Aufgaben ab. "
            "Je Aufgabe: Verb am Anfang, optional Verantwortlicher/Frist, wenn im "
            "Text erkennbar. Antworte als Liste auf Deutsch."
        ),
    },
}
