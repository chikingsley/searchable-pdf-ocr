#!/usr/bin/env -S uv run
"""Whole-page identity rebuild: turn a scanned page into editable vector text.

Pipeline (V1, pixel-faithful ClearScan):

1. Segment OCR word boxes into per-letter boxes (letter_boxes, cc method).
2. Group letters by line; derive a per-line baseline and font size.
3. Cut one representative glyph per distinct character from the scan and build a
   document-specific Unicode TTF (reuses scanfont_edit.build_font).
4. Place every letter occurrence at its own box; optionally composite over the
   original page so photos/figures survive (--composite).
5. Save the rebuilt PDF; compare to the original with verify_pdf to measure drift.

Known limit: one representative glyph per character. A bad crop for a character
poisons every occurrence, so the representative is chosen by median height with an
outlier-width filter. True per-occurrence fidelity needs shape-driven placement.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import letter_boxes as lb
import scanfont_edit as sf

FONT_NAME = "ScanDocRebuild"
CAP_FRACTION = 0.7  # cap height as a fraction of the em
WIDTH_LO, WIDTH_HI = 0.5, 1.5  # keep representatives within this band of the median width
PAD_PX = 2  # padding when erasing scanned text under composite
RGB_CHANNELS = 3


def render_rgb(pdf: Path, page_number: int, width: int, height: int) -> np.ndarray:
    doc = pymupdf.open(pdf)
    page = doc[page_number - 1]
    matrix = pymupdf.Matrix(width / page.rect.width, height / page.rect.height)
    pm = page.get_pixmap(matrix=matrix, alpha=False)
    img = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
    return img[:, :, :3].copy() if pm.n >= RGB_CHANNELS else cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)


def line_id(word_id: str) -> str:
    return word_id.rsplit("-w", 1)[0]


def segment_letters(record: dict, gray: np.ndarray) -> list[lb.Letter]:
    letters: list[lb.Letter] = []
    for word_id, text, (bx, by, bw, bh) in lb.iter_words(record):
        crop = gray[by : by + bh, bx : bx + bw]
        if crop.size == 0:
            continue
        letters.extend(
            lt
            for lt in lb.segment_word(crop, text, word_id, (bx, by), method="cc")
            if lt.char != "?" and lt.char.isprintable() and not lt.char.isspace()
        )
    return letters


def line_metrics(letters: list[lb.Letter], f: float) -> tuple[dict[str, float], dict[str, float]]:
    by_line: dict[str, list[lb.Letter]] = {}
    for lt in letters:
        by_line.setdefault(line_id(lt.word_id), []).append(lt)
    baseline: dict[str, float] = {}
    fontsize: dict[str, float] = {}
    for lid, group in by_line.items():
        baseline[lid] = statistics.median(lt.box[1] + lt.box[3] for lt in group) * f
        fontsize[lid] = (statistics.median(lt.box[3] for lt in group) / CAP_FRACTION) * f
    return baseline, fontsize


def representatives(
    letters: list[lb.Letter], baseline: dict[str, float], fontsize: dict[str, float], f: float
) -> dict[str, sf.CharBox]:
    occ: dict[str, list[lb.Letter]] = {}
    for lt in letters:
        occ.setdefault(lt.char, []).append(lt)
    rep: dict[str, sf.CharBox] = {}
    for char, group in occ.items():
        widths = sorted(it.box[2] for it in group)
        med_w = widths[len(widths) // 2]
        # drop merged-crop outliers (e.g. a 'T' whose crop swallowed the next letter)
        clean = [it for it in group if med_w * WIDTH_LO <= it.box[2] <= med_w * WIDTH_HI] or group
        chosen = sorted(clean, key=lambda it: it.box[3])[len(clean) // 2]
        lid = line_id(chosen.word_id)
        x, y, w, h = chosen.box
        rep[char] = sf.CharBox(
            char=char,
            origin=(x * f, baseline[lid]),
            bbox=(x * f, y * f, (x + w) * f, (y + h) * f),
            advance=w * f,
            font_size=fontsize[lid],
        )
    return rep


def composite_background(page: pymupdf.Page, src_page: pymupdf.Page, record: dict, dpi: int, f: float) -> None:
    pm = src_page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
    page.insert_image(page.rect, pixmap=pm)
    for _, _, (bx, by, bw, bh) in lb.iter_words(record):
        rect = pymupdf.Rect((bx - PAD_PX) * f, (by - PAD_PX) * f, (bx + bw + PAD_PX) * f, (by + bh + PAD_PX) * f)
        page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild a scanned page as editable vector text.")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("page", type=int)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--pdf", type=Path, default=None)
    parser.add_argument("--dpi", type=int, default=300, help="OCR raster dpi (coordinate space)")
    parser.add_argument("--composite", action="store_true", help="keep original page (photos), replace only text")
    args = parser.parse_args()

    record = lb.load_page_record(args.jsonl, args.page)
    pdf = args.pdf or Path(record["source_image"])
    width, height = int(record["width"]), int(record["height"])
    f = 72.0 / args.dpi

    image = render_rgb(pdf, args.page, width, height)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    letters = segment_letters(record, gray)
    if not letters:
        raise SystemExit("no letters segmented")

    baseline, fontsize = line_metrics(letters, f)
    rep = representatives(letters, baseline, fontsize, f)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    font_path = args.out_dir / f"{FONT_NAME}-Regular.ttf"
    sf.build_font(
        image, list(rep.values()), text="".join(rep), out_font=font_path,
        crops_dir=args.out_dir / "crops", dpi=args.dpi, threshold=200, min_area=2.0,
    )

    src = pymupdf.open(pdf)
    src_page = src[args.page - 1]
    out = pymupdf.open()
    page = out.new_page(width=src_page.rect.width, height=src_page.rect.height)
    if args.composite:
        composite_background(page, src_page, record, args.dpi, f)
    page.insert_font(fontname=FONT_NAME, fontfile=str(font_path))
    for lt in letters:
        lid = line_id(lt.word_id)
        page.insert_text(
            (lt.box[0] * f, baseline[lid]), lt.char, fontsize=fontsize[lid], fontname=FONT_NAME, color=(0, 0, 0)
        )
    out_pdf = args.out_dir / f"page{args.page}-rebuild.pdf"
    out.save(out_pdf, garbage=4, deflate=True)
    sys.stdout.write(f"placed {len(letters)} letters, {len(rep)} glyphs\nsaved: {out_pdf}\n")


if __name__ == "__main__":
    main()
