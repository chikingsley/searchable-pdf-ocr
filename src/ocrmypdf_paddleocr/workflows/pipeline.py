from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values

from ocrmypdf_paddleocr.chandra_sidecar import ChandraMethod, ChandraOcrOptions, ChandraOcrResult, run_chandra_ocr
from ocrmypdf_paddleocr.constants import DEFAULT_RECONCILE_MODEL, DEFAULT_SUPERWHISPER_URL
from ocrmypdf_paddleocr.mistral_sidecar import run_mistral_ocr
from ocrmypdf_paddleocr.rebuild import rebuild_pdf
from ocrmypdf_paddleocr.reconcile import reconcile_words
from ocrmypdf_paddleocr.visualize import render_pdf_page_previews, visualize_bboxes
from ocrmypdf_paddleocr.workflows.searchable import (
    EngineName,
    OcrBackendName,
    PrecisionName,
    SearchableOptions,
    run_searchable_pdf,
)

ReconcileMode = Literal["auto", "always", "never"]


@dataclass(frozen=True, slots=True)
class WordReviewResult:
    bboxes_pdf: Path | None
    page_count: int = 0
    line_count: int = 0
    word_count: int = 0
    preview_files: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineOptions:
    input_pdf: Path
    out_dir: Path
    ocr_backend: OcrBackendName = "paddle"
    language: tuple[str, ...] = ("eng",)
    device: str = "cpu"
    ocr_version: str = "PP-OCRv6"
    det_model_name: str | None = None
    rec_model_name: str | None = None
    det_model_dir: str | None = None
    rec_model_dir: str | None = None
    engine: EngineName | None = None
    enable_hpi: bool = False
    use_tensorrt: bool = False
    precision: PrecisionName = "fp32"
    cpu_threads: int | None = None
    rec_batch_size: int | None = None
    enable_orientation: bool = False
    enable_unwarping: bool = False
    pages: str | None = None
    jobs: int | None = None
    force_ocr: bool = False
    skip_text: bool = False
    deskew: bool = False
    rotate_pages: bool = False
    review_bboxes: bool = False
    review_pages: str | None = None
    review_labels: bool = False
    preview_pages: tuple[int, ...] = ()
    optimize: int = 1
    output_type: str = "pdf"
    env_file: Path | None = None
    reconcile_mode: ReconcileMode = "auto"
    rebuild_corrected: bool = True
    superwhisper_base_url: str = DEFAULT_SUPERWHISPER_URL
    reconcile_model: str = DEFAULT_RECONCILE_MODEL
    reconcile_timeout: float = 600.0
    final_pdf: Path | None = None
    final_suffix: str = "-OCR"
    font_file: Path | None = None
    chandra_sidecar: bool = False
    chandra_method: ChandraMethod = "vllm"
    chandra_vllm_api_base: str | None = None
    chandra_max_output_tokens: int | None = 2048
    chandra_batch_size: int = 1
    chandra_max_workers: int | None = None
    chandra_max_retries: int | None = None
    chandra_max_failure_retries: int | None = None
    chandra_temperature: float = 0.0
    chandra_top_p: float = 0.1
    chandra_include_images: bool = False
    chandra_include_headers_footers: bool = False
    chandra_review_bboxes: bool = False
    chandra_review_pages: str | None = None
    chandra_labels: bool = False
    chandra_preview_pages: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class PipelineResult:
    input_pdf: Path
    out_dir: Path
    searchable_pdf: Path
    words_jsonl: Path
    word_review_pdf: Path | None
    word_review_page_count: int
    word_review_line_count: int
    word_review_word_count: int
    word_preview_files: tuple[Path, ...]
    mistral_markdown: Path
    chandra_result: ChandraOcrResult | None
    corrected_words_jsonl: Path | None
    corrected_searchable_pdf: Path | None
    final_pdf: Path
    manifest_file: Path
    searchable_exit_code: int
    mistral_pages: int
    reconcile_status: str
    reconcile_pages: int
    corrections: int
    rebuild_pages: int
    rebuild_boxes: int

    def manifest(self) -> dict[str, object]:
        return {
            "input_pdf": os.fspath(self.input_pdf),
            "out_dir": os.fspath(self.out_dir),
            "steps": {
                "searchable": {
                    "status": "done",
                    "exit_code": self.searchable_exit_code,
                    "pdf": os.fspath(self.searchable_pdf),
                    "words_jsonl": os.fspath(self.words_jsonl),
                },
                "word_review": word_review_manifest(self),
                "mistral": {
                    "status": "done",
                    "pages": self.mistral_pages,
                    "markdown": os.fspath(self.mistral_markdown),
                },
                "chandra": chandra_manifest(self.chandra_result),
                "reconcile": {
                    "status": self.reconcile_status,
                    "pages": self.reconcile_pages,
                    "corrections": self.corrections,
                    "words_jsonl": _optional_path(self.corrected_words_jsonl),
                    "sidecars": sidecar_manifest_paths(self.mistral_markdown, self.chandra_result),
                },
                "rebuild": {
                    "status": "done" if self.corrected_searchable_pdf else "skipped",
                    "pages": self.rebuild_pages,
                    "boxes": self.rebuild_boxes,
                    "pdf": _optional_path(self.corrected_searchable_pdf),
                },
                "final": {
                    "status": "done",
                    "pdf": os.fspath(self.final_pdf),
                },
            },
            "manifest": os.fspath(self.manifest_file),
        }


