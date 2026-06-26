from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from searchable_pdf_ocr.mistral_sidecar import MistralOcrResult
from searchable_pdf_ocr.workflows import pipeline as pipeline_workflow
from searchable_pdf_ocr.workflows.pipeline import PipelineOptions

if TYPE_CHECKING:
    from searchable_pdf_ocr.workflows.searchable import SearchableOptions


def test_pipeline_auto_reconciles_and_rebuilds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_pdf = tmp_path / "input.pdf"
    input_pdf.write_bytes(b"%PDF-1.4\n")
    out_dir = tmp_path / "out"
    monkeypatch.setenv("SUPERWHISPER_API_KEY", "test-token")

    def fake_searchable(options: SearchableOptions) -> int:
        assert options.ocr_backend == "rapidocr"
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
