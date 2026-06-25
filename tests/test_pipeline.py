from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ocrmypdf_paddleocr.chandra_sidecar import ChandraOcrOptions, ChandraOcrResult
from ocrmypdf_paddleocr.mistral_sidecar import MistralOcrResult
from ocrmypdf_paddleocr.workflows import pipeline as pipeline_workflow
from ocrmypdf_paddleocr.workflows.pipeline import PipelineOptions

if TYPE_CHECKING:
    from ocrmypdf_paddleocr.workflows.searchable import SearchableOptions


def test_pipeline_auto_reconciles_and_rebuilds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_pdf = tmp_path / "input.pdf"
    input_pdf.write_bytes(b"%PDF-1.4\n")
    out_dir = tmp_path / "out"
    monkeypatch.setenv("SUPERWHISPER_API_KEY", "test-token")

    def fake_searchable(options: SearchableOptions) -> int:
        assert options.ocr_backend == "paddle"
        assert options.pages == "1-2"
        options.output_pdf.parent.mkdir(parents=True, exist_ok=True)
        options.output_pdf.write_text("searchable", encoding="utf-8")
        assert options.words_jsonl is not None
        options.words_jsonl.write_text("{}", encoding="utf-8")
        return 0

    def fake_mistral(
        pdf: Path,
        output_root: Path,
        pages: str | None = None,
        env_file: Path | None = None,
    ) -> MistralOcrResult:
        assert pdf == input_pdf.resolve()
        assert pages == "1-2"
        assert env_file is None
        sidecar_dir = output_root / pdf.stem
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        combined = sidecar_dir / f"{pdf.stem}.mistral.md"
        combined.write_text("sidecar", encoding="utf-8")
        return MistralOcrResult(output_dir=sidecar_dir, combined_file=combined, page_count=2)

    def fake_reconcile(
        *,
        words_jsonl: Path,
        sidecars: list[Path],
        output_jsonl: Path,
        base_url: str,
        model: str,
        timeout: float,
        api_key: str | None = None,
    ) -> tuple[int, int]:
        assert words_jsonl == out_dir.resolve() / "searchable" / "input.words.jsonl"
        assert len(sidecars) == 1
        assert base_url == "http://127.0.0.1:8787"
        assert model == "claude-sonnet-4-6"
        assert timeout == 600.0
        assert api_key == "test-token"
        output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        output_jsonl.write_text("corrected", encoding="utf-8")
        return 2, 5

    def fake_rebuild(
        input_path: Path, words_jsonl: Path, output_pdf: Path, font_file: Path | None = None
    ) -> tuple[int, int]:
        assert input_path == input_pdf.resolve()
        assert words_jsonl == out_dir.resolve() / "reconcile" / "input.corrected.words.jsonl"
        assert font_file is None
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        output_pdf.write_text("rebuilt", encoding="utf-8")
        return 2, 20

    monkeypatch.setattr(pipeline_workflow, "run_searchable_pdf", fake_searchable)
    monkeypatch.setattr(pipeline_workflow, "run_mistral_ocr", fake_mistral)
    monkeypatch.setattr(pipeline_workflow, "reconcile_words", fake_reconcile)
    monkeypatch.setattr(pipeline_workflow, "rebuild_pdf", fake_rebuild)

    result = pipeline_workflow.run_pipeline(PipelineOptions(input_pdf=input_pdf, out_dir=out_dir, pages="1-2"))

    assert result.reconcile_status == "done"
    assert result.corrected_words_jsonl == out_dir.resolve() / "reconcile" / "input.corrected.words.jsonl"
    assert result.corrected_searchable_pdf == out_dir.resolve() / "rebuild" / "input.corrected.searchable.pdf"
    assert result.final_pdf == out_dir.resolve() / "final" / "input-OCR.pdf"
    assert result.final_pdf.read_text(encoding="utf-8") == "rebuilt"
    manifest = json.loads(result.manifest_file.read_text(encoding="utf-8"))
    assert manifest["steps"]["reconcile"]["corrections"] == 5
    assert manifest["steps"]["rebuild"]["boxes"] == 20
    assert manifest["steps"]["final"]["pdf"] == str(out_dir.resolve() / "final" / "input-OCR.pdf")


