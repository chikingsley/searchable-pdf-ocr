from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any

from ocrmypdf import BoundingBox, OcrClass, OcrElement

from pdf_pipeline.ocr.schema import BBox, LineRecord, PageRecord, WordRecord

Point = tuple[float, float]
FOUR_POINTS = 4
COORDINATE_MINIMUM = 2
RAPIDOCR_WORD_BOX_INDEX = 2
ARABIC_SCRIPT_RANGES = (
    ("\u0600", "\u06ff"),
    ("\u0750", "\u077f"),
    ("\u0870", "\u089f"),
    ("\u08a0", "\u08ff"),
    ("\ufb50", "\ufdff"),
    ("\ufe70", "\ufeff"),
)


def polygon_to_bbox(poly: object) -> BBox:
    points = coerce_points(poly)
    xs = [point[0] for point in points]
    if len(points) == FOUR_POINTS:
        top = (points[0][1] + points[1][1]) / 2
        bottom = (points[2][1] + points[3][1]) / 2
    else:
        ys = [point[1] for point in points]
        top = min(ys)
        bottom = max(ys)
    return BBox(left=min(xs), top=top, right=max(xs), bottom=bottom)


def union_bbox(boxes: list[BBox]) -> BBox:
    return BBox(
        left=min(box.left for box in boxes),
        top=min(box.top for box in boxes),
        right=max(box.right for box in boxes),
        bottom=max(box.bottom for box in boxes),
    )


def coerce_points(poly: object) -> list[Point]:
    tolist = getattr(poly, "tolist", None)
    value = tolist() if callable(tolist) else poly
    if isinstance(value, list | tuple):
        points = [
            (float(str(item[0])), float(str(item[1])))
            for item in value
            if isinstance(item, list | tuple) and len(item) >= COORDINATE_MINIMUM
        ]
        if points:
            return points
    message = "OCR engine returned an unusable polygon"
    raise ValueError(message)


def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def has_arabic_script(text: str) -> bool:
    return any(start <= char <= end for char in text for start, end in ARABIC_SCRIPT_RANGES)


def to_ocr_bbox(box: BBox) -> BoundingBox:
    return BoundingBox(left=box.left, top=box.top, right=box.right, bottom=box.bottom)


def page_record_to_element(record: PageRecord) -> OcrElement:
    line_elements: list[OcrElement] = []
    for line in record.lines:
        words = [
            OcrElement(
                ocr_class=OcrClass.WORD,
                bbox=to_ocr_bbox(word.bbox),
                text=word.corrected_text or word.text,
                confidence=word.confidence,
            )
            for word in line.words
        ]
        line_elements.append(
            OcrElement(
                ocr_class=OcrClass.LINE,
                bbox=to_ocr_bbox(line.bbox),
                text=line.text,
                confidence=line.confidence,
                children=words,
            )
        )
    return OcrElement(
        ocr_class=OcrClass.PAGE,
        bbox=BoundingBox(left=0, top=0, right=record.width, bottom=record.height),
        dpi=record.dpi,
        page_number=record.page_number,
        children=line_elements,
    )


def paddle_result_to_page_record(
    result: object,
    *,
    source_image: Path,
    page_number: int,
    width: int,
    height: int,
    dpi: float,
) -> PageRecord:
    to_dict = getattr(result, "to_dict", None)
    data = result if isinstance(result, dict) else to_dict() if callable(to_dict) else {}
    data = data if isinstance(data, dict) else {}
    texts = list_value(data.get("rec_texts"))
    scores = list_value(data.get("rec_scores"))
    polys = list_value(data.get("rec_polys") or data.get("rec_boxes"))
    word_tokens_by_line = list_value(data.get("text_word"))
    word_regions_by_line = list_value(data.get("text_word_region"))
    lines: list[LineRecord] = []
    for line_index, text in enumerate(texts):
        line_text = str(text).strip()
        if line_text == "":
            continue
        if line_index >= len(polys):
            continue
        line_bbox = polygon_to_bbox(polys[line_index])
        confidence = coerce_score(scores[line_index]) if line_index < len(scores) else None
        words = line_words(
            line_text=line_text,
            line_bbox=line_bbox,
            line_index=line_index,
            page_number=page_number,
            confidence=confidence,
            token_line=word_tokens_by_line[line_index] if line_index < len(word_tokens_by_line) else None,
            region_line=word_regions_by_line[line_index] if line_index < len(word_regions_by_line) else None,
        )
        lines.append(
            LineRecord(
                id=f"p{page_number:04d}-l{line_index + 1:04d}",
                text=line_text,
                bbox=line_bbox,
                confidence=confidence,
                words=words,
            )
        )
    return PageRecord(
        source_image=str(source_image),
        page_number=page_number,
        width=width,
        height=height,
        dpi=dpi,
        plain_text="\n".join(line.text for line in lines),
        lines=lines,
    )


