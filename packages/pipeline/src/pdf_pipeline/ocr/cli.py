from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pdf_pipeline.ocr.adapters.surya import load_surya_overlay_pages
from pdf_pipeline.ocr.constants import DEFAULT_DEVICE, DEFAULT_OCR_VERSION, DEFAULT_RECONCILE_MODEL
from pdf_pipeline.ocr.mistral_sidecar import run_mistral_ocr
from pdf_pipeline.ocr.rebuild import rebuild_pdf
from pdf_pipeline.ocr.reconcile import reconcile_words
from pdf_pipeline.ocr.visualize import render_pdf_page_previews, visualize_bboxes, visualize_overlay_pages
from pdf_pipeline.ocr.workflows.compare import CompareOptions, run_compare
from pdf_pipeline.ocr.workflows.pipeline import PipelineOptions, run_pipeline
from pdf_pipeline.ocr.workflows.searchable import SearchableOptions, run_searchable_pdf

COMMANDS = {
    "searchable",
    "mistral-ocr",
    "reconcile",
    "rebuild",
    "review-bboxes",
    "review-surya",
    "compare-backends",
    "pipeline",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="searchable-pdf-ocr")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_searchable_command(subparsers)
    add_mistral_command(subparsers)
    add_reconcile_command(subparsers)
    add_rebuild_command(subparsers)
    add_review_bboxes_command(subparsers)
    add_review_surya_command(subparsers)
    add_compare_backends_command(subparsers)
    add_pipeline_command(subparsers)
    return parser


def add_searchable_arguments(parser: argparse.ArgumentParser, *, include_ocr_backend: bool = True) -> None:
    if include_ocr_backend:
        parser.add_argument("--ocr-backend", choices=("paddle", "rapidocr"), default="rapidocr")
    parser.add_argument("-l", "--language", action="append")
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--ocr-version", default=DEFAULT_OCR_VERSION)
    parser.add_argument("--det-model-name")
    parser.add_argument("--rec-model-name")
    parser.add_argument("--det-model-dir")
    parser.add_argument("--rec-model-dir")
    parser.add_argument("--engine", choices=("paddle", "paddle_static", "paddle_dynamic", "onnxruntime"))
    parser.add_argument("--enable-hpi", action="store_true")
    parser.add_argument("--use-tensorrt", action="store_true")
    parser.add_argument("--precision", choices=("fp32", "fp16"), default="fp32")
    parser.add_argument("--cpu-threads", type=int)
    parser.add_argument("--rec-batch-size", type=int)
    parser.add_argument("--enable-orientation", action="store_true")
    parser.add_argument("--enable-unwarping", action="store_true")
    parser.add_argument("--pages")
    parser.add_argument("--jobs", type=int)
    parser.add_argument("--force-ocr", action="store_true")
    parser.add_argument("--skip-text", action="store_true")
    parser.add_argument("--deskew", action="store_true")
    parser.add_argument("--rotate-pages", action="store_true")
    parser.add_argument("--optimize", type=int, default=1)
    parser.add_argument("--output-type", default="pdf")


def add_searchable_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    searchable = subparsers.add_parser("searchable")
    searchable.add_argument("input_pdf", type=Path)
    searchable.add_argument("output_pdf", type=Path)
    add_searchable_arguments(searchable)
    searchable.add_argument("--words-jsonl", type=Path)
    searchable.set_defaults(func=run_searchable)


def add_mistral_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    mistral = subparsers.add_parser("mistral-ocr")
    mistral.add_argument("input_pdf", type=Path)
    mistral.add_argument("--out-dir", type=Path, default=Path("runs/sidecars"))
    mistral.add_argument("--pages")
    mistral.add_argument("--env-file", type=Path)
    mistral.set_defaults(func=run_mistral)


def add_reconcile_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    reconcile = subparsers.add_parser("reconcile")
    reconcile.add_argument("--words-jsonl", type=Path, required=True)
    reconcile.add_argument("--sidecar", type=Path, action="append", required=True)
    reconcile.add_argument("--out", type=Path, required=True)
    reconcile.add_argument("--base-url", default="http://127.0.0.1:8787")
    reconcile.add_argument("--model", default=DEFAULT_RECONCILE_MODEL)
    reconcile.add_argument("--timeout", type=float, default=600.0)
    reconcile.set_defaults(func=run_reconcile)


