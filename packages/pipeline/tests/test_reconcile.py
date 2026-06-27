from __future__ import annotations

import pytest
from pdf_pipeline.ocr.reconcile import changed_correction_map, extract_json
from pdf_pipeline.ocr.schema import BBox, LineRecord, PageRecord, ReconcileResponse, WordRecord


def test_extract_json_accepts_plain_object() -> None:
    payload = extract_json('{"page_number": 1, "corrections": []}')

    assert payload == {"page_number": 1, "corrections": []}


def test_extract_json_accepts_fenced_object() -> None:
    payload = extract_json('```json\n{"page_number": 2, "corrections": []}\n```')

    assert payload == {"page_number": 2, "corrections": []}


def test_extract_json_uses_first_valid_object() -> None:
    payload = extract_json('notes\n{"page_number": 3, "corrections": []}\n{"ignored": true}')

    assert payload == {"page_number": 3, "corrections": []}


def test_extract_json_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        extract_json("[]")


def test_changed_correction_map_drops_no_ops_and_unknown_ids() -> None:
    bbox = BBox(left=0, top=0, right=10, bottom=10)
    record = PageRecord(
        source_image="page.png",
        page_number=1,
        width=100,
        height=100,
        dpi=300,
        plain_text="DESCEIPTORS prices",
        lines=[
            LineRecord(
                id="p0001-l0001",
                text="DESCEIPTORS prices",
                bbox=bbox,
                words=[
                    WordRecord(id="p0001-l0001-w0001", text="DESCEIPTORS", bbox=bbox),
                    WordRecord(id="p0001-l0001-w0002", text="prices", bbox=bbox),
                ],
            )
        ],
    )
    reconcile = ReconcileResponse.model_validate(
        {
            "page_number": 1,
            "corrections": [
                {"word_id": "p0001-l0001-w0001", "text": "DESCRIPTORS"},
                {"word_id": "p0001-l0001-w0002", "text": "prices"},
                {"word_id": "unknown", "text": "ignored"},
            ],
        }
    )

    assert changed_correction_map(record, reconcile) == {"p0001-l0001-w0001": "DESCRIPTORS"}