def test_pipeline_auto_skips_reconcile_without_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_pdf = tmp_path / "input.pdf"
    input_pdf.write_bytes(b"%PDF-1.4\n")
    out_dir = tmp_path / "out"
    monkeypatch.delenv("SUPERWHISPER_API_KEY", raising=False)

    def fake_searchable(options: SearchableOptions) -> int:
        options.output_pdf.parent.mkdir(parents=True, exist_ok=True)
        options.output_pdf.write_text("searchable", encoding="utf-8")
        assert options.words_jsonl is not None
        options.words_jsonl.write_text("{}", encoding="utf-8")
        return 0

    def fake_mistral(
        pdf: Path,
        output_root: Path,
        pages: str | None = None,
        env_file: Path | None = None,
    ) -> MistralOcrResult:
        assert pages is None
        assert env_file is None
        sidecar_dir = output_root / pdf.stem
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        combined = sidecar_dir / f"{pdf.stem}.mistral.md"
        combined.write_text("sidecar", encoding="utf-8")
        return MistralOcrResult(output_dir=sidecar_dir, combined_file=combined, page_count=1)

    def fail_reconcile(**_kwargs: object) -> tuple[int, int]:
        raise AssertionError("reconcile should be skipped")

    monkeypatch.setattr(pipeline_workflow, "run_searchable_pdf", fake_searchable)
    monkeypatch.setattr(pipeline_workflow, "run_mistral_ocr", fake_mistral)
    monkeypatch.setattr(pipeline_workflow, "reconcile_words", fail_reconcile)

    result = pipeline_workflow.run_pipeline(PipelineOptions(input_pdf=input_pdf, out_dir=out_dir))

    assert result.reconcile_status == "skipped-key-missing"
    assert result.corrected_words_jsonl is None
    assert result.corrected_searchable_pdf is None
    assert result.final_pdf == out_dir.resolve() / "final" / "input-OCR.pdf"
    assert result.final_pdf.read_text(encoding="utf-8") == "searchable"


def test_pipeline_can_render_word_bbox_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_pdf = tmp_path / "input.pdf"
    input_pdf.write_bytes(b"%PDF-1.4\n")
    out_dir = tmp_path / "out"
    monkeypatch.delenv("SUPERWHISPER_API_KEY", raising=False)

    def fake_searchable(options: SearchableOptions) -> int:
        options.output_pdf.parent.mkdir(parents=True, exist_ok=True)
        options.output_pdf.write_text("searchable", encoding="utf-8")
        assert options.words_jsonl is not None
        options.words_jsonl.write_text("{}", encoding="utf-8")
        return 0

    def fake_mistral(
        pdf: Path,
        output_root: Path,
        pages: str | None = None,
        env_file: Path | None = None,
    ) -> MistralOcrResult:
        del pages, env_file
        sidecar_dir = output_root / pdf.stem
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        combined = sidecar_dir / f"{pdf.stem}.mistral.md"
        combined.write_text("sidecar", encoding="utf-8")
        return MistralOcrResult(output_dir=sidecar_dir, combined_file=combined, page_count=1)

    def fake_visualize(
        *,
        input_pdf: Path,
        words_jsonl: Path,
        output_pdf: Path,
        pages: str | None = None,
        labels: bool = False,
    ) -> tuple[int, int, int]:
        assert input_pdf == (tmp_path / "input.pdf").resolve()
        assert words_jsonl == out_dir.resolve() / "searchable" / "input.words.jsonl"
        assert output_pdf == out_dir.resolve() / "review-bboxes" / "input.words.bboxes.pdf"
        assert pages == "1"
        assert labels is True
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        output_pdf.write_bytes(b"%PDF-1.4\n")
        return 1, 2, 3

    def fake_previews(
        pdf: Path,
        *,
        out_dir: Path,
        pages: tuple[int, ...],
        prefix: str,
        dpi: int = 144,
    ) -> list[Path]:
        assert pdf == out_dir.parent / "input.words.bboxes.pdf"
        assert pages == (1,)
        assert prefix == "input.words.bboxes"
        assert dpi == 144
        preview_file = out_dir / "input.words.bboxes-0001.png"
        preview_file.parent.mkdir(parents=True, exist_ok=True)
        preview_file.write_bytes(b"png")
        return [preview_file]

    monkeypatch.setattr(pipeline_workflow, "run_searchable_pdf", fake_searchable)
    monkeypatch.setattr(pipeline_workflow, "run_mistral_ocr", fake_mistral)
    monkeypatch.setattr(pipeline_workflow, "visualize_bboxes", fake_visualize)
    monkeypatch.setattr(pipeline_workflow, "render_pdf_page_previews", fake_previews)

    result = pipeline_workflow.run_pipeline(
        PipelineOptions(
            input_pdf=input_pdf,
            out_dir=out_dir,
            review_bboxes=True,
            review_pages="1",
            review_labels=True,
            preview_pages=(1,),
        )
    )

    assert result.word_review_pdf == out_dir.resolve() / "review-bboxes" / "input.words.bboxes.pdf"
    assert result.word_review_page_count == 1
    assert result.word_review_line_count == 2
    assert result.word_review_word_count == 3
    assert result.word_preview_files == (
        out_dir.resolve() / "review-bboxes" / "previews" / "input.words.bboxes-0001.png",
    )
    manifest = json.loads(result.manifest_file.read_text(encoding="utf-8"))
    assert manifest["steps"]["word_review"]["status"] == "done"
    assert manifest["steps"]["word_review"]["words"] == 3
    assert manifest["steps"]["word_review"]["previews"] == [str(result.word_preview_files[0])]


