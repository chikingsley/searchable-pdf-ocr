from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pymupdf
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_l_y_f import Glyph

UNITS_PER_EM = 1000
ASCENT = 1120
DESCENT = -360
RGBA_CHANNELS = 4
MIN_CONTOUR_POINTS = 3


@dataclass(frozen=True)
class CharBox:
    char: str
    origin: tuple[float, float]
    bbox: tuple[float, float, float, float]
    advance: float
    font_size: float


@dataclass(frozen=True)
class GlyphSource:
    char: str
    glyph_name: str
    crop_path: Path | None
    bbox: tuple[float, float, float, float] | None
    origin: tuple[float, float] | None
    advance_units: int
    contour_count: int
    fallback: bool


def glyph_name(char: str) -> str:
    if char == " ":
        return "space"
    return f"uni{ord(char):04X}"


def raw_char_boxes(metrics_pdf: Path, *, page_number: int, source_text: str | None) -> list[CharBox]:
    doc = pymupdf.open(metrics_pdf)
    page = doc[page_number - 1]
    raw = page.get_text("rawdict")
    chars: list[dict[str, Any]] = []
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                font_size = float(span.get("size", 0.0))
                chars.extend({**char, "font_size": font_size} for char in span.get("chars", []) if char.get("c"))

    if source_text:
        joined = "".join(str(char["c"]) for char in chars)
        start = joined.find(source_text)
        if start == -1:
            message = f"Could not find source text {source_text!r} in {metrics_pdf}"
            raise ValueError(message)
        chars = chars[start : start + len(source_text)]

    boxes: list[CharBox] = []
    for index, char in enumerate(chars):
        origin = tuple(float(value) for value in char["origin"])
        bbox = tuple(float(value) for value in char["bbox"])
        if index + 1 < len(chars) and chars[index + 1]["c"] != "\n":
            next_origin_x = float(chars[index + 1]["origin"][0])
            advance = max(next_origin_x - origin[0], bbox[2] - bbox[0])
        else:
            advance = bbox[2] - bbox[0]
        boxes.append(
            CharBox(
                char=str(char["c"]),
                origin=(origin[0], origin[1]),
                bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
                advance=advance,
                font_size=float(char["font_size"]),
            )
        )
    return boxes


def render_page(pdf: Path, *, page_number: int, dpi: int) -> np.ndarray:
    doc = pymupdf.open(pdf)
    page = doc[page_number - 1]
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape((pixmap.height, pixmap.width, pixmap.n))
    if pixmap.n == RGBA_CHANNELS:
        image = image[:, :, :3]
    return image.copy()


def point_to_pixel(value: float, *, dpi: int) -> int:
    return round(value * dpi / 72)


def crop_char(image: np.ndarray, box: CharBox, *, dpi: int, pad_px: int) -> tuple[np.ndarray, tuple[int, int]]:
    x0, y0, x1, y1 = box.bbox
    left = max(point_to_pixel(x0, dpi=dpi) - pad_px, 0)
    top = max(point_to_pixel(y0, dpi=dpi) - pad_px, 0)
    right = min(point_to_pixel(x1, dpi=dpi) + pad_px, image.shape[1])
    bottom = min(point_to_pixel(y1, dpi=dpi) + pad_px, image.shape[0])
    return image[top:bottom, left:right], (left, top)


def signed_area(points: list[tuple[int, int]]) -> float:
    area = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area += point[0] * next_point[1] - next_point[0] * point[1]
    return area / 2


def orient(points: list[tuple[int, int]], *, hole: bool) -> list[tuple[int, int]]:
    area = signed_area(points)
    if hole and area < 0:
        return list(reversed(points))
    if not hole and area > 0:
        return list(reversed(points))
    return points


def contour_to_font_points(
    contour: np.ndarray,
    *,
    offset_px: tuple[int, int],
    origin: tuple[float, float],
    baseline: float,
    font_size: float,
    dpi: int,
) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    for point in contour[:, 0, :]:
        page_x = (offset_px[0] + float(point[0])) * 72 / dpi
        page_y = (offset_px[1] + float(point[1])) * 72 / dpi
        x_units = round((page_x - origin[0]) / font_size * UNITS_PER_EM)
        y_units = round((baseline - page_y) / font_size * UNITS_PER_EM)
        points.append((x_units, y_units))
    return points


def glyph_from_crop(
    crop: np.ndarray,
    *,
    offset_px: tuple[int, int],
    box: CharBox,
    dpi: int,
    threshold: int,
    min_area: float,
) -> tuple[Glyph, int]:
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    pen = TTGlyphPen(None)
    contour_count = 0
    if hierarchy is None:
        return pen.glyph(), contour_count

    for index, contour in enumerate(contours):
        if abs(cv2.contourArea(contour)) < min_area:
            continue
        epsilon = max(0.7, 0.004 * cv2.arcLength(contour, closed=True))
        approx = cv2.approxPolyDP(contour, epsilon, closed=True)
        points = contour_to_font_points(
            approx,
            offset_px=offset_px,
            origin=box.origin,
            baseline=box.origin[1],
            font_size=box.font_size,
            dpi=dpi,
        )
        if len(points) < MIN_CONTOUR_POINTS:
            continue
        hole = int(hierarchy[0][index][3]) != -1
        points = orient(points, hole=hole)
        pen.moveTo(points[0])
        for point in points[1:]:
            pen.lineTo(point)
        pen.closePath()
        contour_count += 1
    return pen.glyph(), contour_count


def empty_glyph() -> Glyph:
    return TTGlyphPen(None).glyph()


