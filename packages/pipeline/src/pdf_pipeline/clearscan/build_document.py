#!/usr/bin/env -S uv run
"""Assemble OCR'd pages into one faithful, searchable ClearScan PDF, with bookmarks.

Loads the page records from one or more words.jsonl files, rebuilds each page with
the per-occurrence vector engine (clearscan_page.add_page), merges them into a
single document in page order, and optionally applies a table of contents. TOC
targets in the bookmarks file refer to *original* PDF pages; they are remapped to
the assembled page order and entries outside the selection are dropped.

Each page is rendered at its own recorded OCR dpi.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf

from pdf_pipeline.clearscan import clearscan_page as cs


def load_records(jsonls: list[Path]) -> list[dict]:
    records: list[dict] = []
    for jsonl in jsonls:
        records.extend(json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip())
    records.sort(key=lambda r: int(r["page_number"]))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble OCR'd pages into one searchable ClearScan PDF.")
    parser.add_argument("out", type=Path)
    parser.add_argument("--jsonl", type=Path, nargs="+", required=True, help="one or more words.jsonl files")
    parser.add_argument("--pdf", type=Path, default=None, help="source PDF (default: source_image from first record)")
    parser.add_argument("--text-font", default=cs.HIDDEN_FONT)
    parser.add_argument("--dilate-px", type=int, default=2)
    parser.add_argument("--no-composite", action="store_true")
    parser.add_argument("--toc", type=Path, default=None, help="bookmarks json: [[level, title, original_page], ...]")
    args = parser.parse_args()

    records = load_records(args.jsonl)
    if not records:
        raise SystemExit("no page records found")
    pdf = args.pdf or Path(records[0]["source_image"])

    out = pymupdf.open()
    page_map: dict[int, int] = {}
    total_drawn = total_hidden = 0
    for index, record in enumerate(records, start=1):
        drawn, hidden = cs.add_page(
            out, record, pdf,
            dpi=round(float(record["dpi"])), text_font=args.text_font,
            dilate_px=args.dilate_px, composite=not args.no_composite,
        )
        page_map[int(record["page_number"])] = index
        total_drawn += drawn
        total_hidden += hidden

    if args.toc:
        bookmarks = json.loads(args.toc.read_text(encoding="utf-8"))
        toc = [[lvl, title, page_map[orig]] for lvl, title, orig in bookmarks if orig in page_map]
        if toc:
            out.set_toc(toc)
            sys.stdout.write(f"set {len(toc)} bookmark(s)\n")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.save(args.out, garbage=4, deflate=True)
    sys.stdout.write(f"assembled {len(records)} pages -> {args.out} ({total_drawn} words, {total_hidden} hidden)\n")


if __name__ == "__main__":
    main()
