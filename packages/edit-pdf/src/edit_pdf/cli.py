#!/usr/bin/env -S uv run
"""Edit a digital PDF's text in its own embedded font (Acrobat "Edit PDF" analog).

Digital PDFs already carry real text and embedded fonts. This tool finds a text
string, extracts the matching embedded font, removes the old text, and re-inserts
the replacement in that font at the same baseline / size / color -- so the edit
looks native. It reports any replacement characters the embedded font subset is
missing (the one real limitation of editing subsetted fonts).
"""

from __future__ import annotations

import argparse
import io
import sys
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from fontTools.ttLib import TTFont

MIN_TEXT_CHARS = 50  # heuristic: digital text layer vs scan


@dataclass
class Target:
    origin: tuple[float, float]  # baseline-left, in points
    rect: pymupdf.Rect  # bbox of the matched substring
    font: str  # span basefont, e.g. "FranklinGothic-Book"
    size: float
    color: tuple[float, float, float]


def int_to_rgb(color: int) -> tuple[float, float, float]:
    return ((color >> 16 & 255) / 255, (color >> 8 & 255) / 255, (color & 255) / 255)


def classify(pdf: Path) -> str:
    doc = pymupdf.open(pdf)
    page = doc[0]
    chars = len(page.get_text().strip())
    fonts = len(page.get_fonts(full=True))
    images = len(page.get_images(full=True))
    if chars >= MIN_TEXT_CHARS and fonts:
        return f"DIGITAL (text_chars={chars}, fonts={fonts}, images={images}) -> editpdf lane"
    return f"SCAN/IMAGE (text_chars={chars}, fonts={fonts}, images={images}) -> clearscan lane"


def find_target(page: pymupdf.Page, find: str) -> Target:
    raw = page.get_text("rawdict")
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                chars = span.get("chars", [])
                text = "".join(c["c"] for c in chars)
                start = text.find(find)
                if start == -1:
                    continue
                matched = chars[start : start + len(find)]
                origin = matched[0]["origin"]
                x0 = min(c["bbox"][0] for c in matched)
                y0 = min(c["bbox"][1] for c in matched)
                x1 = max(c["bbox"][2] for c in matched)
                y1 = max(c["bbox"][3] for c in matched)
                return Target(
                    origin=(float(origin[0]), float(origin[1])),
                    rect=pymupdf.Rect(x0, y0, x1, y1),
                    font=span.get("font", ""),
                    size=float(span.get("size", 10.0)),
                    color=int_to_rgb(int(span.get("color", 0))),
                )
    msg = f"text {find!r} not found"
    raise SystemExit(msg)


def embedded_font_for(doc: pymupdf.Document, page: pymupdf.Page, basefont: str, need: str) -> tuple[bytes, list[str]]:
    """Return (font buffer, missing chars), preferring the subset that covers `need`."""
    best: tuple[bytes, list[str]] | None = None
    for entry in page.get_fonts(full=True):
        xref, ext = entry[0], entry[1]
        embedded_name = str(entry[3]).rpartition("+")[2]
        if not ext or embedded_name != basefont.rpartition("+")[2]:
            continue
        buffer = doc.extract_font(xref)[3]
        if not buffer:
            continue
        cmap: dict[int, str] = TTFont(io.BytesIO(buffer)).getBestCmap() or {}
        missing = sorted({c for c in need if ord(c) not in cmap and not c.isspace()})
        if not missing:
            return buffer, []
        if best is None or len(missing) < len(best[1]):
            best = (buffer, missing)
    if best is None:
        msg = f"no embedded font matching {basefont!r}"
        raise SystemExit(msg)
    return best


def edit(pdf: Path, out: Path, *, find: str, replace: str, page_number: int | None) -> None:
    doc = pymupdf.open(pdf)
    pages = [doc[page_number - 1]] if page_number else [doc[i] for i in range(doc.page_count)]
    for page in pages:
        if not page.search_for(find):
            continue
        target = find_target(page, find)
        buffer, missing = embedded_font_for(doc, page, target.font, replace)
        if missing:
            sys.stdout.write(
                f"WARNING: embedded {target.font} subset is missing glyphs for {missing} (edit will show gaps)\n"
            )
        page.add_redact_annot(target.rect, fill=(1, 1, 1))
        page.apply_redactions(images=getattr(pymupdf, "PDF_REDACT_IMAGE_NONE", 0))
        fontname = "EditFont"
        page.insert_font(fontname=fontname, fontbuffer=buffer)
        page.insert_text(target.origin, replace, fontname=fontname, fontsize=target.size, color=target.color)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(out, garbage=4, deflate=True)
        sys.stdout.write(
            f"edited {find!r} -> {replace!r} on page using {target.font} @ {target.size:.0f}pt\nsaved: {out}\n"
        )
        return
    msg = f"text {find!r} not found in document"
    raise SystemExit(msg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Edit a digital PDF in its own embedded font.")
    sub = parser.add_subparsers(dest="command", required=True)

    cls = sub.add_parser("classify")
    cls.add_argument("pdf", type=Path)

    ed = sub.add_parser("edit")
    ed.add_argument("pdf", type=Path)
    ed.add_argument("out", type=Path)
    ed.add_argument("--find", required=True)
    ed.add_argument("--replace", required=True)
    ed.add_argument("--page", type=int, default=None)

    args = parser.parse_args()
    if args.command == "classify":
        sys.stdout.write(classify(args.pdf) + "\n")
    else:
        edit(args.pdf, args.out, find=args.find, replace=args.replace, page_number=args.page)


if __name__ == "__main__":
    main()
