#!/usr/bin/env -S uv run
"""Segment OCR word boxes into per-letter boxes and visualize them.

The editable layer needs one box per letter, but this repo's OCR only emits
word/line boxes. This tool crops each OCR word from the page raster and splits it
into letters two ways, so we can eyeball which segmenter survives a bad scan:

- cc:  raw connected components (merged by x-overlap to rejoin i/j dots, accents,
       broken strokes). No reliance on the OCR string.
- ocr: same components, then forced to match the OCR word's character count
       (merge nearest gaps if too many, split widest by projection valley if too
       few). Fragile exactly where OCR misreads characters.

Outputs an overlay PNG per method and a per-letter JSON manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
import pymupdf

Box = tuple[int, int, int, int]  # x, y, w, h in page pixels
RGB_CHANNELS = 3
INK_THRESHOLD = 128


@dataclass
class Letter:
    char: str
    box: Box
    word_id: str
    method: str


def load_page_record(jsonl: Path, page_number: int) -> dict:
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if int(record.get("page_number", -1)) == page_number:
            return record
    msg = f"page {page_number} not found in {jsonl}"
    raise ValueError(msg)


def render_gray(pdf: Path, page_number: int, width: int, height: int) -> np.ndarray:
    doc = pymupdf.open(pdf)
    page = doc[page_number - 1]
    zoom_x = width / page.rect.width
    zoom_y = height / page.rect.height
    pm = page.get_pixmap(matrix=pymupdf.Matrix(zoom_x, zoom_y), alpha=False)
    img = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
    rgb = img[:, :, :3] if pm.n >= RGB_CHANNELS else np.repeat(img, RGB_CHANNELS, axis=2)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def x_overlap(a: Box, b: Box) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2]


def union(a: Box, b: Box) -> Box:
    x0 = min(a[0], b[0])
    y0 = min(a[1], b[1])
    x1 = max(a[0] + a[2], b[0] + b[2])
    y1 = max(a[1] + a[3], b[1] + b[3])
    return (x0, y0, x1 - x0, y1 - y0)


def components(crop: np.ndarray, *, min_area: int, min_h: int) -> list[Box]:
    _, binary = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    boxes: list[Box] = []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if area < min_area or h < min_h:
            continue
        boxes.append((int(x), int(y), int(w), int(h)))
    # merge components that overlap horizontally (i/j dots, accents, broken strokes)
    boxes.sort(key=lambda b: b[0])
    merged: list[Box] = []
    for b in boxes:
        if merged and x_overlap(merged[-1], b):
            merged[-1] = union(merged[-1], b)
        else:
            merged.append(b)
    return merged


def split_widest(boxes: list[Box], crop: np.ndarray) -> list[Box]:
    idx = max(range(len(boxes)), key=lambda i: boxes[i][2])
    x, y, w, h = boxes[idx]
    col_ink = (crop[y : y + h, x : x + w] < INK_THRESHOLD).sum(axis=0)
    inner = col_ink[w // 4 : 3 * w // 4]
    if inner.size == 0:
        return boxes
    cut = int(np.argmin(inner)) + w // 4
    left = (x, y, cut, h)
    right = (x + cut, y, w - cut, h)
    return [*boxes[:idx], left, right, *boxes[idx + 1 :]]


def merge_closest(boxes: list[Box]) -> list[Box]:
    gaps = [boxes[i + 1][0] - (boxes[i][0] + boxes[i][2]) for i in range(len(boxes) - 1)]
    i = int(np.argmin(gaps))
    return [*boxes[:i], union(boxes[i], boxes[i + 1]), *boxes[i + 2 :]]


def fit_count(boxes: list[Box], target: int, crop: np.ndarray) -> list[Box]:
    boxes = list(boxes)
    while len(boxes) > target and len(boxes) > 1:
        boxes = merge_closest(boxes)
    while len(boxes) < target:
        before = len(boxes)
        boxes = split_widest(boxes, crop)
        if len(boxes) == before:
            break
    return boxes


def segment_word(crop: np.ndarray, text: str, word_id: str, origin: tuple[int, int], *, method: str) -> list[Letter]:
    boxes = components(crop, min_area=8, min_h=6)
    chars = [c for c in text if not c.isspace()]
    if method == "ocr" and chars:
        boxes = fit_count(boxes, len(chars), crop)
    ox, oy = origin
    letters: list[Letter] = []
    for i, (x, y, w, h) in enumerate(boxes):
        char = chars[i] if i < len(chars) else "?"
        letters.append(Letter(char=char, box=(ox + x, oy + y, w, h), word_id=word_id, method=method))
    return letters


def iter_words(record: dict) -> Iterator[tuple[str, str, Box]]:
    for line in record.get("lines", []):
        for word in line.get("words", []):
            bb = word["bbox"]
            left, top, right, bottom = int(bb["left"]), int(bb["top"]), int(bb["right"]), int(bb["bottom"])
            text = word.get("corrected_text") or word.get("text", "")
            yield word["id"], text, (left, top, right - left, bottom - top)


def overlay(gray: np.ndarray, letters: list[Letter], *, label: bool) -> np.ndarray:
    canvas = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for lt in letters:
        x, y, w, h = lt.box
        cv2.rectangle(canvas, (x, y), (x + w, y + h), (0, 0, 255), 2)
        if label and lt.char.isascii() and lt.char != "?":
            cv2.putText(canvas, lt.char, (x, max(y - 4, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 140, 0), 2)
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description="Segment OCR words into letters and visualize.")
    parser.add_argument("jsonl", type=Path, help="OCR words.jsonl")
    parser.add_argument("page", type=int, help="page number (1-based)")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--pdf", type=Path, default=None, help="source PDF (default: source_image from jsonl)")
    parser.add_argument("--crop", nargs=4, type=int, default=None, metavar=("X", "Y", "W", "H"), help="close-up region")
    args = parser.parse_args()

    record = load_page_record(args.jsonl, args.page)
    pdf = args.pdf or Path(record["source_image"])
    width, height = int(record["width"]), int(record["height"])
    gray = render_gray(pdf, args.page, width, height)

    words = list(iter_words(record))
    counts = {"words": len(words)}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for method in ("cc", "ocr"):
        letters: list[Letter] = []
        for word_id, text, (bx, by, bw, bh) in words:
            crop = gray[by : by + bh, bx : bx + bw]
            if crop.size == 0:
                continue
            letters.extend(segment_word(crop, text, word_id, (bx, by), method=method))
        counts[method] = len(letters)
        canvas = overlay(gray, letters, label=(method == "ocr"))
        cv2.imwrite(str(args.out_dir / f"page{args.page}-{method}.png"), canvas)
        if args.crop:
            x, y, w, h = args.crop
            cv2.imwrite(str(args.out_dir / f"page{args.page}-{method}-crop.png"), canvas[y : y + h, x : x + w])
        (args.out_dir / f"page{args.page}-{method}.json").write_text(
            json.dumps([asdict(lt) for lt in letters], indent=2), encoding="utf-8"
        )
    expected = sum(len([c for c in t if not c.isspace()]) for _, t, _ in words)
    counts["ocr_expected_chars"] = expected
    sys.stdout.write(json.dumps(counts, indent=2) + "\n")


if __name__ == "__main__":
    main()
