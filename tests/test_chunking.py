"""Tests für mykb.chunking (wortbasiertes Chunking mit Überlappung)."""
from __future__ import annotations

from mykb.chunking import chunk_text


def test_leerer_text_gibt_leere_liste() -> None:
    assert chunk_text("", size=10, overlap=2) == []


def test_nur_whitespace_gibt_leere_liste() -> None:
    assert chunk_text("   \n\t  ", size=10, overlap=2) == []


def test_text_kuerzer_als_size_einzelner_chunk() -> None:
    assert chunk_text("eins zwei drei", size=10, overlap=2) == ["eins zwei drei"]


def test_split_normalisiert_whitespace() -> None:
    # str.split() kollabiert mehrfachen Whitespace und entfernt Ränder.
    assert chunk_text("  a   b\tc\n", size=10, overlap=0) == ["a b c"]


def test_step_ist_size_minus_overlap() -> None:
    words = [f"w{i}" for i in range(10)]
    text = " ".join(words)
    chunks = chunk_text(text, size=4, overlap=1)
    # step = 4 - 1 = 3, Startindizes 0,3,6,9
    assert chunks[0] == "w0 w1 w2 w3"
    assert chunks[1] == "w3 w4 w5 w6"
    assert chunks[2] == "w6 w7 w8 w9"
    assert chunks[3] == "w9"
    assert len(chunks) == 4


def test_overlap_words_werden_geteilt() -> None:
    words = [f"w{i}" for i in range(6)]
    chunks = chunk_text(" ".join(words), size=3, overlap=1)
    # step = 2, Startindizes 0,2,4
    assert chunks == ["w0 w1 w2", "w2 w3 w4", "w4 w5"]
    # Letztes Wort jedes Chunks taucht als erstes im nächsten wieder auf.
    assert chunks[0].split()[-1] == chunks[1].split()[0]


def test_overlap_null_kein_doppeltes_wort() -> None:
    words = [f"w{i}" for i in range(6)]
    chunks = chunk_text(" ".join(words), size=2, overlap=0)
    # step = 2, keine Überlappung
    assert chunks == ["w0 w1", "w2 w3", "w4 w5"]
    joined = " ".join(chunks).split()
    assert joined == words


def test_overlap_groesser_gleich_size_step_mindestens_eins() -> None:
    # max(size - overlap, 1): step darf nie 0 werden (keine Endlosschleife).
    words = [f"w{i}" for i in range(5)]
    chunks = chunk_text(" ".join(words), size=2, overlap=5)
    # step = max(2 - 5, 1) = 1, Startindizes 0..4
    assert len(chunks) == 5
    assert chunks[0] == "w0 w1"
    assert chunks[-1] == "w4"


def test_overlap_gleich_size() -> None:
    words = [f"w{i}" for i in range(4)]
    chunks = chunk_text(" ".join(words), size=3, overlap=3)
    # step = max(3 - 3, 1) = 1
    assert chunks[0] == "w0 w1 w2"
    assert chunks[1] == "w1 w2 w3"
    assert len(chunks) == 4


def test_lange_eingabe_deckt_alle_woerter_ab() -> None:
    n = 1000
    words = [f"w{i}" for i in range(n)]
    chunks = chunk_text(" ".join(words), size=50, overlap=10)
    # Jedes Originalwort muss in mindestens einem Chunk vorkommen.
    seen = set()
    for c in chunks:
        seen.update(c.split())
    assert seen == set(words)
    # Erster Chunk hat genau size Wörter.
    assert len(chunks[0].split()) == 50


def test_size_eins_overlap_null_ein_wort_pro_chunk() -> None:
    chunks = chunk_text("a b c", size=1, overlap=0)
    assert chunks == ["a", "b", "c"]


def test_jeder_chunk_hoechstens_size_woerter() -> None:
    words = [f"w{i}" for i in range(37)]
    size = 8
    chunks = chunk_text(" ".join(words), size=size, overlap=3)
    assert all(len(c.split()) <= size for c in chunks)
