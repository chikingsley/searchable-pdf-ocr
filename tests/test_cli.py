from __future__ import annotations

from searchable_pdf_ocr.cli import build_parser


def test_language_option_replaces_default_when_explicit() -> None:
    parser = build_parser()
    args = parser.parse_args(["searchable", "input.pdf", "output.pdf", "--language", "fas"])

    assert args.language == ["fas"]


def test_compare_backends_defaults_to_backend_list_later() -> None:
    parser = build_parser()
    args = parser.parse_args(["compare-backends", "input.pdf", "runs/compare", "--language", "fas"])

    assert args.backend is None
    assert args.language == ["fas"]


def test_review_surya_accepts_results_json_and_previews() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "review-surya",
            "input.pdf",
            "results.json",
            "--out",
            "runs/review/surya.bboxes.pdf",
            "--box-source",
            "ocr",
            "--page-base",
            "1",
            "--page-offset",
            "6",
            "--preview-page",
            "1",
        ]
    )

    assert args.input_pdf.name == "input.pdf"
    assert args.results_json.name == "results.json"
    assert args.box_source == "ocr"
    assert args.page_base == 1
    assert args.page_offset == 6
    assert args.preview_page == [1]


def test_pipeline_accepts_word_review_options() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "pipeline",
            "input.pdf",
            "runs/input",
            "--review-bboxes",
            "--review-pages",
            "7",
            "--review-labels",
            "--preview-page",
            "7",
        ]
    )

    assert args.review_bboxes is True
    assert args.review_pages == "7"
    assert args.review_labels is True
    assert args.preview_page == [7]
