from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import paddleocr as paddleocr_module

from pdf_pipeline.ocr.constants import DEFAULT_DEVICE, DEFAULT_OCR_VERSION, LANGUAGE_MAP
from pdf_pipeline.ocr.convert import paddle_result_to_page_record

if TYPE_CHECKING:
    from pdf_pipeline.ocr.schema import PageRecord

log = logging.getLogger(__name__)

try:
    from paddleocr import PaddleOCR as PaddleOCRClass
except ImportError:  # pragma: no cover - exercised only in missing optional dependency installs
    PaddleOCRClass: Any = None


def available() -> bool:
    return bool(PaddleOCRClass)


def version() -> str:
    return str(getattr(paddleocr_module, "__version__", "unknown"))


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
    ocr = _get_paddle_ocr(
        lang=_paddle_lang(options),
        device=str(getattr(options, "paddle_device", DEFAULT_DEVICE)),
        ocr_version=str(getattr(options, "paddle_ocr_version", DEFAULT_OCR_VERSION)),
        det_model_name=getattr(options, "paddle_det_model_name", None),
        rec_model_name=getattr(options, "paddle_rec_model_name", None),
        det_model_dir=getattr(options, "paddle_det_model_dir", None),
        rec_model_dir=getattr(options, "paddle_rec_model_dir", None),
        engine=getattr(options, "paddle_engine", None),
        enable_hpi=bool(getattr(options, "paddle_enable_hpi", False)),
        use_tensorrt=bool(getattr(options, "paddle_use_tensorrt", False)),
        precision=str(getattr(options, "paddle_precision", "fp32")),
        cpu_threads=getattr(options, "paddle_cpu_threads", None),
        rec_batch_size=getattr(options, "paddle_rec_batch_size", None),
        enable_orientation=bool(getattr(options, "paddle_enable_orientation", False)),
        enable_unwarping=bool(getattr(options, "paddle_enable_unwarping", False)),
    )
    result = ocr.predict(os.fspath(input_file), return_word_box=True)
    page_result = result[0] if result else {}
    return paddle_result_to_page_record(
        page_result,
        source_image=source_pdf,
        page_number=page_number,
        width=width,
        height=height,
        dpi=dpi,
    )


@lru_cache(maxsize=8)
def _get_paddle_ocr(
    *,
    lang: str,
    device: str,
    ocr_version: str,
    det_model_name: str | None,
    rec_model_name: str | None,
    det_model_dir: str | None,
    rec_model_dir: str | None,
    engine: str | None,
    enable_hpi: bool,
    use_tensorrt: bool,
    precision: str,
    cpu_threads: int | None,
    rec_batch_size: int | None,
    enable_orientation: bool,
    enable_unwarping: bool,
) -> Any:  # noqa: ANN401
    if PaddleOCRClass is None:
        message = "PaddleOCR is unavailable"
        raise RuntimeError(message)
    kwargs: dict[str, Any] = {
        "device": device,
        "lang": lang,
        "ocr_version": ocr_version,
        "use_doc_orientation_classify": enable_orientation,
        "use_doc_unwarping": enable_unwarping,
        "use_textline_orientation": enable_orientation,
        "engine": engine,
        "enable_hpi": enable_hpi,
        "use_tensorrt": use_tensorrt,
        "precision": precision,
    }
    if cpu_threads:
        kwargs["cpu_threads"] = cpu_threads
    if rec_batch_size:
        kwargs["text_recognition_batch_size"] = rec_batch_size
    if det_model_name:
        kwargs["text_detection_model_name"] = det_model_name
    if rec_model_name:
        kwargs["text_recognition_model_name"] = rec_model_name
    if det_model_dir:
        kwargs["text_detection_model_dir"] = det_model_dir
    if rec_model_dir:
        kwargs["text_recognition_model_dir"] = rec_model_dir
    log.info("Initializing PaddleOCR with %s", kwargs)
    return PaddleOCRClass(**kwargs)


def _paddle_lang(options: Any) -> str:  # noqa: ANN401
    override = getattr(options, "paddle_lang", None)
    if override:
        return str(override)
    languages = list(getattr(options, "languages", []) or [])
    if languages == []:
        return "en"
    return LANGUAGE_MAP.get(str(languages[0]).lower(), str(languages[0]).lower())
