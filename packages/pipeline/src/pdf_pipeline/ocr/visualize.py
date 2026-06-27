from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import fitz

from pdf_pipeline.ocr.rebuild import load_page_records, word_text

if TYPE_CHECKING:
    from pdf_pipeline.ocr.schema import BBox, OverlayBox, OverlayPage, PageRecord, WordRecord

RGBColor = tuple[float, float, float]

LINE_COLOR: RGBColor = (0.0, 0.25, 1.0)
WORD_COLOR: RGBColor = (0.0, 0.65, 0.25)
OVERLAY_COLOR: RGBColor = (0.75, 0.25, 0.0)
LABEL_COLOR: RGBColor = (0.75, 0.0, 0.0)
POINTS_PER_INCH = 72


def parse_page_spec(spec: str | None) -> set[int] | None:
    if spec is None or spec.strip() == "":
        return None
    pages: set[int] = set()
    for raw_part in spec.split(","):
        part = raw_part.strip()
        if part == "":
            continue
        if "-" in part:
            start_raw, end_raw = part.split("-", 1)
            start = int(start_raw)
            end = int(end_raw)
            if start <= 0 or end < start:
                message = f"Invalid page range: {part}"
                raise ValueError(message)
            pages.update(range(start, end + 1))
            continue
        page = int(part)
        if page <= 0:
            message = f"Invalid page number: {part}"
            raise ValueError(message)
        pages.add(page)
    return pages


def scaled_rect(box: BBox, *, scale_x: float, scale_y: float) -> fitz.Rect:
    return fitz.Rect(box.left * scale_x, box.top * scale_y, box.right * scale_x, box.bottom * scale_y)


def label_text(word: WordRecord) -> str:
    text = " ".join(word_text(word).split())
    return text[:40]


def draw_word_label(page: fitz.Page, rect: fitz.Rect, word: WordRecord) -> None:
    text = label_text(word)
    if text == "":
        return
    fontsize = min(max(rect.height * 0.35, 3.0), 7.0)
    label_rect = fitz.Rect(rect.x0, max(rect.y0 - fontsize * 1.6, 0), rect.x1 + 80, rect.y0)
    page.insert_textbox(label_rect, text, fontsize=fontsize, color=LABEL_COLOR, overlay=True)


def overlay_label_text(box: OverlayBox) -> str:
    parts = [part for part in (box.label, box.text) if part]
    return " | ".join(parts)[:80]


def draw_overlay_label(page: fitz.Page, rect: fitz.Rect, box: OverlayBox) -> None:
    text = overlay_label_text(box)
    if text == "":
        return
    fontsize = min(max(rect.height * 0.22, 4.0), 8.0)
    label_rect = fitz.Rect(rect.x0, max(rect.y0 - fontsize * 1.6, 0), rect.x1 + 140, rect.y0)
    page.insert_textbox(label_rect, text, fontsize=fontsize, color=LABEL_COLOR, overlay=True)


def draw_record(
    *,
    page: fitz.Page,
    record: PageRecord,
    draw_lines: bool,
    draw_words: bool,
    labels: bool,
) -> tuple[int, int]:
    scale_x = page.rect.width / max(record.width, 1)
    scale_y = page.rect.height / max(record.height, 1)
    line_count = 0
    word_count = 0
    for line in record.lines:
        line_rect = scaled_rect(line.bbox, scale_x=scale_x, scale_y=scale_y)
        if draw_lines and line_rect.is_empty is False and line_rect.is_infinite is False:
            page.draw_rect(line_rect, color=LINE_COLOR, width=0.5, overlay=True)
            line_count += 1
        if draw_words is False:
            continue
        for word in line.words:
            word_rect = scaled_rect(word.bbox, scale_x=scale_x, scale_y=scale_y)
            if word_rect.is_empty or word_rect.is_infinite:
                continue
            page.draw_rect(word_rect, color=WORD_COLOR, width=0.35, overlay=True)
            if labels:
                draw_word_label(page, word_rect, word)
            word_count += 1
    return line_count, word_count


def draw_overlay_page(*, page: fitz.Page, record: OverlayPage, labels: bool) -> int:
    scale_x = page.rect.width / max(record.width, 1)
    scale_y = page.rect.height / max(record.height, 1)
    box_count = 0
    for box in record.boxes:
        rect = scaled_rect(box.bbox, scale_x=scale_x, scale_y=scale_y)
        if rect.is_empty or rect.is_infinite:
            continue
        page.draw_rect(rect, color=OVERLAY_COLOR, width=0.7, overlay=True)
        if labels:
            draw_overlay_label(page, rect, box)
        box_count += 1
    return box_count


def visualize_bboxes(
    *,
    input_pdf: Path,
    words_jsonl: Path,
    output_pdf: Path,
    pages: str | None = None,
    draw_lines: bool = True,
    draw_words: bool = True,
    labels: bool = False,
) -> tuple[int, int, int]:
    records = load_page_records(words_jsonl)
    if records == []:
        message = f"No page records found in {words_jsonl}"
        raise SystemExit(message)
    selected_pages = parse_page_spec(pages)
    by_page = {record.page_number: record for record in records}
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    page_count = 0
    line_count = 0
    word_count = 0
    with fitz.open(input_pdf) as document:
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            page_selected = True if selected_pages is None else page_number in selected_pages
            if page_selected is False:
                continue
            record = by_page.get(page_number)
            if record is None:
                continue
            page_count += 1
            drawn_lines, drawn_words = draw_record(
                page=page,
                record=record,
                draw_lines=draw_lines,
                draw_words=draw_words,
                labels=labels,
            )
            line_count += drawn_lines
            word_count += drawn_words
        document.save(output_pdf, garbage=4, deflate=True)
    return page_count, line_count, word_count


def visualize_overlay_pages(
    *,
    input_pdf: Path,
    overlay_pages: list[OverlayPage],
    output_pdf: Path,
    pages: str | None = None,
    labels: bool = False,
) -> tuple[int, int]:
    if overlay_pages == []:
        message = "No overlay pages found"
        raise SystemExit(message)
    selected_pages = parse_page_spec(pages)
    by_page = {record.page_number: record for record in overlay_pages}
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    page_count = 0
    box_count = 0
    with fitz.open(input_pdf) as document:
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            page_selected = True if selected_pages is None else page_number in selected_pages
            if page_selected is False:
                continue
            record = by_page.get(page_number)
            if record is None:
                continue
            page_count += 1
            box_count += draw_overlay_page(page=page, record=record, labels=labels)
        document.save(output_pdf, garbage=4, deflate=True)
    return page_count, box_count


def render_pdf_page_previews(
    pdf: Path,
    *,
    out_dir: Path,
    pages: tuple[int, ...],
    prefix: str,
    dpi: int = 144,
) -> list[Path]:
    if pages == ():
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    scale = dpi / POINTS_PER_INCH
    output_files: list[Path] = []
    with fitz.open(pdf) as document:
        for page_number in pages:
            if page_number < 1 or page_number > document.page_count:
                message = f"Page {page_number} is outside PDF page count {document.page_count}"
                raise ValueError(message)
            page = document[page_number - 1]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            output_file = out_dir / f"{prefix}-{page_number:04d}.png"
            pixmap.save(output_file)
            output_files.append(output_file)
    return output_files