def add_rebuild_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    rebuild = subparsers.add_parser("rebuild")
    rebuild.add_argument("input_pdf", type=Path)
    rebuild.add_argument("--words-jsonl", type=Path, required=True)
    rebuild.add_argument("--out", type=Path, required=True)
    rebuild.add_argument("--font-file", type=Path)
    rebuild.set_defaults(func=run_rebuild)


def add_review_bboxes_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    review = subparsers.add_parser("review-bboxes")
    review.add_argument("input_pdf", type=Path)
    review.add_argument("--words-jsonl", type=Path, required=True)
    review.add_argument("--out", type=Path, required=True)
    review.add_argument("--pages")
    review.add_argument("--labels", action="store_true")
    review.add_argument("--skip-lines", action="store_true")
    review.add_argument("--skip-words", action="store_true")
    review.set_defaults(func=run_review_bboxes)


def add_review_surya_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    review = subparsers.add_parser("review-surya")
    review.add_argument("input_pdf", type=Path)
    review.add_argument("results_json", type=Path)
    review.add_argument("--out", type=Path, required=True)
    review.add_argument("--document-key")
    review.add_argument("--box-source", choices=("auto", "ocr", "layout", "detect"), default="auto")
    review.add_argument("--page-base", type=int, choices=(0, 1), default=0)
    review.add_argument("--page-offset", type=int, default=0)
    review.add_argument("--pages")
    review.add_argument("--labels", action="store_true")
    review.add_argument("--preview-page", type=int, action="append")
    review.set_defaults(func=run_review_surya)


def add_compare_backends_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    compare = subparsers.add_parser("compare-backends")
    compare.add_argument("input_pdf", type=Path)
    compare.add_argument("out_dir", type=Path)
    compare.add_argument("--backend", choices=("paddle", "rapidocr"), action="append")
    compare.add_argument("--preview-page", type=int, action="append")
    add_searchable_arguments(compare, include_ocr_backend=False)
    compare.set_defaults(func=run_compare_backends)


def add_pipeline_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    pipeline = subparsers.add_parser("pipeline")
    pipeline.add_argument("input_pdf", type=Path)
    pipeline.add_argument("out_dir", type=Path)
    add_searchable_arguments(pipeline)
    pipeline.add_argument("--env-file", type=Path)
    reconcile_mode = pipeline.add_mutually_exclusive_group()
    reconcile_mode.add_argument(
        "--reconcile",
        dest="reconcile_mode",
        action="store_const",
        const="always",
        default="auto",
        help="Run Superwhisper/Sonnet reconciliation and fail if no API key is available.",
    )
    reconcile_mode.add_argument(
        "--no-reconcile",
        dest="reconcile_mode",
        action="store_const",
        const="never",
        help="Skip Superwhisper/Sonnet reconciliation.",
    )
    rebuild_mode = pipeline.add_mutually_exclusive_group()
    rebuild_mode.add_argument(
        "--rebuild-corrected",
        dest="rebuild_corrected",
        action="store_true",
        default=True,
        help="Rebuild a corrected searchable PDF when reconciliation runs.",
    )
    rebuild_mode.add_argument(
        "--no-rebuild",
        dest="rebuild_corrected",
        action="store_false",
        help="Skip the corrected-PDF rebuild.",
    )
    pipeline.add_argument("--base-url", default="http://127.0.0.1:8787")
    pipeline.add_argument("--model", default=DEFAULT_RECONCILE_MODEL)
    pipeline.add_argument("--timeout", type=float, default=600.0)
    pipeline.add_argument("--final-pdf", type=Path, help="Copy the best generated PDF to this path.")
    pipeline.add_argument("--final-suffix", default="-OCR", help="Suffix for the default final PDF name.")
    pipeline.add_argument("--font-file", type=Path, help="Font file for corrected PDF text insertion.")
    pipeline.add_argument("--review-bboxes", action="store_true")
    pipeline.add_argument("--review-pages")
    pipeline.add_argument("--review-labels", action="store_true")
    pipeline.add_argument("--preview-page", type=int, action="append")
    pipeline.set_defaults(func=run_pipeline_command)


