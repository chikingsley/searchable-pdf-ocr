from __future__ import annotations

from pathlib import Path

import pytest

from searchable_pdf_ocr.workflows import searchable as searchable_workflow
from searchable_pdf_ocr.workflows.searchable import SearchableOptions


def test_searchable_passes_ocr_backend_to_ocrmypdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_pdf = tmp_path / "input.pdf"
    output_pdf = tmp_path / "output.pdf"
    words_jsonl = tmp_path / "words.jsonl"
    input_pdf.write_bytes(b"%PDF-1.4\n")

    def fake_ocr(*args: object, **kwargs: object) -> int:
        assert args[0] == input_pdf
        assert args[1] == output_pdf
        assert kwargs["ocr_engine"] == "searchable-pdf-ocr"
        assert kwargs["ocr_backend"] == "rapidocr"
        assert kwargs["paddle_debug_jsonl"] == str(words_jsonl)
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        output_pdf.write_text("pdf", encoding="utf-8")
        words_jsonl.write_text(
            ('{"source_image":"page.png","page_number":1,"width":1,"height":1,"dpi":300,"plain_text":"","lines":[]}\n'),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(searchable_workflow.ocrmypdf, "ocr", fake_ocr)

    exit_code = searchable_workflow.run_searchable_pdf(
        SearchableOptions(input_pdf=input_pdf, output_pdf=output_pdf, ocr_backend="rapidocr", words_jsonl=words_jsonl)
    )

    assert exit_code == 0
