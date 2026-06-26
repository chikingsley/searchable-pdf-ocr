from __future__ import annotations

from pathlib import Path

import fitz

from searchable_pdf_ocr.schema import BBox, OverlayBox, OverlayPage
from searchable_pdf_ocr.visualize import (
    parse_page_spec,
    render_pdf_page_previews,
    visualize_bboxes,
    visualize_overlay_pages,
)


def test_parse_page_spec_accepts_pages_and_ranges() -> None:
    assert parse_page_spec(None) is None
    assert parse_page_spec("1,3-5,7") == {1, 3, 4, 5, 7}


def test_visualize_bboxes_writes_review_pdf(tmp_path: Path) -> None:
    input_pdf = tmp_path / "input.pdf"
    words_jsonl = tmp_path / "words.jsonl"
    output_pdf = tmp_path / "review.pdf"
    with fitz.open() as document:
        page = document.new_page(width=200, height=100)
        page.insert_text((20, 40), "hello")
        document.save(input_pdf)
    words_jsonl.write_text(
        (
            '{"source_image":"page.png","page_number":1,"width":200,"height":100,"dpi":300,'
            '"plain_text":"hello","lines":[{"id":"p0001-l0001","text":"hello",'
            '"bbox":{"left":20,"top":20,"right":80,"bottom":45},"confidence":0.9,'
            '"words":[{"id":"p0001-l0001-w0001","text":"hello",'
            '"bbox":{"left":20,"top":20,"right":80,"bottom":45},"confidence":0.9}]}]}\n'
        ),
        encoding="utf-8",
    )

    pages, lines, words = visualize_bboxes(input_pdf=input_pdf, words_jsonl=words_jsonl, output_pdf=output_pdf)

    assert (pages, lines, words) == (1, 1, 1)
    with fitz.open(output_pdf) as document:
        assert document.page_count == 1


def test_render_pdf_page_previews_writes_png(tmp_path: Path) -> None:
    input_pdf = tmp_path / "input.pdf"
    preview_dir = tmp_path / "previews"
    with fitz.open() as document:
        document.new_page(width=100, height=100)
        document.save(input_pdf)

    previews = render_pdf_page_previews(input_pdf, out_dir=preview_dir, pages=(1,), prefix="page")

    assert len(previews) == 1
    assert previews[0].name == "page-0001.png"
    assert previews[0].is_file()


def test_visualize_overlay_pages_writes_review_pdf(tmp_path: Path) -> None:
    input_pdf = tmp_path / "input.pdf"
    output_pdf = tmp_path / "review.pdf"
    with fitz.open() as document:
        page = document.new_page(width=200, height=100)
        page.insert_text((20, 40), "hello")
        document.save(input_pdf)

    overlay_pages = [
        OverlayPage(
            page_number=1,
            width=200,
            height=100,
            boxes=[
                OverlayBox(
                    id="box-1",
                    label="Text",
                    text="hello",
                    bbox=BBox(left=20, top=20, right=80, bottom=45),
                )
            ],
        )
    ]

    pages, boxes = visualize_overlay_pages(input_pdf=input_pdf, overlay_pages=overlay_pages, output_pdf=output_pdf)

    assert (pages, boxes) == (1, 1)
    with fitz.open(output_pdf) as document:
        assert document.page_count == 1
