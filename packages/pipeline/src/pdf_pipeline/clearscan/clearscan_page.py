#!/usr/bin/env -S uv run
"""Per-occurrence faithful, searchable ClearScan-style re-render.

Traces the *actual ink* of each OCR text box into vector outlines and draws them
in place (in the word's own sampled ink color, over its sampled local background),
then adds an invisible OCR text layer for search. Because the look comes from
traced ink, the display is script-agnostic: Latin, Cyrillic, and Persian cursive
all render faithfully. Photos/figures survive via compositing over the original.

NOTE: this is a faithful *searchable* re-render, not type-to-edit text. The visible
layer is vector paths; the text layer is invisible. For real editable (retype-able)
text on clean Latin/Cyrillic, use rebuild_page.py (deduped font), which has a
fidelity ceiling. This tool trades editability for faithful display on any script.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import pymupdf

from pdf_pipeline.clearscan import letter_boxes as lb

RGB_CHANNELS = 3
PAD_PX = 2
MIN_CONTOUR_AREA = 3.0
MIN_POLY_POINTS = 3
EPSILON_FRAC = 0.004
INVISIBLE = 3  # PDF text render mode: no fill, no stroke (searchable but unseen)
HIDDEN_FONT = "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"  # Latin + Cyrillic

Color = tuple[float, float, float]


def render_rgb(pdf: Path, page_number: int, width: int, height: int) -> np.ndarray:
    doc = pymupdf.open(pdf)
    page = doc[page_number - 1]
    matrix = pymupdf.Matrix(width / page.rect.width, height / page.rect.height)
    pm = page.get_pixmap(matrix=matrix, alpha=False)
    img = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
    return img[:, :, :3].copy() if pm.n >= RGB_CHANNELS else cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)


def word_colors(rgb_crop: np.ndarray, ink_mask: np.ndarray) -> tuple[Color, Color]:
    """Median ink color (dark pixels) and background color (the rest), each as 0..1 RGB."""
    ink_px = rgb_crop[ink_mask]
    bg_px = rgb_crop[~ink_mask]
    ink = tuple(np.median(ink_px, axis=0) / 255) if ink_px.size else (0.0, 0.0, 0.0)
    bg = tuple(np.median(bg_px, axis=0) / 255) if bg_px.size else (1.0, 1.0, 1.0)
    return ink, bg


def trace_ink(ink_mask: np.ndarray, offset_px: tuple[int, int], f: float) -> list[list[pymupdf.Point]]:
    """Closed polygons (PDF points) for all ink in the mask; holes handled by even-odd fill."""
    contours, _ = cv2.findContours(ink_mask.astype(np.uint8) * 255, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    ox, oy = offset_px
    polys: list[list[pymupdf.Point]] = []
    for contour in contours:
        if abs(cv2.contourArea(contour)) < MIN_CONTOUR_AREA:
            continue
        eps = max(0.5, EPSILON_FRAC * cv2.arcLength(contour, closed=True))
        approx = cv2.approxPolyDP(contour, eps, closed=True)
        if len(approx) < MIN_POLY_POINTS:
            continue
        polys.append([pymupdf.Point((ox + float(p[0][0])) * f, (oy + float(p[0][1])) * f) for p in approx])
    return polys


def draw_words(page: pymupdf.Page, record: dict, rgb: np.ndarray, f: float, dilate_px: int) -> int:
    drawn = 0
    kernel = np.ones((dilate_px, dilate_px), np.uint8) if dilate_px > 0 else None
    for _, _, (bx, by, bw, bh) in lb.iter_words(record):
        rgb_crop = rgb[by : by + bh, bx : bx + bw]
        if rgb_crop.size == 0:
            continue
        gray = cv2.cvtColor(rgb_crop, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ink_mask = binary > 0
        ink, bg = word_colors(rgb_crop, ink_mask)  # colour sampled from the un-dilated ink
        # erase the scanned text into its local background colour, then draw the ink
        rect = pymupdf.Rect((bx - PAD_PX) * f, (by - PAD_PX) * f, (bx + bw + PAD_PX) * f, (by + bh + PAD_PX) * f)
        page.draw_rect(rect, color=bg, fill=bg)
        trace_mask = cv2.dilate(binary, kernel) > 0 if kernel is not None else ink_mask
        polys = trace_ink(trace_mask, (bx, by), f)
        if not polys:
            continue
        shape = page.new_shape()
        for poly in polys:
            shape.draw_polyline(poly)
        shape.finish(fill=ink, color=None, even_odd=True, closePath=True)
        shape.commit()
        drawn += 1
    return drawn


def hidden_text(page: pymupdf.Page, record: dict, f: float, font_path: str) -> int:
    fontname = "hiddentext"
    page.insert_font(fontname=fontname, fontfile=font_path)
    placed = 0
    for _, text, (bx, by, _bw, bh) in lb.iter_words(record):
        if not text.strip():
            continue
        try:
            page.insert_text(
                (bx * f, (by + bh) * f), text, fontsize=bh * f * 0.9,
                fontname=fontname, render_mode=INVISIBLE,
            )
            placed += 1
        except (ValueError, RuntimeError):
            continue
    return placed


def add_page(
    out: pymupdf.Document, record: dict, pdf: Path, *,
    dpi: int, text_font: str, dilate_px: int, composite: bool,
) -> tuple[int, int]:
    """Append one rebuilt page to `out`; return (words drawn, hidden words placed)."""
    page_number = int(record["page_number"])
    width, height = int(record["width"]), int(record["height"])
    f = 72.0 / dpi
    rgb = render_rgb(pdf, page_number, width, height)
    src_page = pymupdf.open(pdf)[page_number - 1]
    page = out.new_page(width=src_page.rect.width, height=src_page.rect.height)
    if composite:
        pm = src_page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
        page.insert_image(page.rect, pixmap=pm)
    drawn = draw_words(page, record, rgb, f, dilate_px)
    placed = hidden_text(page, record, f, text_font)
    return drawn, placed


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-occurrence faithful searchable ClearScan re-render.")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("page", type=int)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--pdf", type=Path, default=None)
    parser.add_argument("--dpi", type=int, default=300, help="OCR raster dpi (coordinate space)")
    parser.add_argument("--text-font", default=HIDDEN_FONT, help="font for the hidden searchable text layer")
    parser.add_argument("--no-composite", action="store_true", help="render on white instead of over the original page")
    parser.add_argument("--dilate-px", type=int, default=0, help="thicken traced ink by N px to match scan weight")
    args = parser.parse_args()

    record = lb.load_page_record(args.jsonl, args.page)
    pdf = args.pdf or Path(record["source_image"])
    out = pymupdf.open()
    drawn, placed = add_page(
        out, record, pdf, dpi=args.dpi, text_font=args.text_font,
        dilate_px=args.dilate_px, composite=not args.no_composite,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_pdf = args.out_dir / f"page{args.page}-clearscan.pdf"
    out.save(out_pdf, garbage=4, deflate=True)
    sys.stdout.write(f"drew {drawn} words, {placed} hidden\nsaved: {out_pdf}\n")


if __name__ == "__main__":
    main()
