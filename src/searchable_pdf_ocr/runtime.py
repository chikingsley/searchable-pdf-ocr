from __future__ import annotations

from typing import Any, cast

from ocrmypdf import hookimpl
from ocrmypdf._plugin_manager import OcrmypdfPluginManager, get_plugin_manager
from ocrmypdf.builtin_plugins import tesseract_ocr


@hookimpl
def _skip_tesseract_dependency_check(options: Any) -> None:  # noqa: ANN401
    del options


def searchable_pdf_plugin_manager() -> OcrmypdfPluginManager:
    cast("Any", tesseract_ocr).check_options = _skip_tesseract_dependency_check
    return get_plugin_manager([])