def test_pipeline_forced_reconcile_requires_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_pdf = tmp_path / "input.pdf"
    input_pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.delenv("SUPERWHISPER_API_KEY", raising=False)

    def fake_searchable(options: SearchableOptions) -> int:
        options.output_pdf.parent.mkdir(parents=True, exist_ok=True)
        options.output_pdf.write_text("searchable", encoding="utf-8")
        assert options.words_jsonl is not None
        options.words_jsonl.write_text("{}", encoding="utf-8")
        return 0

    def fake_mistral(
        pdf: Path,
        output_root: Path,
        pages: str | None = None,
        env_file: Path | None = None,
    ) -> MistralOcrResult:
        del pages, env_file
        sidecar_dir = output_root / pdf.stem
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        combined = sidecar_dir / f"{pdf.stem}.mistral.md"
        combined.write_text("sidecar", encoding="utf-8")
        return MistralOcrResult(output_dir=sidecar_dir, combined_file=combined, page_count=1)

    monkeypatch.setattr(pipeline_workflow, "run_searchable_pdf", fake_searchable)
    monkeypatch.setattr(pipeline_workflow, "run_mistral_ocr", fake_mistral)

    with pytest.raises(SystemExit, match="SUPERWHISPER_API_KEY"):
        pipeline_workflow.run_pipeline(
            PipelineOptions(input_pdf=input_pdf, out_dir=tmp_path / "out", reconcile_mode="always")
        )


def test_pipeline_passes_ocr_backend_to_searchable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_pdf = tmp_path / "input.pdf"
    input_pdf.write_bytes(b"%PDF-1.4\n")

    def fake_searchable(options: SearchableOptions) -> int:
        assert options.ocr_backend == "rapidocr"
        options.output_pdf.parent.mkdir(parents=True, exist_ok=True)
        options.output_pdf.write_text("searchable", encoding="utf-8")
        assert options.words_jsonl is not None
        options.words_jsonl.write_text("{}", encoding="utf-8")
        return 0

    def fake_mistral(
        pdf: Path,
        output_root: Path,
        pages: str | None = None,
        env_file: Path | None = None,
    ) -> MistralOcrResult:
        del pages, env_file
        sidecar_dir = output_root / pdf.stem
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        combined = sidecar_dir / f"{pdf.stem}.mistral.md"
        combined.write_text("sidecar", encoding="utf-8")
        return MistralOcrResult(output_dir=sidecar_dir, combined_file=combined, page_count=1)

    monkeypatch.setattr(pipeline_workflow, "run_searchable_pdf", fake_searchable)
    monkeypatch.setattr(pipeline_workflow, "run_mistral_ocr", fake_mistral)

    result = pipeline_workflow.run_pipeline(
        PipelineOptions(input_pdf=input_pdf, out_dir=tmp_path / "out", ocr_backend="rapidocr")
    )

    assert result.searchable_pdf.read_text(encoding="utf-8") == "searchable"


