from __future__ import annotations

from pathlib import Path

import fitz

from searchable_pdf_ocr.rebuild import load_page_records, rebuild_pdf, sort_page_records_jsonl


def test_rebuild_pdf_inserts_hidden_text(tmp_path: Path) -> None:
    input_pdf = tmp_path / "input.pdf"
    words_jsonl = tmp_path / "words.jsonl"
    output_pdf = tmp_path / "output.pdf"

    with fitz.open() as document:
        page = document.new_page(width=200, height=100)
        page.insert_text((10, 20), "scan placeholder", fontsize=10)
        document.save(input_pdf)

    words_jsonl.write_text(
        (
            '{"source_image":"page.png","page_number":1,"width":200,"height":100,"dpi":72,'
            '"plain_text":"hidden text","lines":[{"id":"p0001-l0001","text":"hidden text",'
            '"bbox":{"left":10,"top":20,"right":120,"bottom":40},"words":[{"id":"p0001-l0001-w0001",'
            '"text":"hidden","bbox":{"left":10,"top":20,"right":60,"bottom":40}},{"id":"p0001-l0001-w0002",'
            '"text":"text","bbox":{"left":65,"top":20,"right":120,"bottom":40}}]}]}\n'
        ),
        encoding="utf-8",
    )

    pages, boxes = rebuild_pdf(input_pdf, words_jsonl, output_pdf)

    assert pages == 1
    assert boxes == 2
    with fitz.open(output_pdf) as document:
        assert "hidden" in document[0].get_text()


def test_sort_page_records_jsonl_orders_by_page(tmp_path: Path) -> None:
    words_jsonl = tmp_path / "words.jsonl"
    page_two = (
        '{"source_image":"page.png","page_number":2,"width":200,"height":100,"dpi":72,"plain_text":"","lines":[]}\n'
    )
    page_one = (
        '{"source_image":"page.png","page_number":1,"width":200,"height":100,"dpi":72,"plain_text":"","lines":[]}\n'
    )
    words_jsonl.write_text(page_two + page_one, encoding="utf-8")

    count = sort_page_records_jsonl(words_jsonl)
    records = load_page_records(words_jsonl)

    assert count == 2
    assert [record.page_number for record in records] == [1, 2]
