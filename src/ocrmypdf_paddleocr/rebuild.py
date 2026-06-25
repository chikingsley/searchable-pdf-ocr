from __future__ import annotations

import json
import os
from pathlib import Path

import fitz

from ocrmypdf_paddleocr.schema import PageRecord, WordRecord

DEFAULT_FONT_CANDIDATES = (
    Path.home() / ".local/share/fonts/NotoNaskhArabic.ttf",
    Path.home() / ".local/share/fonts/NotoSansArabic.ttf",
    Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
)
OCR_FONT_NAME = "ocrfont"


def load_page_records(path: Path) -> list[PageRecord]:
    records: list[PageRecord] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip() == "":
                continue
            payload = json.loads(line)
            if isinstance(payload, dict) and {"page_number", "lines", "width", "height"}.issubset(payload):
                records.append(PageRecord.model_validate(payload))
    return sorted(records, key=lambda record: record.page_number)


def sort_page_records_jsonl(path: Path) -> int:
    records = load_page_records(path)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json() + "\n")
    return len(records)


def word_text(word: WordRecord) -> str:
    return word.corrected_text or word.text


def font_size(word: WordRecord, scale_y: float) -> float:
    height = max(word.bbox.height * scale_y, 1.0)
    return min(max(height * 0.78, 1.0), 14.0)


def default_font_file() -> Path | None:
    env_font = os.environ.get("OCR_PDF_FONT_FILE")
    if env_font:
        path = Path(env_font).expanduser()
        if path.is_file():
            return path
    for path in DEFAULT_FONT_CANDIDATES:
        if path.is_file():
            return path
    return None


def rebuild_pdf(input_pdf: Path, words_jsonl: Path, output_pdf: Path, font_file: Path | None = None) -> tuple[int, int]:
    records = load_page_records(words_jsonl)
    if records == []:
        message = f"No page records found in {words_jsonl}"
        raise SystemExit(message)
    by_page = {record.page_number: record for record in records}
    resolved_font_file = font_file.expanduser().resolve() if font_file else default_font_file()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    boxes = 0
    pages = 0
    with fitz.open(input_pdf) as document:
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            record = by_page.get(page_number)
            if record is None:
                continue
            pages += 1
            scale_x = page.rect.width / max(record.width, 1)
            scale_y = page.rect.height / max(record.height, 1)
            if resolved_font_file:
                page.insert_font(fontname=OCR_FONT_NAME, fontfile=os.fspath(resolved_font_file))
            for word in record.words:
                text = word_text(word)
                if text.strip() == "":
                    continue
                rect = fitz.Rect(
                    word.bbox.left * scale_x,
                    word.bbox.top * scale_y,
                    word.bbox.right * scale_x,
                    word.bbox.bottom * scale_y,
                )
                if rect.is_empty or rect.is_infinite:
                    continue
                page.insert_text(
                    (rect.x0, rect.y1),
                    text,
                    fontsize=font_size(word, scale_y),
                    fontname=OCR_FONT_NAME if resolved_font_file else "helv",
                    render_mode=3,
                    overlay=True,
                    fill_opacity=0,
                    stroke_opacity=0,
                )
                boxes += 1
        document.save(output_pdf, garbage=4, deflate=True)
    return pages, boxes