def test_pipeline_can_include_chandra_sidecar_for_reconcile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_pdf = tmp_path / "input.pdf"
    input_pdf.write_bytes(b"%PDF-1.4\n")
    out_dir = tmp_path / "out"
    monkeypatch.setenv("SUPERWHISPER_API_KEY", "test-token")

    def fake_searchable(options: SearchableOptions) -> int:
        options.output_pdf.parent.mkdir(parents=True, exist_ok=True)
        options.output_pdf.write_text("searchable", encoding="utf-8")
        assert options.words_jsonl is not None
        options.words_jsonl.write_text("{}", encoding="utf-8")
        return 0

    def fake_mistral(
        pdf: Path,
        output_root: Path,
        pages: str | None = None,
        env_file: Path | None = None,
    ) -> MistralOcrResult:
        del pages, env_file
        sidecar_dir = output_root / pdf.stem
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        combined = sidecar_dir / f"{pdf.stem}.mistral.md"
        combined.write_text("mistral", encoding="utf-8")
        return MistralOcrResult(output_dir=sidecar_dir, combined_file=combined, page_count=1)

    def fake_chandra(options: ChandraOcrOptions) -> ChandraOcrResult:
        assert options.pages == "1"
        assert options.review_bboxes is True
        assert options.preview_pages == (1,)
        return fake_chandra_result(options)

    def fake_reconcile(
        *,
        words_jsonl: Path,
        sidecars: list[Path],
        output_jsonl: Path,
        base_url: str,
        model: str,
        timeout: float,
        api_key: str | None = None,
    ) -> tuple[int, int]:
        del words_jsonl, base_url, model, timeout, api_key
        assert len(sidecars) == 2
        assert sidecars[0].name == "input.mistral.md"
        assert sidecars[1].name == "input.chandra.md"
        output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        output_jsonl.write_text("corrected", encoding="utf-8")
        return 1, 1

    def fake_rebuild(
        input_path: Path, words_jsonl: Path, output_pdf: Path, font_file: Path | None = None
    ) -> tuple[int, int]:
        del input_path, words_jsonl, font_file
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        output_pdf.write_text("rebuilt", encoding="utf-8")
        return 1, 2

    monkeypatch.setattr(pipeline_workflow, "run_searchable_pdf", fake_searchable)
    monkeypatch.setattr(pipeline_workflow, "run_mistral_ocr", fake_mistral)
    monkeypatch.setattr(pipeline_workflow, "run_chandra_ocr", fake_chandra)
    monkeypatch.setattr(pipeline_workflow, "reconcile_words", fake_reconcile)
    monkeypatch.setattr(pipeline_workflow, "rebuild_pdf", fake_rebuild)

    result = pipeline_workflow.run_pipeline(
        PipelineOptions(
            input_pdf=input_pdf,
            out_dir=out_dir,
            pages="1",
            chandra_sidecar=True,
            chandra_review_bboxes=True,
            chandra_preview_pages=(1,),
        )
    )

    assert result.chandra_result is not None
    assert result.chandra_result.total_chunk_count == 2
    manifest = json.loads(result.manifest_file.read_text(encoding="utf-8"))
    assert manifest["steps"]["chandra"]["status"] == "done"
    assert manifest["steps"]["chandra"]["chunks"] == 2
    assert manifest["steps"]["chandra"]["chunk_labels"] == {"Table": 1, "Text": 1}
    assert len(manifest["steps"]["reconcile"]["sidecars"]) == 2


def fake_chandra_result(options: ChandraOcrOptions) -> ChandraOcrResult:
    output_dir = options.out_dir / options.input_pdf.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    json_file = output_dir / f"{options.input_pdf.stem}.chandra.json"
    markdown_file = output_dir / f"{options.input_pdf.stem}.chandra.md"
    html_file = output_dir / f"{options.input_pdf.stem}.chandra.html"
    metadata_file = output_dir / f"{options.input_pdf.stem}.chandra_metadata.json"
    bboxes_pdf = output_dir / "review-bboxes" / f"{options.input_pdf.stem}.chandra.bboxes.pdf"
    preview_file = output_dir / "review-bboxes" / "previews" / f"{options.input_pdf.stem}.chandra.bboxes-0001.png"
    for path in (json_file, markdown_file, html_file, metadata_file, bboxes_pdf, preview_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(path.name, encoding="utf-8")
    return ChandraOcrResult(
        output_dir=output_dir,
        json_file=json_file,
        markdown_file=markdown_file,
        html_file=html_file,
        metadata_file=metadata_file,
        page_count=1,
        total_token_count=12,
        total_chunk_count=2,
        chunk_labels=(("Table", 1), ("Text", 1)),
        bboxes_pdf=bboxes_pdf,
        review_page_count=1,
        review_box_count=2,
        preview_files=(preview_file,),
    )
