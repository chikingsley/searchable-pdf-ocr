from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Literal, Protocol, cast

import fitz

from ocrmypdf_paddleocr.adapters.chandra import load_chandra_overlay_pages
from ocrmypdf_paddleocr.mistral_sidecar import parse_pages
from ocrmypdf_paddleocr.visualize import render_pdf_page_previews, visualize_overlay_pages

ChandraMethod = Literal["vllm", "hf"]
DEFAULT_CHANDRA_PROMPT_TYPE = "ocr_layout"


class ImageLike(Protocol):
    width: int
    height: int


class ChandraOutputLike(Protocol):
    markdown: str
    html: str
    chunks: object
    raw: str
    page_box: list[int] | None
    token_count: int
    error: bool


class ChandraManagerLike(Protocol):
    def generate(self, batch: list[object], **kwargs: object) -> list[ChandraOutputLike]: ...


@dataclass(frozen=True, slots=True)
class ChandraRuntime:
    load_file: Callable[[str, dict[str, object]], list[ImageLike]]
    create_manager: Callable[[ChandraMethod], ChandraManagerLike]
    create_batch_item: Callable[[ImageLike], object]


@dataclass(frozen=True, slots=True, kw_only=True)
class ChandraOcrOptions:
    input_pdf: Path
    out_dir: Path
    pages: str | None = None
    method: ChandraMethod = "vllm"
    vllm_api_base: str | None = None
    max_output_tokens: int | None = 2048
    batch_size: int = 1
    max_workers: int | None = None
    max_retries: int | None = None
    max_failure_retries: int | None = None
    temperature: float = 0.0
    top_p: float = 0.1
    include_images: bool = False
    include_headers_footers: bool = False
    review_bboxes: bool = False
    review_pdf: Path | None = None
    review_pages: str | None = None
    review_labels: bool = False
    preview_pages: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ChandraReviewResult:
    bboxes_pdf: Path | None
    page_count: int = 0
    box_count: int = 0
    preview_files: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class ChandraOcrResult:
    output_dir: Path
    json_file: Path
    markdown_file: Path
    html_file: Path
    metadata_file: Path
    page_count: int
    total_token_count: int
    total_chunk_count: int
    chunk_labels: tuple[tuple[str, int], ...]
    bboxes_pdf: Path | None = None
    review_page_count: int = 0
    review_box_count: int = 0
    preview_files: tuple[Path, ...] = ()


def load_chandra_runtime() -> ChandraRuntime:
    try:
        load_file = cast(
            "Callable[[str, dict[str, object]], list[ImageLike]]", import_module("chandra.input").load_file
        )
        inference_manager = cast("Callable[..., ChandraManagerLike]", import_module("chandra.model").InferenceManager)
        batch_input_item = cast("Callable[..., object]", import_module("chandra.model.schema").BatchInputItem)
    except ImportError as exc:
        message = (
            "chandra-ocr is required. Run with: uv run --with chandra-ocr==0.2.0 paddle-searchable-pdf chandra-ocr ..."
        )
        raise SystemExit(message) from exc
    return ChandraRuntime(
        load_file=load_file,
        create_manager=lambda method: inference_manager(method=method),
        create_batch_item=lambda image: batch_input_item(image=image, prompt_type=DEFAULT_CHANDRA_PROMPT_TYPE),
    )


def selected_page_indices(pages: str | None, *, page_count: int) -> list[int]:
    selected = parse_pages(pages)
    if selected is None:
        return list(range(page_count))
    invalid = [page_index + 1 for page_index in selected if page_index >= page_count]
    if invalid:
        message = f"Page selection exceeds PDF page count {page_count}: {invalid}"
        raise ValueError(message)
    return selected


def chandra_page_range(page_indices: Sequence[int]) -> str:
    if len(page_indices) == 0:
        return ""
    ranges: list[str] = []
    start = page_indices[0]
    previous = start
    for page_index in page_indices[1:]:
        if page_index == previous + 1:
            previous = page_index
            continue
        ranges.append(page_range_part(start, previous))
        start = page_index
        previous = page_index
    ranges.append(page_range_part(start, previous))
    return ",".join(ranges)


def page_range_part(start: int, end: int) -> str:
    if start == end:
        return str(start)
    return f"{start}-{end}"


