"""Smoke-Test des Test-Gerüsts.

Stellt sicher, dass sich die geteilte Logik ohne torch/mcp importieren lässt
und die LanceDB-Fixtures mit Dummy-Vektoren funktionieren.
"""
from __future__ import annotations

from mykb.config import DOCS_TABLE, SOURCE_TYPES, Config


def test_cfg_paths_under_tmp(cfg, tmp_path):
    assert cfg.db_path.startswith(str(tmp_path))
    assert cfg.state_dir.startswith(str(tmp_path))
    assert cfg.queue_dir.startswith(str(tmp_path))
    assert cfg.docs_path.startswith(str(tmp_path))
    assert cfg.notes_path.startswith(str(tmp_path))
    assert cfg.device == "cpu"


def test_config_is_dataclass_default():
    # Reines Importieren/Instanziieren ohne Embedder/torch.
    c = Config()
    assert DOCS_TABLE == "documents"
    assert "document" in SOURCE_TYPES
    assert isinstance(c, Config)


def test_docs_table_roundtrip(docs_table, make_doc):
    db, table = docs_table
    assert DOCS_TABLE in db.table_names()

    rec = make_doc(uri="doc://a", content="Hallo Welt", title="A")
    table.add([rec])

    rows = (
        table.search()
        .where("uri = 'doc://a'")
        .limit(10)
        .to_list()
    )
    assert len(rows) == 1
    assert rows[0]["title"] == "A"
    assert rows[0]["summary"] == ""
    assert len(rows[0]["vector"]) == 4
