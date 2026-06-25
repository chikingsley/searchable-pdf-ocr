from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast

from ocrmypdf_paddleocr.schema import BBox, OverlayBox, OverlayPage

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


def load_chandra_overlay_pages(results_json: Path, *, page_offset: int = 0) -> list[OverlayPage]:
    payload: Any = json.loads(results_json.read_text(encoding="utf-8"))
    if isinstance(payload, dict) is False:
        message = f"Expected Chandra results object in {results_json}"
        raise ValueError(message)
    payload_dict = cast("dict[str, Any]", payload)
    pages_obj = payload_dict.get("pages")
    if isinstance(pages_obj, list):
        return [
            chandra_overlay_page(cast("dict[str, Any]", page_payload), page_offset=page_offset)
            for page_payload in pages_obj
            if isinstance(page_payload, dict)
        ]
    return [chandra_overlay_page(payload_dict, page_offset=page_offset)]


def chandra_overlay_page(page_payload: dict[str, Any], *, page_offset: int) -> OverlayPage:
    page_number = chandra_page_number(page_payload, page_offset=page_offset)
    width, height = chandra_page_dimensions(page_payload)
    boxes = chandra_boxes(page_payload, page_number=page_number)
    return OverlayPage(page_number=page_number, width=width, height=height, boxes=boxes)


def chandra_page_number(raw_page: dict[str, Any], *, page_offset: int) -> int:
    page_number = raw_page.get("source_page_number")
    if page_number is None:
        page_index = raw_page.get("source_page_index")
    else:
        return int(str(page_number)) + page_offset
    if page_index is None:
        return 1 + page_offset
    return int(str(page_index)) + 1 + page_offset


def chandra_page_dimensions(raw_page: dict[str, Any]) -> tuple[float, float]:
    page_box = raw_page.get("page_box")
    if isinstance(page_box, list | tuple) and len(page_box) >= BBOX_COORDINATES:
        return float(str(page_box[2])), float(str(page_box[3]))
    return 1.0, 1.0


def chandra_boxes(raw_page: dict[str, Any], *, page_number: int) -> list[OverlayBox]:
    chunks_obj = raw_page.get("chunks")
    if isinstance(chunks_obj, list):
        chunks = chunks_obj
    else:
        return []
    boxes: list[OverlayBox] = []
    for index, chunk in enumerate(chunks, 1):
        if isinstance(chunk, dict):
            chunk_payload = cast("dict[str, Any]", chunk)
        else:
            continue
        if chunk_payload.get("bbox") is None:
            continue
        boxes.append(chandra_box(chunk_payload, box_index=index, page_number=page_number))
    return boxes


def chandra_box(item: dict[str, Any], *, box_index: int, page_number: int) -> OverlayBox:
    bbox = coerce_chandra_bbox(item["bbox"])
    return OverlayBox(
        id=f"p{page_number:04d}-chandra-{box_index:04d}",
        bbox=bbox,
        label=optional_string(item.get("label")),
        text=chandra_text(item.get("content")),
    )


def coerce_chandra_bbox(value: object) -> BBox:
    if isinstance(value, list | tuple) and len(value) >= BBOX_COORDINATES:
        return BBox(
            left=float(str(value[0])),
            top=float(str(value[1])),
            right=float(str(value[2])),
            bottom=float(str(value[3])),
        )
    message = "Chandra chunk is missing a usable bbox"
    raise ValueError(message)


def chandra_text(value: object) -> str | None:
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
