from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pymupdf
from PIL import Image, ImageChops


def render_page(pdf: Path, png: Path, *, page_number: int, dpi: int) -> Path:
    doc = pymupdf.open(pdf)
    page = doc[page_number - 1]
    matrix = pymupdf.Matrix(dpi / 72, dpi / 72)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    png.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(png)
    return png


def text_spans(pdf: Path, *, page_number: int) -> list[dict[str, Any]]:
    doc = pymupdf.open(pdf)
    page = doc[page_number - 1]
    raw = page.get_text("dict")
    spans: list[dict[str, Any]] = []
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                if text:
                    spans.append(
                        {
                            "text": text,
                            "font": span.get("font"),
                            "size": span.get("size"),
                            "bbox": span.get("bbox"),
                            "color": span.get("color"),
                        }
                    )
    return spans


def image_diff(left: Path, right: Path, diff: Path) -> dict[str, float | int]:
    left_image = Image.open(left).convert("RGB")
    right_image = Image.open(right).convert("RGB")
    if left_image.size != right_image.size:
        message = f"Rendered sizes differ: {left_image.size} != {right_image.size}"
        raise ValueError(message)
    diff_image = ImageChops.difference(left_image, right_image)
    diff.parent.mkdir(parents=True, exist_ok=True)
    diff_image.save(diff)

    data = np.asarray(diff_image, dtype=np.uint16)
    per_pixel = data.sum(axis=2)
    changed = int(np.count_nonzero(per_pixel))
    total = int(per_pixel.size)
    return {
        "width": left_image.width,
        "height": left_image.height,
        "changed_pixels": changed,
        "total_pixels": total,
        "changed_ratio": changed / total if total else 0.0,
        "mean_abs_channel_delta": float(data.mean()),
        "max_channel_delta": int(data.max(initial=0)),
    }


def probe(pdf: Path, *, page_number: int, out: Path | None) -> dict[str, Any]:
    doc = pymupdf.open(pdf)
    page = doc[page_number - 1]
    spans = text_spans(pdf, page_number=page_number)
    fonts = sorted({str(span["font"]) for span in spans if span.get("font")})
    result = {
        "pdf": str(pdf),
        "page_number": page_number,
        "page_count": doc.page_count,
        "page_size": [page.rect.width, page.rect.height],
        "text": page.get_text().strip(),
        "span_count": len(spans),
        "fonts": fonts,
        "spans": spans,
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def compare(left: Path, right: Path, *, page_number: int, dpi: int, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    left_png = render_page(left, out_dir / "left.png", page_number=page_number, dpi=dpi)
    right_png = render_page(right, out_dir / "right.png", page_number=page_number, dpi=dpi)
    diff_png = out_dir / "diff.png"
    metrics = image_diff(left_png, right_png, diff_png)
    result = {
        "left": str(left),
        "right": str(right),
        "page_number": page_number,
        "dpi": dpi,
        "diff": str(diff_png),
        "metrics": metrics,
        "left_probe": probe(left, page_number=page_number, out=None),
        "right_probe": probe(right, page_number=page_number, out=None),
    }
    (out_dir / "compare.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe and compare PDFs for ClearScan experiments.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe_parser = subparsers.add_parser("probe")
    probe_parser.add_argument("pdf", type=Path)
    probe_parser.add_argument("--page", type=int, default=1)
    probe_parser.add_argument("--out", type=Path)

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("left", type=Path)
    compare_parser.add_argument("right", type=Path)
    compare_parser.add_argument("--page", type=int, default=1)
    compare_parser.add_argument("--dpi", type=int, default=150)
    compare_parser.add_argument("--out-dir", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "probe":
        sys.stdout.write(json.dumps(probe(args.pdf, page_number=args.page, out=args.out), indent=2, ensure_ascii=False))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(
            json.dumps(
                compare(args.left, args.right, page_number=args.page, dpi=args.dpi, out_dir=args.out_dir),
                indent=2,
                ensure_ascii=False,
            )
        )
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
