from __future__ import annotations

from pdf_pipeline.ocr.constants import LANGUAGE_MAP, SUPPORTED_LANGUAGES


def test_persian_aliases_map_to_paddle_fa() -> None:
    assert LANGUAGE_MAP["fa"] == "fa"
    assert LANGUAGE_MAP["fas"] == "fa"
    assert LANGUAGE_MAP["per"] == "fa"
    assert "fa" in SUPPORTED_LANGUAGES