def build_font(
    image: np.ndarray,
    boxes: list[CharBox],
    *,
    text: str,
    out_font: Path,
    crops_dir: Path,
    dpi: int,
    threshold: int,
    min_area: float,
) -> list[GlyphSource]:
    first_by_char: dict[str, CharBox] = {}
    for box in boxes:
        first_by_char.setdefault(box.char, box)

    required_chars = []
    for char in text:
        if char not in required_chars:
            required_chars.append(char)

    glyph_order = [".notdef"]
    cmap: dict[int, str] = {}
    glyphs = {".notdef": empty_glyph()}
    metrics = {".notdef": (500, 0)}
    sources: list[GlyphSource] = []
    crops_dir.mkdir(parents=True, exist_ok=True)

    for char in required_chars:
        name = glyph_name(char)
        glyph_order.append(name)
        cmap[ord(char)] = name
        box = first_by_char.get(char)
        if char == " ":
            advance_units = round(((box.advance if box else 8.0) / (box.font_size if box else 32.0)) * UNITS_PER_EM)
            glyphs[name] = empty_glyph()
            metrics[name] = (advance_units, 0)
            sources.append(
                GlyphSource(
                    char=char,
                    glyph_name=name,
                    crop_path=None,
                    bbox=box.bbox if box else None,
                    origin=box.origin if box else None,
                    advance_units=advance_units,
                    contour_count=0,
                    fallback=box is None,
                )
            )
            continue
        if box is None:
            message = f"Character {char!r} is not available in source boxes; choose observed text or add synthesis."
            raise ValueError(message)

        crop, offset_px = crop_char(image, box, dpi=dpi, pad_px=3)
        crop_path = crops_dir / f"{ord(char):04X}_{name}.png"
        cv2.imwrite(str(crop_path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        glyph, contour_count = glyph_from_crop(
            crop,
            offset_px=offset_px,
            box=box,
            dpi=dpi,
            threshold=threshold,
            min_area=min_area,
        )
        advance_units = max(1, round(box.advance / box.font_size * UNITS_PER_EM))
        glyphs[name] = glyph
        metrics[name] = (advance_units, 0)
        sources.append(
            GlyphSource(
                char=char,
                glyph_name=name,
                crop_path=crop_path,
                bbox=box.bbox,
                origin=box.origin,
                advance_units=advance_units,
                contour_count=contour_count,
                fallback=False,
            )
        )

    builder = FontBuilder(UNITS_PER_EM, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap(cmap)
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    builder.setupNameTable(
        {
            "familyName": "ScanGlyphControl",
            "styleName": "Regular",
            "uniqueFontIdentifier": "ScanGlyphControl Regular 0.1",
            "fullName": "ScanGlyphControl Regular",
            "psName": "ScanGlyphControl-Regular",
            "version": "Version 0.1",
        }
    )
    builder.setupOS2(
        sTypoAscender=ASCENT,
        sTypoDescender=DESCENT,
        usWinAscent=ASCENT,
        usWinDescent=abs(DESCENT),
    )
    builder.setupPost()
    out_font.parent.mkdir(parents=True, exist_ok=True)
    builder.save(out_font)
    return sources


def edit_with_font(
    scan_pdf: Path,
    out_pdf: Path,
    *,
    font_file: Path,
    erase: tuple[float, float, float, float],
    pos: tuple[float, float],
    text: str,
    font_size: float,
) -> None:
    doc = pymupdf.open(scan_pdf)
    page = doc[0]
    page.draw_rect(pymupdf.Rect(*erase), color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
    page.insert_font(fontname="ScanGlyphControl", fontfile=str(font_file))
    page.insert_text(pos, text, fontsize=font_size, fontname="ScanGlyphControl", color=(0, 0, 0), overlay=True)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_pdf, garbage=4, deflate=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a tiny font from scanned glyph crops and use it in a PDF edit.")
    parser.add_argument("scan_pdf", type=Path)
    parser.add_argument("metrics_pdf", type=Path)
    parser.add_argument("out_pdf", type=Path)
    parser.add_argument("--font-out", type=Path, required=True)
    parser.add_argument("--crops-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-text", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--erase", nargs=4, type=float, required=True, metavar=("X0", "Y0", "X1", "Y1"))
    parser.add_argument("--pos", nargs=2, type=float, required=True, metavar=("X", "Y"))
    parser.add_argument("--font-size", type=float, default=32.0)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--threshold", type=int, default=220)
    parser.add_argument("--min-area", type=float, default=2.0)
    args = parser.parse_args()

    boxes = raw_char_boxes(args.metrics_pdf, page_number=args.page, source_text=args.source_text)
    image = render_page(args.scan_pdf, page_number=args.page, dpi=args.dpi)
    sources = build_font(
        image,
        boxes,
        text=args.text,
        out_font=args.font_out,
        crops_dir=args.crops_dir,
        dpi=args.dpi,
        threshold=args.threshold,
        min_area=args.min_area,
    )
    edit_with_font(
        args.scan_pdf,
        args.out_pdf,
        font_file=args.font_out,
        erase=tuple(args.erase),
        pos=tuple(args.pos),
        text=args.text,
        font_size=args.font_size,
    )
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(
            {
                "scan_pdf": str(args.scan_pdf),
                "metrics_pdf": str(args.metrics_pdf),
                "out_pdf": str(args.out_pdf),
                "font_out": str(args.font_out),
                "source_text": args.source_text,
                "text": args.text,
                "glyphs": [
                    {
                        **source.__dict__,
                        "crop_path": str(source.crop_path) if source.crop_path else None,
                    }
                    for source in sources
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
