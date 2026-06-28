"""Tests für ``mykb.extract``.

Randbedingungen (siehe CLAUDE.md / Testvorgaben):
- Kein echter ``Embedder``, kein Netzwerk, alle Pfade unter ``tmp_path``.
- Verhalten an die echte Implementierung angepasst (nicht geraten).
"""
from __future__ import annotations

import hashlib

import pytest

from mykb import extract
from mykb.extract import (
    Extracted,
    _bs4_extract,
    extract_textfile,
    html_to_text,
    load_file,
    sha256_bytes,
    sha256_text,
)


def test_sha256_bytes_matches_hashlib() -> None:
    data = b"hallo welt"
    assert sha256_bytes(data) == hashlib.sha256(data).hexdigest()


def test_sha256_text_is_utf8_of_bytes() -> None:
    text = "Grüße über Umlaute"
    assert sha256_text(text) == sha256_bytes(text.encode("utf-8"))
    assert sha256_text(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_extract_textfile_reads_content_and_hashes(tmp_path) -> None:
    p = tmp_path / "notiz.md"
    content = "# Titel\n\nEtwas Inhalt mit Ümläüten."
    p.write_text(content, encoding="utf-8")

    res = extract_textfile(p)

    assert isinstance(res, Extracted)
    assert res.text == content
    assert res.title == "notiz"  # path.stem
    assert res.pages == 0
    assert res.content_hash == sha256_bytes(content.encode("utf-8"))


def test_extract_textfile_decodes_invalid_utf8_defensively(tmp_path) -> None:
    p = tmp_path / "kaputt.txt"
    raw = b"gut \xff\xfe schlecht"
    p.write_bytes(raw)

    res = extract_textfile(p)

    # errors="replace" -> kein Crash, Hash bleibt über die Rohbytes stabil.
    assert "gut" in res.text
    assert res.content_hash == sha256_bytes(raw)


@pytest.mark.parametrize("suffix", [".md", ".markdown", ".txt"])
def test_load_file_handles_text_suffixes(tmp_path, suffix) -> None:
    p = tmp_path / f"datei{suffix}"
    p.write_text("Inhalt", encoding="utf-8")

    res = load_file(p)

    assert res is not None
    assert res.text == "Inhalt"
    assert res.content_hash == sha256_text("Inhalt")


def test_load_file_unknown_suffix_returns_none(tmp_path) -> None:
    p = tmp_path / "bild.png"
    p.write_bytes(b"\x89PNG\r\n")

    assert load_file(p) is None


def test_load_file_missing_file_is_defensive(tmp_path) -> None:
    # Bekannte Endung, aber Datei existiert nicht -> Fehler wird gefangen, None.
    p = tmp_path / "fehlt.txt"
    assert load_file(p) is None


def test_html_to_text_returns_text_and_title() -> None:
    html = """<html><head><title>Seitentitel</title></head><body>
    <main><h1>Überschrift</h1>
    <p>Dies ist ein ausreichend langer Hauptinhalt, damit trafilatura ihn als
    Artikel erkennt und sauber extrahiert. Lorem ipsum dolor sit amet.</p>
    </main></body></html>"""

    text, title = html_to_text(html)

    assert isinstance(text, str)
    assert isinstance(title, str)
    assert "Hauptinhalt" in text
    assert title  # nicht leer


def test_html_to_text_strips_boilerplate() -> None:
    html = """<html><head><title>T</title></head><body>
    <nav>NAVMARKER menüpunkte hier</nav>
    <header>HEADERMARKER kopfzeile</header>
    <main><h1>Artikelüberschrift</h1>
    <p>Substanzieller Fließtext, lang genug für die Hauptinhalts-Erkennung
    durch trafilatura. Lorem ipsum dolor sit amet consectetur adipiscing.</p>
    </main>
    <footer>FOOTERMARKER fusszeile copyright</footer>
    <script>SCRIPTMARKER var x = 1;</script>
    </body></html>"""

    text, _ = html_to_text(html)

    for marker in ("HEADERMARKER", "FOOTERMARKER", "SCRIPTMARKER"):
        assert marker not in text
    assert "Fließtext" in text


def test_bs4_fallback_when_trafilatura_returns_none(monkeypatch) -> None:
    # trafilatura liefert nichts -> bs4-Fallback greift und entfernt
    # nav/footer/script/etc.; Titel kommt aus <title>.
    import trafilatura

    monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: None)

    html = """<html><head><title>Mein Titel</title></head><body>
    <nav>NAVMARKER</nav>
    <footer>FOOTERMARKER</footer>
    <script>SCRIPTMARKER</script>
    <p>Sichtbarer Absatztext.</p>
    </body></html>"""

    text, title = html_to_text(html)

    assert title == "Mein Titel"
    assert "Sichtbarer Absatztext." in text
    for marker in ("NAVMARKER", "FOOTERMARKER", "SCRIPTMARKER"):
        assert marker not in text


def test_bs4_fallback_when_trafilatura_raises(monkeypatch) -> None:
    # Defensiv: Ausnahme in trafilatura -> Fallback statt Absturz.
    import trafilatura

    def boom(*a, **k):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(trafilatura, "extract", boom)

    html = "<html><body><p>Nur ein Absatz.</p></body></html>"
    text, _title = html_to_text(html)

    assert "Nur ein Absatz." in text


def test_bs4_extract_directly_removes_boilerplate_and_title() -> None:
    html = """<html><head><title>  Getrimmter Titel  </title></head><body>
    <nav>NAVMARKER</nav><aside>ASIDEMARKER</aside>
    <p>Behaltener Text.</p>
    <footer>FOOTERMARKER</footer><script>SCRIPTMARKER</script>
    </body></html>"""

    text, title = _bs4_extract(html)

    assert title == "Getrimmter Titel"  # gestrippt
    assert "Behaltener Text." in text
    for marker in ("NAVMARKER", "ASIDEMARKER", "FOOTERMARKER", "SCRIPTMARKER"):
        assert marker not in text


def test_load_file_returns_none_on_extract_exception(tmp_path, monkeypatch) -> None:
    # Bekannte Endung, aber Extraktion wirft -> defensiv None.
    p = tmp_path / "datei.md"
    p.write_text("egal", encoding="utf-8")

    def boom(_path):
        raise OSError("lesefehler")

    monkeypatch.setattr(extract, "extract_textfile", boom)

    assert load_file(p) is None
