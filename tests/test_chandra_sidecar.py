from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytest

from ocrmypdf_paddleocr import chandra_sidecar
from ocrmypdf_paddleocr.chandra_sidecar import (
    ChandraManagerLike,
    ChandraMethod,
    ChandraOcrOptions,
    ChandraOutputLike,
    ChandraRuntime,
    ImageLike,
    chandra_page_range,
    selected_page_indices,
)


@dataclass
class FakeImage:
    width: int = 200
    height: int = 100


@dataclass
class FakeOutput:
    markdown: str
    html: str
    chunks: object
    raw: str = "<layout />"
    page_box: list[int] | None = None
    token_count: int = 12
    error: bool = False


class FakeManager:
    def __init__(self, method: ChandraMethod, calls: list[dict[str, object]]) -> None:
        self.method = method
        self.calls = calls

    def generate(self, batch: list[object], **kwargs: object) -> list[ChandraOutputLike]:
        self.calls.append({"batch_size": len(batch), "kwargs": kwargs, "method": self.method})
        return [
            FakeOutput(
                markdown=f"page {index}",
                html=f"<p>page {index}</p>",
                page_box=[0, 0, 200, 100],
                chunks=[
                    {
                        "label": "Text",
                        "bbox": [10, 10, 190, 90],
                        "content": f"<p>page {index}</p>",
                    }
                ],
            )
            for index, _item in enumerate(batch, 1)
        ]


def make_pdf(path: Path, pages: int = 3) -> None:
    with fitz.open() as document:
        for _index in range(pages):
            document.new_page(width=200, height=100)
        document.save(path)


def test_chandra_page_range_serializes_zero_based_ranges() -> None:
    assert chandra_page_range([0, 1, 2, 6, 8, 9]) == "0-2,6,8-9"


def test_selected_page_indices_validates_pdf_page_count() -> None:
    assert selected_page_indices("1-2,3", page_count=3) == [0, 1, 2]


def test_run_chandra_ocr_writes_sidecar_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_pdf = tmp_path / "fixture.pdf"
    make_pdf(input_pdf)
    calls: list[dict[str, object]] = []
    load_configs: list[dict[str, object]] = []

    def fake_load_file(_filepath: str, config: dict[str, object]) -> list[ImageLike]:
        load_configs.append(config)
        return [FakeImage(), FakeImage()]

    def fake_create_manager(method: ChandraMethod) -> ChandraManagerLike:
        return FakeManager(method, calls)

    runtime = ChandraRuntime(
        load_file=fake_load_file,
        create_manager=fake_create_manager,
        create_batch_item=lambda image: {"image": image},
    )
    monkeypatch.setattr(chandra_sidecar, "load_chandra_runtime", lambda: runtime)

    result = chandra_sidecar.run_chandra_ocr(
        ChandraOcrOptions(
            input_pdf=input_pdf,
            out_dir=tmp_path / "runs",
            pages="1,3",
            batch_size=2,
            vllm_api_base="http://127.0.0.1:8000/v1",
        )
    )

    assert result.page_count == 2
    assert result.total_token_count == 24
    assert result.total_chunk_count == 2
    assert result.chunk_labels == (("Text", 2),)
    assert result.json_file.is_file()
    assert result.markdown_file.read_text(encoding="utf-8").count("<!-- page") == 2
    assert result.html_file.is_file()
    assert result.metadata_file.is_file()
    metadata = json.loads(result.metadata_file.read_text(encoding="utf-8"))
    assert metadata["total_token_count"] == 24
    assert metadata["total_chunk_count"] == 2
    assert metadata["chunk_labels"] == {"Text": 2}
    assert metadata["artifacts"]["json"].endswith("fixture.chandra.json")
    assert load_configs == [{"page_range": "0,2"}]
    assert calls[0]["method"] == "vllm"
    assert calls[0]["batch_size"] == 2
    kwargs = calls[0]["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs.get("vllm_api_base") == "http://127.0.0.1:8000/v1"


def test_run_chandra_ocr_can_render_review_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_pdf = tmp_path / "fixture.pdf"
    make_pdf(input_pdf)

    def fake_load_file(_filepath: str, _config: dict[str, object]) -> list[ImageLike]:
        return [FakeImage(), FakeImage()]

    def fake_create_manager(method: ChandraMethod) -> ChandraManagerLike:
        return FakeManager(method, [])

    runtime = ChandraRuntime(
        load_file=fake_load_file,
        create_manager=fake_create_manager,
        create_batch_item=lambda image: {"image": image},
    )
    monkeypatch.setattr(chandra_sidecar, "load_chandra_runtime", lambda: runtime)

    result = chandra_sidecar.run_chandra_ocr(
        ChandraOcrOptions(
            input_pdf=input_pdf,
            out_dir=tmp_path / "runs",
            pages="1,3",
            review_bboxes=True,
            preview_pages=(1, 3),
        )
    )

    assert result.bboxes_pdf is not None
    assert result.bboxes_pdf.is_file()
    assert result.review_page_count == 2
    assert result.review_box_count == 2
    assert len(result.preview_files) == 2
    assert all(path.is_file() for path in result.preview_files)
    metadata = json.loads(result.metadata_file.read_text(encoding="utf-8"))
    assert metadata["review"]["bboxes_pdf"].endswith("fixture.chandra.bboxes.pdf")
    assert metadata["review"]["box_count"] == 2
    assert len(metadata["review"]["preview_files"]) == 2
