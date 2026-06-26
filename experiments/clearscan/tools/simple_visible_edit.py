from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf


def visible_edit(
    src: Path,
    out: Path,
    *,
    erase: tuple[float, float, float, float],
    pos: tuple[float, float],
    text: str,
    font: str,
    font_size: float,
) -> None:
    doc = pymupdf.open(src)
    page = doc[0]
    rect = pymupdf.Rect(*erase)
    page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
    page.insert_text(pos, text, fontsize=font_size, fontname=font, color=(0, 0, 0), overlay=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out, garbage=4, deflate=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mask a scanned PDF region and insert visible replacement text.")
    parser.add_argument("src", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--erase", nargs=4, type=float, required=True, metavar=("X0", "Y0", "X1", "Y1"))
    parser.add_argument("--pos", nargs=2, type=float, required=True, metavar=("X", "Y"))
    parser.add_argument("--text", required=True)
    parser.add_argument("--font", default="helv")
    parser.add_argument("--font-size", type=float, default=32.0)
    args = parser.parse_args()
    visible_edit(
        args.src,
        args.out,
        erase=tuple(args.erase),
        pos=tuple(args.pos),
        text=args.text,
        font=args.font,
        font_size=args.font_size,
    )


if __name__ == "__main__":
    main()
