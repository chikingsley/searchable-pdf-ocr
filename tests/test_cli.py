from __future__ import annotations

from ocrmypdf_paddleocr.cli import build_parser


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


def test_review_chandra_accepts_results_json_and_previews() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "review-chandra",
            "input.pdf",
            "chandra.json",
            "--out",
            "runs/review/chandra.bboxes.pdf",
            "--page-offset",
            "6",
            "--preview-page",
            "1",
        ]
    )

    assert args.input_pdf.name == "input.pdf"
    assert args.results_json.name == "chandra.json"
    assert args.page_offset == 6
    assert args.preview_page == [1]


def test_chandra_ocr_accepts_runtime_options() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "chandra-ocr",
            "input.pdf",
            "runs/chandra",
            "--pages",
            "7",
            "--method",
            "vllm",
            "--vllm-api-base",
            "http://127.0.0.1:8000/v1",
            "--max-output-tokens",
            "2048",
            "--batch-size",
            "1",
            "--review-bboxes",
            "--review-out",
            "runs/chandra/review.pdf",
            "--preview-page",
            "7",
        ]
    )

    assert args.input_pdf.name == "input.pdf"
    assert args.out_dir.name == "chandra"
    assert args.pages == "7"
    assert args.vllm_api_base == "http://127.0.0.1:8000/v1"
    assert args.review_bboxes is True
    assert args.review_out.name == "review.pdf"
    assert args.preview_page == [7]


def test_pipeline_accepts_chandra_sidecar_options() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "pipeline",
            "input.pdf",
            "runs/input",
            "--chandra-sidecar",
            "--chandra-vllm-api-base",
            "http://127.0.0.1:8000/v1",
            "--chandra-review-bboxes",
            "--chandra-preview-page",
            "7",
        ]
    )

    assert args.chandra_sidecar is True
    assert args.chandra_vllm_api_base == "http://127.0.0.1:8000/v1"
    assert args.chandra_review_bboxes is True
    assert args.chandra_preview_page == [7]


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
