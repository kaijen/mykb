"""Tests für ``mykb.patterns`` (kuratierte Analyse-Prompts).

Reine Datenstruktur — kein Embedder, kein Netzwerk, keine Server-Importe.
"""
from __future__ import annotations

import pytest

from mykb.patterns import PATTERNS

EXPECTED_KEYS = {"summarize", "extract_wisdom", "extract_claims", "action_items"}


def test_patterns_is_dict() -> None:
    assert isinstance(PATTERNS, dict)
    assert PATTERNS


def test_patterns_has_expected_keys() -> None:
    assert EXPECTED_KEYS.issubset(PATTERNS.keys())


@pytest.mark.parametrize("name", sorted(EXPECTED_KEYS))
def test_entry_has_nonempty_description_and_instruction(name: str) -> None:
    entry = PATTERNS[name]
    assert isinstance(entry, dict)

    description = entry["description"]
    instruction = entry["instruction"]

    assert isinstance(description, str)
    assert isinstance(instruction, str)
    assert description.strip()
    assert instruction.strip()


def test_all_entries_well_formed() -> None:
    for name, entry in PATTERNS.items():
        assert isinstance(name, str) and name
        assert set(entry) >= {"description", "instruction"}
        for value in entry.values():
            assert isinstance(value, str) and value.strip()
