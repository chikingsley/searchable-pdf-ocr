#!/usr/bin/env -S uv run
"""Extract a structured table of contents from an OCR'd contents page.

Proof that the TOC can be built programmatically: read the OCR `words.jsonl` of a
contents page, pair each title with its trailing page number, map printed page
numbers to PDF page indices via a fixed offset, and emit structured entries (which
pymupdf can drop straight into `doc.set_toc(...)` as real bookmarks).

The fragile part is the printed->PDF offset (front matter shifts it); pass it with
--offset (e.g. printed page 1 == PDF page 13 -> --offset 12). Roman-numeral and
appendix (A-1) pages are kept as-is with no PDF target.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PAGE_TOKEN = re.compile(r"^[.\s]*((?:[A-C]-\d+)|(?:\d{1,4})|(?:[ivxlcdm]+))[.\s]*$", re.IGNORECASE)
MIN_TITLE_ALPHA = 3


def is_title(text: str) -> bool:
    return sum(c.isalpha() for c in text) >= MIN_TITLE_ALPHA and not PAGE_TOKEN.match(text)


def extract(jsonl: Path, offset: int) -> list[dict]:
    record = json.loads(next(jsonl.open(encoding="utf-8")))
    lines = [line["text"].strip() for line in record.get("lines", []) if line["text"].strip()]
    entries: list[dict] = []
    pending: str | None = None
    for text in lines:
        match = PAGE_TOKEN.match(text)
        if match and pending:
            token = match.group(1)
            pdf_page = int(token) + offset if token.isdigit() else None
            entries.append({"title": pending, "printed_page": token, "pdf_page": pdf_page})
            pending = None
        elif is_title(text):
            # join a continued title (e.g. "PREFACE," then "A NOTE FOR THE INSTRUCTOR")
            pending = f"{pending} {text}" if pending else text
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract a structured TOC from an OCR'd contents page.")
    parser.add_argument("jsonl", type=Path, help="words.jsonl of the contents page")
    parser.add_argument("out_json", type=Path)
    parser.add_argument("--offset", type=int, default=0, help="printed_page + offset = pdf_page")
    args = parser.parse_args()

    entries = extract(args.jsonl, args.offset)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sys.stdout.write(f"{len(entries)} TOC entries -> {args.out_json}\n")
    for e in entries:
        sys.stdout.write(f"  p{e['pdf_page']!s:>4}  ({e['printed_page']:>4})  {e['title']}\n")
    # pymupdf bookmark form: [[level, title, pdf_page], ...] for doc.set_toc(...)
    bookmarks = [[1, e["title"], e["pdf_page"]] for e in entries if e["pdf_page"]]
    args.out_json.with_suffix(".bookmarks.json").write_text(
        json.dumps(bookmarks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
