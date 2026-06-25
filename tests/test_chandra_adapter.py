from __future__ import annotations

import json
from pathlib import Path

from ocrmypdf_paddleocr.adapters.chandra import load_chandra_overlay_pages


def test_load_chandra_overlay_pages_reads_chunks(tmp_path: Path) -> None:
    results_json = tmp_path / "chandra.json"
    results_json.write_text(
        json.dumps(
            {
                "source_page_number": 39,
                "page_box": [0, 0, 200, 100],
                "chunks": [
                    {
                        "label": "Table",
                        "bbox": [20, 10, 180, 90],
                        "content": "<table><tr><td>Hello</td><td>world</td></tr></table>",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    pages = load_chandra_overlay_pages(results_json)

    assert len(pages) == 1
    assert pages[0].page_number == 39
    assert pages[0].width == 200
    assert pages[0].height == 100
    assert len(pages[0].boxes) == 1
    assert pages[0].boxes[0].label == "Table"
    assert pages[0].boxes[0].text == "Hello world"
    assert pages[0].boxes[0].bbox.left == 20


def test_load_chandra_overlay_pages_uses_source_page_index(tmp_path: Path) -> None:
    results_json = tmp_path / "chandra.json"
    results_json.write_text(
        json.dumps({"source_page_index": 6, "page_box": [0, 0, 100, 100], "chunks": []}),
        encoding="utf-8",
    )

    pages = load_chandra_overlay_pages(results_json)

    assert pages[0].page_number == 7


def test_load_chandra_overlay_pages_reads_runner_payload(tmp_path: Path) -> None:
    results_json = tmp_path / "chandra.json"
    results_json.write_text(
        json.dumps(
            {
                "source_pdf": "input.pdf",
                "pages": [
                    {
                        "source_page_number": 2,
                        "page_box": [0, 0, 100, 100],
                        "chunks": [{"label": "Text", "bbox": [10, 10, 90, 90], "content": "<p>Hello</p>"}],
                    },
                    {
                        "source_page_number": 3,
                        "page_box": [0, 0, 100, 100],
                        "chunks": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    pages = load_chandra_overlay_pages(results_json)

    assert len(pages) == 2
    assert pages[0].page_number == 2
    assert len(pages[0].boxes) == 1
    assert pages[1].page_number == 3
