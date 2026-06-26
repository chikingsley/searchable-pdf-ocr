from __future__ import annotations

from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rapidocr import EngineType, LangRec, ModelType, RapidOCR
from rapidocr.utils.typings import OCRVersion

from searchable_pdf_ocr.convert import rapidocr_result_to_page_record

if TYPE_CHECKING:
    from searchable_pdf_ocr.schema import PageRecord

ARABIC_SCRIPT_LANGUAGES = {"ar", "ara", "fa", "fas", "per", "urd", "ur"}


def available() -> bool:
    try:
        package_version("rapidocr")
    except PackageNotFoundError:
        return False
    return True


def version() -> str:
    try:
        return package_version("rapidocr")
    except PackageNotFoundError:
        return "unavailable"


def recognize_page(
    *,
    input_file: Path,
    options: Any,  # noqa: ANN401
    source_pdf: Path,
    page_number: int,
    width: int,
    height: int,
    dpi: float,
) -> PageRecord:
    ocr = _get_rapidocr(recognition_language=_recognition_language(options))
    result = ocr(input_file, return_word_box=True, use_cls=False)
    return rapidocr_result_to_page_record(
        result,
        source_image=source_pdf,
        page_number=page_number,
        width=width,
        height=height,
        dpi=dpi,
    )


@lru_cache(maxsize=8)
def _get_rapidocr(*, recognition_language: str | None) -> Any:  # noqa: ANN401
    params: dict[str, Any] = {
        "Global.return_word_box": True,
        "Global.use_cls": False,
        "Global.log_level": "warning",
    }
    if recognition_language == "arabic":
        params.update(
            {
                "Det.engine_type": EngineType.ONNXRUNTIME,
                "Det.model_type": ModelType.SMALL,
                "Det.ocr_version": OCRVersion.PPOCRV6,
                "Rec.engine_type": EngineType.ONNXRUNTIME,
                "Rec.lang_type": LangRec.ARABIC,
                "Rec.model_type": ModelType.MOBILE,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
            }
        )
    return RapidOCR(params=params)


def _recognition_language(options: Any) -> str | None:  # noqa: ANN401
    languages = [str(language).lower() for language in list(getattr(options, "languages", []) or [])]
    if languages == []:
        return None
    if languages[0] in ARABIC_SCRIPT_LANGUAGES:
        return "arabic"
    return None