def run_searchable(args: argparse.Namespace) -> int:
    return run_searchable_pdf(
        SearchableOptions(
            input_pdf=args.input_pdf,
            output_pdf=args.output_pdf,
            ocr_backend=args.ocr_backend,
            language=tuple(args.language or ["eng"]),
            device=args.device,
            ocr_version=args.ocr_version,
            det_model_name=args.det_model_name,
            rec_model_name=args.rec_model_name,
            det_model_dir=args.det_model_dir,
            rec_model_dir=args.rec_model_dir,
            engine=args.engine,
            enable_hpi=args.enable_hpi,
            use_tensorrt=args.use_tensorrt,
            precision=args.precision,
            cpu_threads=args.cpu_threads,
            rec_batch_size=args.rec_batch_size,
            enable_orientation=args.enable_orientation,
            enable_unwarping=args.enable_unwarping,
            words_jsonl=args.words_jsonl,
            pages=args.pages,
            jobs=args.jobs,
            force_ocr=args.force_ocr,
            skip_text=args.skip_text,
            deskew=args.deskew,
            rotate_pages=args.rotate_pages,
            optimize=args.optimize,
            output_type=args.output_type,
        )
    )


def run_mistral(args: argparse.Namespace) -> int:
    result = run_mistral_ocr(
        args.input_pdf.expanduser().resolve(),
        args.out_dir.expanduser(),
        pages=args.pages,
        env_file=args.env_file.expanduser().resolve() if args.env_file else None,
    )
    print(f"pages={result.page_count}")
    print(f"markdown={result.combined_file}")
    return 0


def run_reconcile(args: argparse.Namespace) -> int:
    pages, corrections = reconcile_words(
        words_jsonl=args.words_jsonl.expanduser().resolve(),
        sidecars=[path.expanduser().resolve() for path in args.sidecar],
        output_jsonl=args.out.expanduser(),
        base_url=args.base_url,
        model=args.model,
        timeout=args.timeout,
    )
    print(f"pages={pages} corrections={corrections}")
    print(f"out={args.out}")
    return 0


def run_rebuild(args: argparse.Namespace) -> int:
    pages, boxes = rebuild_pdf(
        args.input_pdf.expanduser().resolve(),
        args.words_jsonl.expanduser().resolve(),
        args.out.expanduser(),
        font_file=args.font_file.expanduser().resolve() if args.font_file else None,
    )
    print(f"pages={pages} boxes={boxes}")
    print(f"out={args.out}")
    return 0


def run_review_bboxes(args: argparse.Namespace) -> int:
    pages, lines, words = visualize_bboxes(
        input_pdf=args.input_pdf.expanduser().resolve(),
        words_jsonl=args.words_jsonl.expanduser().resolve(),
        output_pdf=args.out.expanduser(),
        pages=args.pages,
        draw_lines=args.skip_lines is False,
        draw_words=args.skip_words is False,
        labels=args.labels,
    )
    print(f"pages={pages} lines={lines} words={words}")
    print(f"out={args.out}")
    return 0


def run_review_surya(args: argparse.Namespace) -> int:
    input_pdf = args.input_pdf.expanduser().resolve()
    output_pdf = args.out.expanduser()
    overlay_pages = load_surya_overlay_pages(
        args.results_json.expanduser().resolve(),
        input_stem=input_pdf.stem,
        document_key=args.document_key,
        box_source=args.box_source,
        page_base=args.page_base,
        page_offset=args.page_offset,
    )
    pages, boxes = visualize_overlay_pages(
        input_pdf=input_pdf,
        overlay_pages=overlay_pages,
        output_pdf=output_pdf,
        pages=args.pages,
        labels=args.labels,
    )
    preview_files = render_pdf_page_previews(
        output_pdf,
        out_dir=output_pdf.parent / "previews",
        pages=tuple(args.preview_page or []),
        prefix=output_pdf.stem,
    )
    print(f"pages={pages} boxes={boxes}")
    print(f"out={output_pdf}")
    for preview_file in preview_files:
        print(f"preview={preview_file}")
    return 0


