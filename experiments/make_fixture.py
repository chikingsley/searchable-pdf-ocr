from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
TEXT = "CLEARSCAN EDIT TEST 2026"
EDITED_TEXT = "CLEARSCAN EDIT TEST 2027"


def render_pdf_page_to_image(pdf: Path, image: Path, *, dpi: int) -> None:
    doc = pymupdf.open(pdf)
    page = doc[0]
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
    pixmap.save(image)


def image_to_pdf(image: Path, pdf: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.insert_image(page.rect, filename=image)
    doc.save(pdf)


def make_source_pdf(pdf: Path, *, text: str) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.insert_text((72, 120), text, fontsize=32, fontname="helv", color=(0, 0, 0))
    page.insert_text((72, 172), "The edit target is the final digit.", fontsize=14, fontname="helv", color=(0, 0, 0))
    doc.save(pdf)


def make_fixture(out_dir: Path, *, dpi: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    source_pdf = out_dir / "control_source.pdf"
    edited_source_pdf = out_dir / "control_source_edited.pdf"
    source_png = out_dir / "control_source.png"
    scan_pdf = out_dir / "control_scan.pdf"

    make_source_pdf(source_pdf, text=TEXT)
    make_source_pdf(edited_source_pdf, text=EDITED_TEXT)
    render_pdf_page_to_image(source_pdf, source_png, dpi=dpi)
    image_to_pdf(source_png, scan_pdf)

    manifest = out_dir / "manifest.txt"
    manifest.write_text(
        "\n".join(
            [
                f"text={TEXT}",
                f"edited_text={EDITED_TEXT}",
                f"dpi={dpi}",
                f"source_pdf={source_pdf.name}",
                f"edited_source_pdf={edited_source_pdf.name}",
                f"source_png={source_png.name}",
                f"scan_pdf={scan_pdf.name}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a controlled scanned-PDF fixture for ClearScan experiments.")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args()
    make_fixture(args.out_dir, dpi=args.dpi)


if __name__ == "__main__":
    main()
