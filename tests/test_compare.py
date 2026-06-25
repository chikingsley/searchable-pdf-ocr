from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ocrmypdf_paddleocr.workflows import compare as compare_workflow
from ocrmypdf_paddleocr.workflows.compare import CompareOptions

if TYPE_CHECKING:
    from ocrmypdf_paddleocr.workflows.searchable import SearchableOptions


def test_compare_backends_writes_manifest_and_artifact_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_pdf = tmp_path / "input.pdf"
    out_dir = tmp_path / "compare"
    input_pdf.write_bytes(b"%PDF-1.4\n")

    def fake_searchable(options: SearchableOptions) -> int:
        assert options.pages == "7"
        assert options.force_ocr is True
        assert options.words_jsonl is not None
        options.output_pdf.parent.mkdir(parents=True, exist_ok=True)
        options.output_pdf.write_text(f"{options.ocr_backend} pdf", encoding="utf-8")
        options.words_jsonl.write_text(
            (
                f'{{"source_image":"page.png","page_number":7,"width":200,"height":100,"dpi":300,'
                f'"plain_text":"{options.ocr_backend}","lines":[{{"id":"p0007-l0001",'
                f'"text":"{options.ocr_backend}","bbox":{{"left":1,"top":2,"right":3,"bottom":4}},'
                f'"words":[{{"id":"p0007-l0001-w0001","text":"{options.ocr_backend}",'
                f'"bbox":{{"left":1,"top":2,"right":3,"bottom":4}}}}]}}]}}\n'
            ),
            encoding="utf-8",
        )
        return 0

    def fake_visualize(
        *, input_pdf: Path, words_jsonl: Path, output_pdf: Path, pages: str | None = None
    ) -> tuple[int, int, int]:
        del input_pdf, words_jsonl
        assert pages == "7"
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        output_pdf.write_text("boxes", encoding="utf-8")
        return 1, 1, 1

    monkeypatch.setattr(compare_workflow, "run_searchable_pdf", fake_searchable)
    monkeypatch.setattr(compare_workflow, "visualize_bboxes", fake_visualize)

    result = compare_workflow.run_compare(
        CompareOptions(input_pdf=input_pdf, out_dir=out_dir, pages="7", force_ocr=True)
    )

    assert [backend.backend for backend in result.backends] == ["paddle", "rapidocr"]
    assert result.backends[0].words == 1
    assert result.backends[1].words == 1
    manifest = json.loads(result.manifest_file.read_text(encoding="utf-8"))
    assert manifest["backends"][0]["backend"] == "paddle"
    assert manifest["backends"][1]["backend"] == "rapidocr"
    assert manifest["backends"][0]["arabic_script_lines"] == 0
    assert manifest["backends"][0]["page_stats"][0]["page_number"] == 7
    assert manifest["backends"][0]["page_stats"][0]["words"] == 1
    assert (out_dir / "paddle" / "input.searchable.pdf").is_file()
    assert (out_dir / "rapidocr" / "input.words.jsonl").is_file()
    assert (out_dir / "review-bboxes" / "input.rapidocr.bboxes.pdf").is_file()