def run_compare_backends(args: argparse.Namespace) -> int:
    result = run_compare(
        CompareOptions(
            input_pdf=args.input_pdf,
            out_dir=args.out_dir,
            backends=tuple(args.backend or ["paddle", "rapidocr"]),
            language=tuple(args.language or ["eng"]),
            device=args.device,
            ocr_version=args.ocr_version,
            det_model_name=args.det_model_name,
            rec_model_name=args.rec_model_name,
            det_model_dir=args.det_model_dir,
            rec_model_dir=args.rec_model_dir,
            engine=args.engine,
            enable_hpi=args.enable_hpi,
            use_tensorrt=args.use_tensorrt,
            precision=args.precision,
            cpu_threads=args.cpu_threads,
            rec_batch_size=args.rec_batch_size,
            enable_orientation=args.enable_orientation,
            enable_unwarping=args.enable_unwarping,
            pages=args.pages,
            jobs=args.jobs,
            force_ocr=args.force_ocr,
            skip_text=args.skip_text,
            deskew=args.deskew,
            rotate_pages=args.rotate_pages,
            optimize=args.optimize,
            output_type=args.output_type,
            preview_pages=tuple(args.preview_page or []),
        )
    )
    for backend in result.backends:
        print(
            f"{backend.backend}: pages={backend.pages} lines={backend.lines} words={backend.words} "
            f"seconds={backend.elapsed_seconds:.2f}"
        )
        print(f"{backend.backend}_pdf={backend.searchable_pdf}")
        print(f"{backend.backend}_words_jsonl={backend.words_jsonl}")
        print(f"{backend.backend}_bboxes_pdf={backend.bboxes_pdf}")
        for preview_file in backend.preview_files:
            print(f"{backend.backend}_preview={preview_file}")
    print(f"manifest={result.manifest_file}")
    return 0


def run_pipeline_command(args: argparse.Namespace) -> int:
    result = run_pipeline(
        PipelineOptions(
            input_pdf=args.input_pdf,
            out_dir=args.out_dir,
            ocr_backend=args.ocr_backend,
            language=tuple(args.language or ["eng"]),
            device=args.device,
            ocr_version=args.ocr_version,
            det_model_name=args.det_model_name,
            rec_model_name=args.rec_model_name,
            det_model_dir=args.det_model_dir,
            rec_model_dir=args.rec_model_dir,
            engine=args.engine,
            enable_hpi=args.enable_hpi,
            use_tensorrt=args.use_tensorrt,
            precision=args.precision,
            cpu_threads=args.cpu_threads,
            rec_batch_size=args.rec_batch_size,
            enable_orientation=args.enable_orientation,
            enable_unwarping=args.enable_unwarping,
            pages=args.pages,
            jobs=args.jobs,
            force_ocr=args.force_ocr,
            skip_text=args.skip_text,
            deskew=args.deskew,
            rotate_pages=args.rotate_pages,
            optimize=args.optimize,
            output_type=args.output_type,
            env_file=args.env_file,
            reconcile_mode=args.reconcile_mode,
            rebuild_corrected=args.rebuild_corrected,
            superwhisper_base_url=args.base_url,
            reconcile_model=args.model,
            reconcile_timeout=args.timeout,
            final_pdf=args.final_pdf,
            final_suffix=args.final_suffix,
            font_file=args.font_file,
            review_bboxes=args.review_bboxes,
            review_pages=args.review_pages,
            review_labels=args.review_labels,
            preview_pages=tuple(args.preview_page or ()),
        )
    )
    print(f"searchable_pdf={result.searchable_pdf}")
    print(f"words_jsonl={result.words_jsonl}")
    if result.word_review_pdf:
        print(f"word_bboxes_pdf={result.word_review_pdf}")
    for preview_file in result.word_preview_files:
        print(f"word_preview={preview_file}")
    print(f"mistral_markdown={result.mistral_markdown}")
    print(f"reconcile={result.reconcile_status}")
    if result.corrected_words_jsonl:
        print(f"corrected_words_jsonl={result.corrected_words_jsonl}")
    if result.corrected_searchable_pdf:
        print(f"corrected_searchable_pdf={result.corrected_searchable_pdf}")
    print(f"final_pdf={result.final_pdf}")
    print(f"manifest={result.manifest_file}")
    return 0


def normalized_argv(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        return None
    if argv == [] or argv[0] in COMMANDS or argv[0] in {"-h", "--help"}:
        return argv
    return ["searchable", *argv]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    args = parser.parse_args(normalized_argv(argv))
    return int(args.func(args))