def rapidocr_result_to_page_record(
    result: object,
    *,
    source_image: Path,
    page_number: int,
    width: int,
    height: int,
    dpi: float,
) -> PageRecord:
    records = rapidocr_records(result)
    word_results = list_value(getattr(result, "word_results", None))
    lines: list[LineRecord] = []
    for line_index, item in enumerate(records):
        if isinstance(item, dict) is False:
            continue
        line_text = str(item.get("txt") or item.get("text") or "").strip()
        if line_text == "":
            continue
        line_box = item.get("box") or item.get("bbox")
        if line_box is None:
            continue
        line_bbox = polygon_to_bbox(line_box)
        confidence = coerce_score(item.get("score"))
        words = rapidocr_words(word_results[line_index] if line_index < len(word_results) else None)
        token_line, region_line = rapidocr_word_parts(words)
        line_words_result = line_words(
            line_text=line_text,
            line_bbox=line_bbox,
            line_index=line_index,
            page_number=page_number,
            confidence=confidence,
            token_line=token_line,
            region_line=region_line,
        )
        lines.append(
            LineRecord(
                id=f"p{page_number:04d}-l{line_index + 1:04d}",
                text=line_text,
                bbox=line_bbox,
                confidence=confidence,
                words=line_words_result,
            )
        )
    return PageRecord(
        source_image=str(source_image),
        page_number=page_number,
        width=width,
        height=height,
        dpi=dpi,
        plain_text="\n".join(line.text for line in lines),
        lines=lines,
    )


def rapidocr_records(result: object) -> list[Any]:
    to_json = getattr(result, "to_json", None)
    records = to_json() if callable(to_json) else result
    if isinstance(records, str):
        payload = json.loads(records)
        return list_value(payload)
    return list_value(records)


def rapidocr_words(value: object) -> list[dict[str, object]]:
    words: list[dict[str, object]] = []
    for item in list_value(value):
        if isinstance(item, dict):
            text = str(item.get("txt") or item.get("text") or "").strip()
            box = item.get("box") or item.get("bbox")
        else:
            parts = list_value(item)
            text = str(parts[0]).strip() if len(parts) >= 1 else ""
            box = parts[RAPIDOCR_WORD_BOX_INDEX] if len(parts) > RAPIDOCR_WORD_BOX_INDEX else None
        if text and (box is None) is False:
            words.append({"text": text, "box": box})
    return words


def rapidocr_word_parts(words: list[dict[str, object]]) -> tuple[list[object], list[object]]:
    tokens: list[object] = []
    regions: list[object] = []
    for word in words:
        if tokens:
            tokens.append("")
            regions.append(word["box"])
        tokens.append(word["text"])
        regions.append(word["box"])
    return tokens, regions


def coerce_score(value: object) -> float | None:
    try:
        return float(str(value))
    except ValueError:
        return None


def line_words(
    *,
    line_text: str,
    line_bbox: BBox,
    line_index: int,
    page_number: int,
    confidence: float | None,
    token_line: object,
    region_line: object,
) -> list[WordRecord]:
    native = native_words(
        token_line=token_line,
        region_line=region_line,
        line_index=line_index,
        page_number=page_number,
        confidence=confidence,
    )
    if native:
        if has_arabic_script(line_text):
            return rtl_words_from_line_text(
                line_text=line_text,
                line_bbox=line_bbox,
                native=native,
                line_index=line_index,
                page_number=page_number,
                confidence=confidence,
            )
        return native
    return estimated_words(
        line_text=line_text,
        line_bbox=line_bbox,
        line_index=line_index,
        page_number=page_number,
        confidence=confidence,
    )


