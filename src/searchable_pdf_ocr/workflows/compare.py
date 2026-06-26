from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from searchable_pdf_ocr.convert import has_arabic_script
from searchable_pdf_ocr.rebuild import load_page_records
from searchable_pdf_ocr.visualize import render_pdf_page_previews, visualize_bboxes
from searchable_pdf_ocr.workflows.searchable import (
    EngineName,
    OcrBackendName,
    PrecisionName,
    SearchableOptions,
    run_searchable_pdf,
)

if TYPE_CHECKING:
    from searchable_pdf_ocr.schema import PageRecord


@dataclass(frozen=True, slots=True, kw_only=True)
class CompareOptions:
    input_pdf: Path
    out_dir: Path
    backends: tuple[OcrBackendName, ...] = ("paddle", "rapidocr")
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
    optimize: int = 1
    output_type: str = "pdf"
    preview_pages: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class BackendCompareResult:
    backend: OcrBackendName
    searchable_pdf: Path
    words_jsonl: Path
    bboxes_pdf: Path
    exit_code: int
    elapsed_seconds: float
    pages: int
    lines: int
    words: int
    arabic_script_lines: int
    arabic_script_words: int
    page_stats: tuple[dict[str, int], ...]
    preview_files: tuple[Path, ...]

    def manifest(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "searchable_pdf": os.fspath(self.searchable_pdf),
            "words_jsonl": os.fspath(self.words_jsonl),
            "bboxes_pdf": os.fspath(self.bboxes_pdf),
            "exit_code": self.exit_code,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "pages": self.pages,
            "lines": self.lines,
            "words": self.words,
            "arabic_script_lines": self.arabic_script_lines,
            "arabic_script_words": self.arabic_script_words,
            "page_stats": list(self.page_stats),
            "preview_files": [os.fspath(path) for path in self.preview_files],
        }


@dataclass(frozen=True, slots=True)
class CompareResult:
    input_pdf: Path
    out_dir: Path
    manifest_file: Path
    backends: tuple[BackendCompareResult, ...]

    def manifest(self) -> dict[str, object]:
        return {
            "input_pdf": os.fspath(self.input_pdf),
            "out_dir": os.fspath(self.out_dir),
            "backends": [backend.manifest() for backend in self.backends],
            "manifest": os.fspath(self.manifest_file),
        }


def run_compare(options: CompareOptions) -> CompareResult:
    input_pdf = options.input_pdf.expanduser().resolve()
    out_dir = options.out_dir.expanduser().resolve()
    stem = input_pdf.stem
    results: list[BackendCompareResult] = []
    for backend in options.backends:
        backend_dir = out_dir / backend
        searchable_pdf = backend_dir / f"{stem}.searchable.pdf"
        words_jsonl = backend_dir / f"{stem}.words.jsonl"
        bboxes_pdf = out_dir / "review-bboxes" / f"{stem}.{backend}.bboxes.pdf"
        start = time.perf_counter()
        exit_code = run_searchable_pdf(
            SearchableOptions(
                input_pdf=input_pdf,
                output_pdf=searchable_pdf,
                ocr_backend=backend,
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
        elapsed_seconds = time.perf_counter() - start
        records = load_page_records(words_jsonl)
        page_count = len(records)
        line_count = sum(len(record.lines) for record in records)
        word_count = sum(len(record.words) for record in records)
        page_stats = tuple(page_stat(record) for record in records)
        arabic_script_line_count = sum(stat["arabic_script_lines"] for stat in page_stats)
        arabic_script_word_count = sum(stat["arabic_script_words"] for stat in page_stats)
        visualize_bboxes(input_pdf=input_pdf, words_jsonl=words_jsonl, output_pdf=bboxes_pdf, pages=options.pages)
        preview_files = render_pdf_page_previews(
            bboxes_pdf,
            out_dir=out_dir / "review-bboxes" / "previews",
            pages=options.preview_pages,
            prefix=f"{stem}.{backend}.bboxes",
        )
        results.append(
            BackendCompareResult(
                backend=backend,
                searchable_pdf=searchable_pdf,
                words_jsonl=words_jsonl,
                bboxes_pdf=bboxes_pdf,
                exit_code=exit_code,
                elapsed_seconds=elapsed_seconds,
                pages=page_count,
                lines=line_count,
                words=word_count,
                arabic_script_lines=arabic_script_line_count,
                arabic_script_words=arabic_script_word_count,
                page_stats=page_stats,
                preview_files=tuple(preview_files),
            )
        )
    manifest_file = out_dir / f"{stem}.compare.json"
    result = CompareResult(input_pdf=input_pdf, out_dir=out_dir, manifest_file=manifest_file, backends=tuple(results))
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(result.manifest(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def page_stat(record: PageRecord) -> dict[str, int]:
    return {
        "page_number": record.page_number,
        "lines": len(record.lines),
        "words": len(record.words),
        "arabic_script_lines": sum(1 for line in record.lines if has_arabic_script(line.text)),
        "arabic_script_words": sum(1 for word in record.words if has_arabic_script(word.text)),
    }