def pdf_page_count(pdf: Path) -> int:
    with fitz.open(pdf) as document:
        return int(document.page_count)


def run_chandra_ocr(options: ChandraOcrOptions) -> ChandraOcrResult:
    input_pdf = options.input_pdf.expanduser().resolve()
    if input_pdf.is_file() is False:
        message = f"Missing PDF: {input_pdf}"
        raise SystemExit(message)
    if options.batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    page_count = pdf_page_count(input_pdf)
    page_indices = selected_page_indices(options.pages, page_count=page_count)
    runtime = load_chandra_runtime()
    images = runtime.load_file(os.fspath(input_pdf), {"page_range": chandra_page_range(page_indices)})
    if len(images) != len(page_indices):
        message = f"Chandra returned {len(images)} pages for {len(page_indices)} selected pages"
        raise RuntimeError(message)
    manager = runtime.create_manager(options.method)
    output_dir = options.out_dir.expanduser() / input_pdf.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for batch_start in range(0, len(images), options.batch_size):
        batch_images = images[batch_start : batch_start + options.batch_size]
        batch_page_indices = page_indices[batch_start : batch_start + options.batch_size]
        batch_items = [runtime.create_batch_item(image) for image in batch_images]
        batch_outputs = manager.generate(batch_items, **generation_kwargs(options))
        for image, page_index, output in zip(batch_images, batch_page_indices, batch_outputs, strict=True):
            records.append(chandra_record(output, image=image, input_pdf=input_pdf, page_index=page_index))
    json_file = output_dir / f"{input_pdf.stem}.chandra.json"
    markdown_file = output_dir / f"{input_pdf.stem}.chandra.md"
    html_file = output_dir / f"{input_pdf.stem}.chandra.html"
    metadata_file = output_dir / f"{input_pdf.stem}.chandra_metadata.json"
    payload = {
        "source_pdf": os.fspath(input_pdf),
        "pages": records,
    }
    json_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_file.write_text(combined_markdown(records), encoding="utf-8")
    html_file.write_text(combined_html(records), encoding="utf-8")
    review = render_chandra_review(options, input_pdf=input_pdf, json_file=json_file, output_dir=output_dir)
    label_counts = chunk_label_counts(records)
    metadata_file.write_text(
        json.dumps(
            metadata(
                options,
                input_pdf=input_pdf,
                records=records,
                json_file=json_file,
                markdown_file=markdown_file,
                html_file=html_file,
                metadata_file=metadata_file,
                review=review,
                label_counts=label_counts,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return ChandraOcrResult(
        output_dir=output_dir,
        json_file=json_file,
        markdown_file=markdown_file,
        html_file=html_file,
        metadata_file=metadata_file,
        page_count=len(records),
        total_token_count=total_token_count(records),
        total_chunk_count=total_chunk_count(records),
        chunk_labels=tuple(label_counts.items()),
        bboxes_pdf=review.bboxes_pdf,
        review_page_count=review.page_count,
        review_box_count=review.box_count,
        preview_files=review.preview_files,
    )


def generation_kwargs(options: ChandraOcrOptions) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "include_images": options.include_images,
        "include_headers_footers": options.include_headers_footers,
        "temperature": options.temperature,
        "top_p": options.top_p,
    }
    optional_values = {
        "max_output_tokens": options.max_output_tokens,
        "max_workers": options.max_workers,
        "max_retries": options.max_retries,
        "max_failure_retries": options.max_failure_retries,
        "vllm_api_base": options.vllm_api_base,
    }
    for key, value in optional_values.items():
        if value is None:
            continue
        kwargs[key] = value
    return kwargs


def chandra_record(
    output: ChandraOutputLike, *, image: ImageLike, input_pdf: Path, page_index: int
) -> dict[str, object]:
    page_box = output.page_box
    if page_box is None:
        page_box = [0, 0, image.width, image.height]
    return {
        "source_pdf": os.fspath(input_pdf),
        "source_page_index": page_index,
        "source_page_number": page_index + 1,
        "page_box": list(page_box),
        "token_count": int(output.token_count),
        "error": bool(output.error),
        "raw": str(output.raw),
        "markdown": str(output.markdown),
        "html": str(output.html),
        "chunks": output.chunks,
    }


def combined_markdown(records: Sequence[dict[str, object]]) -> str:
    parts = [f"<!-- page {record['source_page_number']} -->\n\n{record['markdown']}".rstrip() for record in records]
    return "\n\n---\n\n".join(parts) + "\n"


def combined_html(records: Sequence[dict[str, object]]) -> str:
    parts = [f"<!-- page {record['source_page_number']} -->\n{record['html']}".rstrip() for record in records]
    return "\n\n<hr />\n\n".join(parts) + "\n"


def metadata(
    options: ChandraOcrOptions,
    *,
    input_pdf: Path,
    records: Sequence[dict[str, object]],
    json_file: Path,
    markdown_file: Path,
    html_file: Path,
    metadata_file: Path,
    review: ChandraReviewResult,
    label_counts: dict[str, int],
) -> dict[str, object]:
    return {
        "source_pdf": os.fspath(input_pdf),
        "method": options.method,
        "pages": [record["source_page_number"] for record in records],
        "page_count": len(records),
        "total_token_count": total_token_count(records),
        "total_chunk_count": total_chunk_count(records),
        "chunk_labels": label_counts,
        "max_output_tokens": options.max_output_tokens,
        "batch_size": options.batch_size,
        "max_workers": options.max_workers,
        "max_retries": options.max_retries,
        "max_failure_retries": options.max_failure_retries,
        "temperature": options.temperature,
        "top_p": options.top_p,
        "include_images": options.include_images,
        "include_headers_footers": options.include_headers_footers,
        "artifacts": {
            "json": os.fspath(json_file),
            "markdown": os.fspath(markdown_file),
            "html": os.fspath(html_file),
            "metadata": os.fspath(metadata_file),
        },
        "review": review_metadata(review),
    }


def total_token_count(records: Sequence[dict[str, object]]) -> int:
    return sum(record_token_count(record) for record in records)


def record_token_count(record: dict[str, object]) -> int:
    value = record.get("token_count", 0)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        return int(value)
    return 0


def total_chunk_count(records: Sequence[dict[str, object]]) -> int:
    return sum(len(record_chunks(record)) for record in records)


def chunk_label_counts(records: Sequence[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        for chunk in record_chunks(record):
            label = chunk_label(chunk)
            counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def record_chunks(record: dict[str, object]) -> list[dict[str, object]]:
    chunks = record.get("chunks")
    if isinstance(chunks, list):
        return [cast("dict[str, object]", chunk) for chunk in chunks if isinstance(chunk, dict)]
    return []


def chunk_label(chunk: dict[str, object]) -> str:
    label = chunk.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return "Unknown"


def review_metadata(review: ChandraReviewResult) -> dict[str, object]:
    return {
        "bboxes_pdf": os.fspath(review.bboxes_pdf) if review.bboxes_pdf else None,
        "page_count": review.page_count,
        "box_count": review.box_count,
        "preview_files": [os.fspath(path) for path in review.preview_files],
    }


def render_chandra_review(
    options: ChandraOcrOptions, *, input_pdf: Path, json_file: Path, output_dir: Path
) -> ChandraReviewResult:
    if options.review_bboxes is False and options.review_pdf is None and options.preview_pages == ():
        return ChandraReviewResult(bboxes_pdf=None)
    output_pdf = options.review_pdf.expanduser() if options.review_pdf else default_review_pdf(input_pdf, output_dir)
    overlay_pages = load_chandra_overlay_pages(json_file)
    review_pages = options.pages
    if options.review_pages:
        review_pages = options.review_pages
    page_count, box_count = visualize_overlay_pages(
        input_pdf=input_pdf,
        overlay_pages=overlay_pages,
        output_pdf=output_pdf,
        pages=review_pages,
        labels=options.review_labels,
    )
    preview_files = render_pdf_page_previews(
        output_pdf,
        out_dir=output_pdf.parent / "previews",
        pages=options.preview_pages,
        prefix=output_pdf.stem,
    )
    return ChandraReviewResult(
        bboxes_pdf=output_pdf,
        page_count=page_count,
        box_count=box_count,
        preview_files=tuple(preview_files),
    )


def default_review_pdf(input_pdf: Path, output_dir: Path) -> Path:
    return output_dir / "review-bboxes" / f"{input_pdf.stem}.chandra.bboxes.pdf"