def word_id(*, page_number: int, line_index: int, word_index: int) -> str:
    return f"p{page_number:04d}-l{line_index + 1:04d}-w{word_index:04d}"


def rtl_words_from_line_text(
    *,
    line_text: str,
    line_bbox: BBox,
    native: list[WordRecord],
    line_index: int,
    page_number: int,
    confidence: float | None,
) -> list[WordRecord]:
    tokens = line_text.split()
    if tokens == []:
        return native
    if len(native) == 1:
        return [
            WordRecord(
                id=word_id(page_number=page_number, line_index=line_index, word_index=1),
                text=line_text,
                bbox=native[0].bbox,
                confidence=confidence,
            )
        ]
    if len(tokens) == len(native):
        right_to_left_boxes = sorted((word.bbox for word in native), key=lambda box: box.right, reverse=True)
        return [
            WordRecord(
                id=word_id(page_number=page_number, line_index=line_index, word_index=word_index),
                text=token,
                bbox=right_to_left_boxes[word_index - 1],
                confidence=confidence,
            )
            for word_index, token in enumerate(tokens, 1)
        ]
    return [
        WordRecord(
            id=word_id(page_number=page_number, line_index=line_index, word_index=1),
            text=line_text,
            bbox=line_bbox,
            confidence=confidence,
        )
    ]


def native_words(
    *,
    token_line: object,
    region_line: object,
    line_index: int,
    page_number: int,
    confidence: float | None,
) -> list[WordRecord]:
    tokens = list_value(token_line)
    regions = list_value(region_line)
    if tokens == [] or regions == []:
        return []
    merged: list[tuple[str, list[BBox]]] = []
    current_tokens: list[str] = []
    current_boxes: list[BBox] = []
    for token, region in zip(tokens, regions, strict=False):
        token_text = str(token).strip()
        if token_text == "":
            if current_tokens:
                merged.append(("".join(current_tokens), current_boxes))
            current_tokens = []
            current_boxes = []
            continue
        current_tokens.append(token_text)
        current_boxes.append(polygon_to_bbox(region))
    if current_tokens:
        merged.append(("".join(current_tokens), current_boxes))
    words: list[WordRecord] = []
    for word_index, (word, boxes) in enumerate(merged, 1):
        if boxes:
            words.append(
                WordRecord(
                    id=word_id(page_number=page_number, line_index=line_index, word_index=word_index),
                    text=word,
                    bbox=union_bbox(boxes),
                    confidence=confidence,
                )
            )
    return words


def estimated_words(
    *,
    line_text: str,
    line_bbox: BBox,
    line_index: int,
    page_number: int,
    confidence: float | None,
) -> list[WordRecord]:
    tokens = line_text.split()
    if tokens == []:
        return []
    total_chars = sum(len(token) for token in tokens)
    space_count = max(len(tokens) - 1, 0)
    space_width = line_bbox.width * space_count / max(total_chars + space_count, 1)
    word_area_width = line_bbox.width - space_width * space_count
    cursor = line_bbox.left
    words: list[WordRecord] = []
    for word_index, token in enumerate(tokens, 1):
        word_width = word_area_width * len(token) / total_chars if total_chars > 0 else line_bbox.width / len(tokens)
        right = line_bbox.right if word_index == len(tokens) else cursor + word_width
        words.append(
            WordRecord(
                id=word_id(page_number=page_number, line_index=line_index, word_index=word_index),
                text=token,
                bbox=BBox(left=cursor, top=line_bbox.top, right=right, bottom=line_bbox.bottom),
                confidence=confidence,
            )
        )
        cursor = right + space_width
    return words


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def list_value(value: object) -> list[Any]:
    if isinstance(value, list | tuple):
        return list(value)
    return []
