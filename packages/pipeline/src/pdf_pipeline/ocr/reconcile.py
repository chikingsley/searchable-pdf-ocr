from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from pdf_pipeline.ocr.constants import DEFAULT_RECONCILE_MODEL, DEFAULT_SUPERWHISPER_URL
from pdf_pipeline.ocr.rebuild import load_page_records
from pdf_pipeline.ocr.schema import PageRecord, ReconcileResponse

SYSTEM_PROMPT = """You correct OCR word text using sidecar document parses.

Rules:
- Keep every word_id and bbox unchanged.
- Only propose corrections for words where the OCR text is clearly wrong.
- Return JSON only with shape {"page_number": int, "corrections": [{"word_id": str, "text": str, "reason": str}]}.
- Preserve the source language/script and leave uncertain words absent from corrections.
"""


def extract_json(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                payload, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        message = "reconcile response must contain a JSON object"
        raise ValueError(message) from None
    if isinstance(payload, dict):
        return payload
    message = "reconcile response must be a JSON object"
    raise ValueError(message)


def page_prompt(record: PageRecord, sidecars: list[Path]) -> str:
    ocr_lines = []
    for line in record.lines:
        words = " ".join(f"{word.id}={word.text}" for word in line.words)
        ocr_lines.append(f"{line.id}: {words}")
    sidecar_parts = [f"## {sidecar.name}\n\n{sidecar.read_text(encoding='utf-8')[:20000]}" for sidecar in sidecars]
    return "\n\n".join(
        [
            f"Page: {record.page_number}",
            "OCR word stream:",
            "\n".join(ocr_lines),
            "Sidecar parses:",
            "\n\n---\n\n".join(sidecar_parts),
        ]
    )


def call_superwhisper(
    *,
    base_url: str,
    api_key: str,
    model: str,
    record: PageRecord,
    sidecars: list[Path],
    timeout: float,
) -> ReconcileResponse:
    headers = {"Authorization": f"Bearer {api_key}"}
    body = {
        "model": model,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": page_prompt(record, sidecars)}],
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout) as client:
        response = client.post("/v1/text/generate", json=body)
        response.raise_for_status()
    payload = response.json()
    text = str(payload.get("text", ""))
    return ReconcileResponse.model_validate(extract_json(text))


def changed_correction_map(record: PageRecord, reconcile: ReconcileResponse) -> dict[str, str]:
    original_text = {word.id: word.text for word in record.words}
    return {
        item.word_id: item.text
        for item in reconcile.corrections
        if item.word_id in original_text and item.text != original_text[item.word_id]
    }


def reconcile_words(
    *,
    words_jsonl: Path,
    sidecars: list[Path],
    output_jsonl: Path,
    base_url: str = DEFAULT_SUPERWHISPER_URL,
    model: str = DEFAULT_RECONCILE_MODEL,
    timeout: float = 600.0,
    api_key: str | None = None,
) -> tuple[int, int]:
    token = api_key or os.environ.get("SUPERWHISPER_API_KEY")
    if token is None or token.strip() == "":
        raise SystemExit("SUPERWHISPER_API_KEY is required")
    records = load_page_records(words_jsonl)
    corrections_total = 0
    corrected_records: list[PageRecord] = []
    for record in records:
        reconcile = call_superwhisper(
            base_url=base_url,
            api_key=token,
            model=model,
            record=record,
            sidecars=sidecars,
            timeout=timeout,
        )
        correction_map = changed_correction_map(record, reconcile)
        corrections_total += len(correction_map)
        corrected_lines = []
        for line in record.lines:
            corrected_words = [
                word.model_copy(update={"corrected_text": correction_map[word.id]})
                if word.id in correction_map
                else word
                for word in line.words
            ]
            corrected_lines.append(line.model_copy(update={"words": corrected_words}))
        corrected_records.append(record.model_copy(update={"lines": corrected_lines}))
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8") as handle:
        for record in corrected_records:
            handle.write(record.model_dump_json() + "\n")
    return len(corrected_records), corrections_total
