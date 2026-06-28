"""CLI für die Erstellungsseite (Laptop): Indexieren, Web-Ingest, Linksammlung.

    python -m mykb index --source all|documents|notes
    python -m mykb web <url> [--collection C] [--tags a,b]
    python -m mykb links sync
    python -m mykb links check
    python -m mykb links list [--broken]
"""
from __future__ import annotations

import argparse

import structlog

from .config import load_config

logger = structlog.get_logger()


def _tags(value: str | None) -> list[str]:
    return [t.strip() for t in value.split(",") if t.strip()] if value else []


def cmd_index(args, cfg) -> None:
    from .ingest import Ingestor

    ing = Ingestor(cfg)
    total = 0
    if args.source in {"documents", "all"}:
        total += ing.ingest_path(cfg.docs_path, "document")
    if args.source in {"notes", "all"}:
        total += ing.ingest_path(cfg.notes_path, "note")
    logger.info("index_done", source=args.source, chunks=total)


def cmd_web(args, cfg) -> None:
    from .ingest import Ingestor

    ing = Ingestor(cfg)
    result = ing.ingest_url(args.url, collection=args.collection, tags=_tags(args.tags))
    if result is None:
        raise SystemExit(1)
    logger.info("web_ingested", **result)


def cmd_links(args, cfg) -> None:
    from . import links, store

    if args.links_cmd == "sync":
        links.sync_from_linkwarden(cfg)
    elif args.links_cmd == "check":
        links.check_links(cfg)
    elif args.links_cmd == "list":
        db = store.connect(cfg)
        table = store.ensure_links(db)
        rows = store.all_links(table)
        if args.broken:
            rows = [r for r in rows if r.get("status") not in {"ok", "unchecked"}]
        for r in sorted(rows, key=lambda r: r.get("status", "")):
            print(f"[{r.get('status', '?'):9}] {r.get('url', '')}  — {r.get('title', '')}")
        print(f"\n{len(rows)} Link(s)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mykb", description="Persönlicher Wissensspeicher")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_index = sub.add_parser("index", help="Lokale Dokumente/Notizen indexieren")
    p_index.add_argument(
        "--source", choices=["documents", "notes", "all"], default="all"
    )
    p_index.set_defaults(func=cmd_index)

    p_web = sub.add_parser("web", help="Einzelne Web-Seite indexieren")
    p_web.add_argument("url")
    p_web.add_argument("--collection", default="")
    p_web.add_argument("--tags", default="")
    p_web.set_defaults(func=cmd_web)

    p_links = sub.add_parser("links", help="Linksammlung (Linkwarden)")
    links_sub = p_links.add_subparsers(dest="links_cmd", required=True)
    links_sub.add_parser("sync", help="Links aus Linkwarden übernehmen + indexieren")
    links_sub.add_parser("check", help="Erreichbarkeit prüfen (Link-Rot)")
    p_list = links_sub.add_parser("list", help="Links auflisten")
    p_list.add_argument("--broken", action="store_true", help="nur problematische")
    p_links.set_defaults(func=cmd_links)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    cfg = load_config()
    args.func(args, cfg)


if __name__ == "__main__":
    main()
