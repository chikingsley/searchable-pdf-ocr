from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal, cast

from pdf_pipeline.ocr.schema import BBox, OverlayBox, OverlayPage

SuryaBoxSource = Literal["auto", "ocr", "layout", "detect"]

HTML_SNIPPET_LIMIT = 80
BBOX_COORDINATES = 4


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


def load_surya_overlay_pages(
    results_json: Path,
    *,
    input_stem: str | None = None,
    document_key: str | None = None,
    box_source: SuryaBoxSource = "auto",
    page_base: int = 0,
    page_offset: int = 0,
) -> list[OverlayPage]:
    payload: Any = json.loads(results_json.read_text(encoding="utf-8"))
    if isinstance(payload, dict) is False:
        message = f"Expected Surya results object in {results_json}"
        raise ValueError(message)
    pages_payload = select_document_payload(
        cast("dict[str, Any]", payload), input_stem=input_stem, document_key=document_key
    )
    pages: list[OverlayPage] = []
    for fallback_index, raw_page in enumerate(pages_payload, 1):
        if isinstance(raw_page, dict) is False:
            continue
        page_payload = cast("dict[str, Any]", raw_page)
        page_number = surya_page_number(
            page_payload,
            fallback_index=fallback_index,
            page_base=page_base,
            page_offset=page_offset,
        )
        width, height = surya_page_dimensions(page_payload)
        boxes = surya_boxes(page_payload, source=box_source, page_number=page_number)
        pages.append(OverlayPage(page_number=page_number, width=width, height=height, boxes=boxes))
    return pages


def select_document_payload(payload: dict[str, Any], *, input_stem: str | None, document_key: str | None) -> list[Any]:
    if document_key:
        selected = payload.get(document_key)
        if isinstance(selected, list):
            return list(selected)
        message = f"Missing Surya document key {document_key!r}"
        raise ValueError(message)
    selected = payload.get(input_stem) if input_stem else None
    if isinstance(selected, list):
        return list(selected)
    list_values = [value for value in payload.values() if isinstance(value, list)]
    if len(list_values) == 1:
        return list(list_values[0])
    message = "Surya results contain multiple documents; pass --document-key"
    raise ValueError(message)


def surya_page_number(raw_page: dict[str, Any], *, fallback_index: int, page_base: int, page_offset: int) -> int:
    for key in ("page", "page_idx", "page_index", "page_number"):
        raw_value = raw_page.get(key)
        if raw_value is None:
            continue
        value = int(str(raw_value))
        return value - page_base + 1 + page_offset
    return fallback_index + page_offset


def surya_page_dimensions(raw_page: dict[str, Any]) -> tuple[float, float]:
    image_bbox = raw_page.get("image_bbox")
    if isinstance(image_bbox, list | tuple) and len(image_bbox) >= BBOX_COORDINATES:
        return float(str(image_bbox[2])), float(str(image_bbox[3]))
    return 1.0, 1.0


def surya_boxes(raw_page: dict[str, Any], *, source: SuryaBoxSource, page_number: int) -> list[OverlayBox]:
    blocks = raw_page.get("blocks")
    if source in ("auto", "ocr") and isinstance(blocks, list):
        return overlay_boxes_from_items(blocks, page_number=page_number, text_key="html")
    bboxes = raw_page.get("bboxes")
    if source in ("auto", "layout", "detect") and isinstance(bboxes, list):
        return overlay_boxes_from_items(bboxes, page_number=page_number, text_key=None)
    return []


def overlay_boxes_from_items(
    items: list[Any], *, page_number: int, text_key: Literal["html"] | None
) -> list[OverlayBox]:
    boxes: list[OverlayBox] = []
    for index, item in enumerate(items, 1):
        if isinstance(item, dict) is False or item.get("bbox") is None:
            continue
        boxes.append(
            surya_box(cast("dict[str, Any]", item), box_index=index, page_number=page_number, text_key=text_key)
        )
    return boxes


def surya_box(
    item: dict[str, Any], *, box_index: int, page_number: int, text_key: Literal["html"] | None
) -> OverlayBox:
    bbox = coerce_surya_bbox(item["bbox"])
    return OverlayBox(
        id=f"p{page_number:04d}-surya-{box_index:04d}",
        bbox=bbox,
        label=optional_string(item.get("label") or item.get("raw_label")),
        text=surya_text(item.get(text_key)) if text_key else None,
        confidence=optional_float(item.get("confidence")),
    )


def coerce_surya_bbox(value: object) -> BBox:
    if isinstance(value, list | tuple) and len(value) >= BBOX_COORDINATES:
        return BBox(
            left=float(str(value[0])),
            top=float(str(value[1])),
            right=float(str(value[2])),
            bottom=float(str(value[3])),
        )
    message = "Surya box is missing a usable bbox"
    raise ValueError(message)


def surya_text(value: object) -> str | None:
    if isinstance(value, str):
        html = value
    else:
        return None
    if html.strip() == "":
        return None
    parser = _TextExtractor()
    parser.feed(html)
    text = parser.text() or html
    return " ".join(text.split())[:HTML_SNIPPET_LIMIT]


def optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None
