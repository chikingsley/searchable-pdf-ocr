from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import ocrmypdf

from ocrmypdf_paddleocr.constants import DEFAULT_DEVICE, DEFAULT_OCR_VERSION
from ocrmypdf_paddleocr.rebuild import sort_page_records_jsonl
from ocrmypdf_paddleocr.runtime import paddle_plugin_manager

EngineName = Literal["paddle", "paddle_static", "paddle_dynamic", "onnxruntime"]
PrecisionName = Literal["fp32", "fp16"]
OcrBackendName = Literal["paddle", "rapidocr"]


@dataclass(frozen=True, slots=True, kw_only=True)
class SearchableOptions:
    input_pdf: Path
    output_pdf: Path
    ocr_backend: OcrBackendName = "paddle"
    language: tuple[str, ...] = ("eng",)
    device: str = DEFAULT_DEVICE
    ocr_version: str = DEFAULT_OCR_VERSION
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
    words_jsonl: Path | None = None
    pages: str | None = None
    jobs: int | None = None
    force_ocr: bool = False
    skip_text: bool = False
    deskew: bool = False
    rotate_pages: bool = False
    optimize: int = 1
    output_type: str = "pdf"


def run_searchable_pdf(options: SearchableOptions) -> int:
    options.output_pdf.parent.mkdir(parents=True, exist_ok=True)
    if options.words_jsonl:
        options.words_jsonl.parent.mkdir(parents=True, exist_ok=True)
        if options.words_jsonl.exists():
            options.words_jsonl.unlink()
    exit_code = ocrmypdf.ocr(
        options.input_pdf,
        options.output_pdf,
        language=list(options.language),
        jobs=options.jobs,
        force_ocr=options.force_ocr,
        skip_text=options.skip_text,
        deskew=options.deskew,
        rotate_pages=options.rotate_pages,
        optimize=options.optimize,
        output_type=options.output_type,
        pages=options.pages,
        progress_bar=True,
        plugin_manager=paddle_plugin_manager(),
        ocr_engine="paddleocr",
        ocr_backend=options.ocr_backend,
        paddle_device=options.device,
        paddle_ocr_version=options.ocr_version,
        paddle_det_model_name=options.det_model_name,
        paddle_rec_model_name=options.rec_model_name,
        paddle_det_model_dir=options.det_model_dir,
        paddle_rec_model_dir=options.rec_model_dir,
        paddle_engine=options.engine,
        paddle_enable_hpi=options.enable_hpi,
        paddle_use_tensorrt=options.use_tensorrt,
        paddle_precision=options.precision,
        paddle_cpu_threads=options.cpu_threads,
        paddle_rec_batch_size=options.rec_batch_size,
        paddle_enable_orientation=options.enable_orientation,
        paddle_enable_unwarping=options.enable_unwarping,
        paddle_debug_jsonl=str(options.words_jsonl) if options.words_jsonl else None,
    )
    if options.words_jsonl:
        sort_page_records_jsonl(options.words_jsonl)
    return int(exit_code)
