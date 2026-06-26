from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ocrmypdf import OcrClass

from searchable_pdf_ocr.convert import (
    paddle_result_to_page_record,
    page_record_to_element,
    rapidocr_result_to_page_record,
)


def test_paddle_result_to_page_record_uses_native_word_boxes() -> None:
    result = {
        "rec_texts": ["hello world"],
        "rec_scores": [0.98],
        "rec_polys": [[[10, 20], [110, 20], [110, 40], [10, 40]]],
        "text_word": [["hello", " ", "world"]],
        "text_word_region": [
            [
                [[10, 20], [50, 20], [50, 40], [10, 40]],
                [[50, 20], [60, 20], [60, 40], [50, 40]],
                [[60, 20], [110, 20], [110, 40], [60, 40]],
            ],
        ],
    }

    record = paddle_result_to_page_record(
        result,
        source_image=Path("page.png"),
        page_number=1,
        width=200,
        height=100,
        dpi=300,
    )

    assert record.plain_text == "hello world"
    assert [word.text for word in record.words] == ["hello", "world"]
    assert record.words[0].bbox.left == 10
    assert record.words[1].bbox.right == 110


def test_paddle_result_to_page_record_uses_rtl_line_text_for_single_native_box() -> None:
    result = {
        "rec_texts": ["ب كره زمين"],
        "rec_scores": [0.92],
        "rec_polys": [[[180, 20], [260, 20], [260, 40], [180, 40]]],
        "text_word": [["نيمز هرك ب"]],
        "text_word_region": [[[[180, 20], [260, 20], [260, 40], [180, 40]]]],
    }

    record = paddle_result_to_page_record(
        result,
        source_image=Path("page.png"),
        page_number=7,
        width=300,
        height=100,
        dpi=300,
    )

    assert [word.text for word in record.words] == ["ب كره زمين"]
    assert record.words[0].bbox.left == 180
    assert record.words[0].bbox.right == 260


def test_paddle_result_to_page_record_assigns_rtl_line_tokens_to_rightmost_boxes() -> None:
    result = {
        "rec_texts": ["ب كره زمين"],
        "rec_scores": [0.92],
        "rec_polys": [[[10, 20], [90, 20], [90, 40], [10, 40]]],
        "text_word": [["نيمز", " ", "هرك", " ", "ب"]],
        "text_word_region": [
            [
                [[10, 20], [30, 20], [30, 40], [10, 40]],
                [[30, 20], [40, 20], [40, 40], [30, 40]],
                [[40, 20], [70, 20], [70, 40], [40, 40]],
                [[70, 20], [80, 20], [80, 40], [70, 40]],
                [[80, 20], [90, 20], [90, 40], [80, 40]],
            ],
        ],
    }

    record = paddle_result_to_page_record(
        result,
        source_image=Path("page.png"),
        page_number=7,
        width=300,
        height=100,
        dpi=300,
    )

    assert [word.text for word in record.words] == ["ب", "كره", "زمين"]
    assert [(word.bbox.left, word.bbox.right) for word in record.words] == [(80, 90), (40, 70), (10, 30)]


class RapidResult:
    word_results: ClassVar[list[list[list[object]]]] = [
        [
            ["نيمز", 0.99, [[10, 20], [30, 20], [30, 40], [10, 40]]],
            ["هرك", 0.88, [[40, 20], [70, 20], [70, 40], [40, 40]]],
            ["ب", 0.99, [[80, 20], [90, 20], [90, 40], [80, 40]]],
        ]
    ]

    def to_json(self) -> list[dict[str, object]]:
        return [
            {
                "txt": "ب كره زمين",
                "score": 0.93,
                "box": [[10, 20], [90, 20], [90, 40], [10, 40]],
            }
        ]


def test_rapidocr_result_to_page_record_reuses_rtl_line_text_strategy() -> None:
    record = rapidocr_result_to_page_record(
        RapidResult(),
        source_image=Path("page.png"),
        page_number=7,
        width=300,
        height=100,
        dpi=300,
    )

    assert [word.text for word in record.words] == ["ب", "كره", "زمين"]
    assert [(word.bbox.left, word.bbox.right) for word in record.words] == [(80, 90), (40, 70), (10, 30)]


def test_page_record_to_element_builds_ocrmypdf_tree() -> None:
    record = paddle_result_to_page_record(
        {
            "rec_texts": ["hello world"],
            "rec_scores": [0.98],
            "rec_polys": [[[10, 20], [110, 20], [110, 40], [10, 40]]],
        },
        source_image=Path("page.png"),
        page_number=1,
        width=200,
        height=100,
        dpi=300,
    )

    element = page_record_to_element(record)

    assert element.ocr_class == OcrClass.PAGE
    assert element.children[0].ocr_class == OcrClass.LINE
    assert element.children[0].children[0].ocr_class == OcrClass.WORD
