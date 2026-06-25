from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values
from mistralai.client import Mistral

MISTRAL_OCR_MODEL = "mistral-ocr-latest"
SIGNED_URL_EXPIRY_HOURS = 1
DEFAULT_MISTRAL_ENV_FILE = Path("/home/simon/github/pimsleur-hub/.env.local")


@dataclass(frozen=True)
class MistralOcrResult:
    output_dir: Path
    combined_file: Path
    page_count: int


def parse_pages(pages: str | None) -> list[int] | None:
    if pages is None or pages.strip() == "":
        return None
    selected: set[int] = set()
    for raw in pages.split(","):
        chunk = raw.strip()
        if chunk == "":
            continue
        if "-" in chunk:
            start_text, end_text = chunk.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start < 1 or end < start:
                message = f"Invalid page range: {chunk!r}"
                raise ValueError(message)
            selected.update(range(start - 1, end))
        else:
            value = int(chunk)
            if value < 1:
                message = f"Page numbers are 1-based: {chunk!r}"
                raise ValueError(message)
            selected.add(value - 1)
    return sorted(selected)


def mistral_client(api_key: str) -> Mistral:
    return Mistral(api_key=api_key)


def load_mistral_api_key(env_file: Path | None = None) -> str:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if api_key:
        return api_key
    candidate = env_file or DEFAULT_MISTRAL_ENV_FILE
    if candidate.is_file():
        value = dotenv_values(candidate).get("MISTRAL_API_KEY")
        if value:
            return value
    message = f"MISTRAL_API_KEY is required. Set it in the environment or in {candidate}."
    raise SystemExit(message)


def run_mistral_ocr(
    pdf: Path,
    output_root: Path,
    pages: str | None = None,
    env_file: Path | None = None,
) -> MistralOcrResult:
    api_key = load_mistral_api_key(env_file)
    if api_key is None or api_key.strip() == "":
        raise SystemExit("MISTRAL_API_KEY is required")
    if pdf.is_file() is False:
        message = f"Missing PDF: {pdf}"
        raise SystemExit(message)
    client = mistral_client(api_key)
    uploaded = client.files.upload(file={"file_name": pdf.name, "content": pdf.read_bytes()}, purpose="ocr")
    signed = client.files.get_signed_url(file_id=uploaded.id, expiry=SIGNED_URL_EXPIRY_HOURS)
    response = client.ocr.process(
        model=MISTRAL_OCR_MODEL,
        document={"type": "document_url", "document_url": signed.url},
        pages=parse_pages(pages),
        include_image_base64=False,
    )
    output_dir = output_root / pdf.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    for page in response.pages:
        human_page = int(page.index) + 1
        markdown = page.markdown or ""
        parts.append(f"<!-- page {human_page} -->\n\n{markdown}".rstrip())
    combined = output_dir / f"{pdf.stem}.mistral.md"
    combined.write_text("\n\n---\n\n".join(parts) + "\n", encoding="utf-8")
    return MistralOcrResult(output_dir=output_dir, combined_file=combined, page_count=len(response.pages))