def run_pipeline(options: PipelineOptions) -> PipelineResult:
    input_pdf = options.input_pdf.expanduser().resolve()
    out_dir = options.out_dir.expanduser().resolve()
    stem = input_pdf.stem
    searchable_pdf = out_dir / "searchable" / f"{stem}.searchable.pdf"
    words_jsonl = out_dir / "searchable" / f"{stem}.words.jsonl"
    corrected_words_jsonl = out_dir / "reconcile" / f"{stem}.corrected.words.jsonl"
    corrected_pdf = out_dir / "rebuild" / f"{stem}.corrected.searchable.pdf"
    final_pdf = (
        options.final_pdf.expanduser().resolve()
        if options.final_pdf
        else out_dir / "final" / f"{stem}{options.final_suffix}.pdf"
    )
    manifest_file = out_dir / f"{stem}.pipeline.json"

    searchable_exit_code = run_searchable_pdf(
        SearchableOptions(
            input_pdf=input_pdf,
            output_pdf=searchable_pdf,
            ocr_backend=options.ocr_backend,
            language=options.language,
            device=options.device,
            ocr_version=options.ocr_version,
            det_model_name=options.det_model_name,
            rec_model_name=options.rec_model_name,
            det_model_dir=options.det_model_dir,
            rec_model_dir=options.rec_model_dir,
            engine=options.engine,
            enable_hpi=options.enable_hpi,
            use_tensorrt=options.use_tensorrt,
            precision=options.precision,
            cpu_threads=options.cpu_threads,
            rec_batch_size=options.rec_batch_size,
            enable_orientation=options.enable_orientation,
            enable_unwarping=options.enable_unwarping,
            words_jsonl=words_jsonl,
            pages=options.pages,
            jobs=options.jobs,
            force_ocr=options.force_ocr,
            skip_text=options.skip_text,
            deskew=options.deskew,
            rotate_pages=options.rotate_pages,
            optimize=options.optimize,
            output_type=options.output_type,
        )
    )
    if searchable_exit_code != 0:
        raise SystemExit(searchable_exit_code)

    word_review = run_pipeline_word_review(options, input_pdf=input_pdf, words_jsonl=words_jsonl, out_dir=out_dir)

    mistral_result = run_mistral_ocr(
        input_pdf,
        out_dir / "sidecars",
        pages=options.pages,
        env_file=options.env_file.expanduser().resolve() if options.env_file else None,
    )
    chandra_result = run_pipeline_chandra_sidecar(options, input_pdf=input_pdf, out_dir=out_dir)

    token = superwhisper_api_key(options.env_file)
    run_reconcile = should_reconcile(options.reconcile_mode, token)
    corrected_jsonl_for_result: Path | None = None
    reconcile_pages = 0
    corrections = 0
    reconcile_status = "skipped-key-missing" if options.reconcile_mode == "auto" else "skipped"
    if options.reconcile_mode == "always" and token is None:
        raise SystemExit("SUPERWHISPER_API_KEY is required for --reconcile.")
    if run_reconcile:
        sidecars = [mistral_result.combined_file]
        if chandra_result:
            sidecars.append(chandra_result.markdown_file)
        reconcile_pages, corrections = reconcile_words(
            words_jsonl=words_jsonl,
            sidecars=sidecars,
            output_jsonl=corrected_words_jsonl,
            base_url=options.superwhisper_base_url,
            model=options.reconcile_model,
            timeout=options.reconcile_timeout,
            api_key=token,
        )
        corrected_jsonl_for_result = corrected_words_jsonl
        reconcile_status = "done"

    corrected_pdf_for_result: Path | None = None
    rebuild_pages = 0
    rebuild_boxes = 0
    if corrected_jsonl_for_result and options.rebuild_corrected:
        rebuild_pages, rebuild_boxes = rebuild_pdf(
            input_pdf, corrected_jsonl_for_result, corrected_pdf, font_file=options.font_file
        )
        corrected_pdf_for_result = corrected_pdf
    final_source_pdf = corrected_pdf_for_result or searchable_pdf
    final_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final_source_pdf, final_pdf)

    result = PipelineResult(
        input_pdf=input_pdf,
        out_dir=out_dir,
        searchable_pdf=searchable_pdf,
        words_jsonl=words_jsonl,
        word_review_pdf=word_review.bboxes_pdf,
        word_review_page_count=word_review.page_count,
        word_review_line_count=word_review.line_count,
        word_review_word_count=word_review.word_count,
        word_preview_files=word_review.preview_files,
        mistral_markdown=mistral_result.combined_file,
        chandra_result=chandra_result,
        corrected_words_jsonl=corrected_jsonl_for_result,
        corrected_searchable_pdf=corrected_pdf_for_result,
        final_pdf=final_pdf,
        manifest_file=manifest_file,
        searchable_exit_code=searchable_exit_code,
        mistral_pages=mistral_result.page_count,
        reconcile_status=reconcile_status,
        reconcile_pages=reconcile_pages,
        corrections=corrections,
        rebuild_pages=rebuild_pages,
        rebuild_boxes=rebuild_boxes,
    )
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(result.manifest(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def run_pipeline_word_review(
    options: PipelineOptions, *, input_pdf: Path, words_jsonl: Path, out_dir: Path
) -> WordReviewResult:
    if options.review_bboxes is False and options.preview_pages == ():
        return WordReviewResult(bboxes_pdf=None)
    stem = input_pdf.stem
    output_pdf = out_dir / "review-bboxes" / f"{stem}.words.bboxes.pdf"
    pages = options.review_pages or options.pages
    page_count, line_count, word_count = visualize_bboxes(
        input_pdf=input_pdf,
        words_jsonl=words_jsonl,
        output_pdf=output_pdf,
        pages=pages,
        labels=options.review_labels,
    )
    preview_files = render_pdf_page_previews(
        output_pdf,
        out_dir=output_pdf.parent / "previews",
        pages=options.preview_pages,
        prefix=output_pdf.stem,
    )
    return WordReviewResult(
        bboxes_pdf=output_pdf,
        page_count=page_count,
        line_count=line_count,
        word_count=word_count,
        preview_files=tuple(preview_files),
    )


def run_pipeline_chandra_sidecar(
    options: PipelineOptions, *, input_pdf: Path, out_dir: Path
) -> ChandraOcrResult | None:
    if options.chandra_sidecar is False:
        return None
    return run_chandra_ocr(
        ChandraOcrOptions(
            input_pdf=input_pdf,
            out_dir=out_dir / "sidecars" / "chandra",
            pages=options.pages,
            method=options.chandra_method,
            vllm_api_base=options.chandra_vllm_api_base,
            max_output_tokens=options.chandra_max_output_tokens,
            batch_size=options.chandra_batch_size,
            max_workers=options.chandra_max_workers,
            max_retries=options.chandra_max_retries,
            max_failure_retries=options.chandra_max_failure_retries,
            temperature=options.chandra_temperature,
            top_p=options.chandra_top_p,
            include_images=options.chandra_include_images,
            include_headers_footers=options.chandra_include_headers_footers,
            review_bboxes=options.chandra_review_bboxes,
            review_pages=options.chandra_review_pages,
            review_labels=options.chandra_labels,
            preview_pages=options.chandra_preview_pages,
        )
    )


def superwhisper_api_key(env_file: Path | None = None) -> str | None:
    value = os.environ.get("SUPERWHISPER_API_KEY")
    if value and value.strip():
        return value
    if env_file is None:
        return None
    candidate = env_file.expanduser()
    if candidate.is_file():
        file_value = dotenv_values(candidate).get("SUPERWHISPER_API_KEY")
        if file_value and file_value.strip():
            return file_value
    return None


def should_reconcile(mode: ReconcileMode, api_key: str | None) -> bool:
    if mode == "never":
        return False
    if mode == "always":
        return True
    return isinstance(api_key, str)


def _optional_path(path: Path | None) -> str | None:
    return os.fspath(path) if path else None


def chandra_manifest(result: ChandraOcrResult | None) -> dict[str, object]:
    if result is None:
        return {"status": "skipped"}
    return {
        "status": "done",
        "pages": result.page_count,
        "tokens": result.total_token_count,
        "chunks": result.total_chunk_count,
        "chunk_labels": dict(result.chunk_labels),
        "json": os.fspath(result.json_file),
        "markdown": os.fspath(result.markdown_file),
        "html": os.fspath(result.html_file),
        "metadata": os.fspath(result.metadata_file),
        "bboxes_pdf": _optional_path(result.bboxes_pdf),
        "review_pages": result.review_page_count,
        "review_boxes": result.review_box_count,
        "previews": [os.fspath(path) for path in result.preview_files],
    }


def word_review_manifest(result: PipelineResult) -> dict[str, object]:
    if result.word_review_pdf is None:
        return {"status": "skipped"}
    return {
        "status": "done",
        "pdf": os.fspath(result.word_review_pdf),
        "pages": result.word_review_page_count,
        "lines": result.word_review_line_count,
        "words": result.word_review_word_count,
        "previews": [os.fspath(path) for path in result.word_preview_files],
    }


def sidecar_manifest_paths(mistral_markdown: Path, chandra_result: ChandraOcrResult | None) -> list[str]:
    sidecars = [os.fspath(mistral_markdown)]
    if chandra_result:
        sidecars.append(os.fspath(chandra_result.markdown_file))
    return sidecars
