from __future__ import annotations

import json
from pathlib import Path

from pdf_pipeline.ocr.adapters.surya import load_surya_overlay_pages


def test_load_surya_overlay_pages_reads_ocr_blocks(tmp_path: Path) -> None:
    results_json = tmp_path / "results.json"
    results_json.write_text(
        json.dumps(
            {
                "input": [
                    {
                        "page": 0,
                        "image_bbox": [0, 0, 200, 100],
                        "blocks": [
                            {
                                "label": "Text",
                                "html": "<p>Hello <b>world</b></p>",
                                "bbox": [20, 10, 180, 40],
                                "confidence": 0.91,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    pages = load_surya_overlay_pages(results_json, input_stem="input")

    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert pages[0].width == 200
    assert pages[0].height == 100
    assert len(pages[0].boxes) == 1
    assert pages[0].boxes[0].label == "Text"
    assert pages[0].boxes[0].text == "Hello world"
    assert pages[0].boxes[0].confidence == 0.91


def test_load_surya_overlay_pages_reads_layout_bboxes(tmp_path: Path) -> None:
    results_json = tmp_path / "results.json"
    results_json.write_text(
        json.dumps(
            {
                "doc": [
                    {
                        "page": 4,
                        "image_bbox": [0, 0, 300, 400],
                        "bboxes": [{"label": "Table", "bbox": [5, 6, 100, 200]}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    pages = load_surya_overlay_pages(results_json, document_key="doc", box_source="layout")

    assert pages[0].page_number == 5
    assert pages[0].boxes[0].label == "Table"
    assert pages[0].boxes[0].bbox.left == 5


def test_load_surya_overlay_pages_applies_page_offset(tmp_path: Path) -> None:
    results_json = tmp_path / "results.json"
    results_json.write_text(
        json.dumps({"doc": [{"page": 1, "image_bbox": [0, 0, 100, 100], "blocks": []}]}),
        encoding="utf-8",
    )

    pages = load_surya_overlay_pages(results_json, document_key="doc", page_base=1, page_offset=6)

    assert pages[0].page_number == 7
