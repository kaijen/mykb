#!/usr/bin/env python3
"""Veraltet — die Indexierung liegt jetzt im Paket ``mykb``.

Dieser Shim bleibt für Muskelgedächtnis/alte Aufrufe erhalten und leitet auf
die neue CLI weiter:

    python -m mykb index --source all

``--target standards|research`` wird auf ``--source documents|notes`` gemappt.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mykb.__main__ import main as mykb_main  # noqa: E402

_TARGET_TO_SOURCE = {"standards": "documents", "research": "notes", "all": "all"}


def main() -> None:
    parser = argparse.ArgumentParser(description="(veraltet) → python -m mykb index")
    parser.add_argument("--target", choices=list(_TARGET_TO_SOURCE), default="all")
    args = parser.parse_args()
    print(
        "Hinweis: scripts/index_literature.py ist veraltet, "
        "nutze 'python -m mykb index'.",
        file=sys.stderr,
    )
    sys.argv = ["mykb", "index", "--source", _TARGET_TO_SOURCE[args.target]]
    mykb_main()


if __name__ == "__main__":
    main()
