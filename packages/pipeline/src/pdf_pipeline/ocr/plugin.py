from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

# PaddlePaddle 3.3.x CPU inference can hit a oneDNN/PIR conversion crash on PP-OCRv6.
os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")

from ocrmypdf import hookimpl
from ocrmypdf.exceptions import MissingDependencyError
from ocrmypdf.models.ocr_element import OcrElement
from ocrmypdf.pluginspec import OcrEngine, OcrOptions, OrientationConfidence
from PIL import Image

from pdf_pipeline.ocr.backends import paddle as paddle_backend
from pdf_pipeline.ocr.backends import rapidocr as rapidocr_backend
from pdf_pipeline.ocr.constants import DEFAULT_DEVICE, DEFAULT_OCR_VERSION, SUPPORTED_LANGUAGES
from pdf_pipeline.ocr.convert import append_jsonl, page_record_to_element

if TYPE_CHECKING:
    from pdf_pipeline.ocr.schema import PageRecord

log = logging.getLogger(__name__)
OCR_ENGINE_NAME = "searchable-pdf-ocr"
DEFAULT_OCR_BACKEND = "rapidocr"
OCR_BACKENDS = {"paddle", "rapidocr"}


def _register_ocr_engine_choice(parser: Any) -> None:  # noqa: ANN401
    for action in parser._actions:  # noqa: SLF001
        if action.dest == "ocr_engine" and action.choices:
            if OCR_ENGINE_NAME in action.choices:
                return
            action.choices = [*action.choices, OCR_ENGINE_NAME]
            return


@hookimpl
def add_options(parser: Any) -> None:  # noqa: ANN401
    _register_ocr_engine_choice(parser)
    group = parser.add_argument_group("Searchable PDF OCR", "RapidOCR/PaddleOCR word-box engine options")
    group.add_argument(
        "--ocr-backend",
        choices=sorted(OCR_BACKENDS),
        default=DEFAULT_OCR_BACKEND,
        help="Word-box OCR backend used by the searchable PDF pipeline.",
    )
    group.add_argument("--paddle-device", default=DEFAULT_DEVICE, help="PaddleOCR device, e.g. cpu, gpu, gpu:0.")
    group.add_argument("--paddle-ocr-version", default=DEFAULT_OCR_VERSION, help="PaddleOCR model family.")
    group.add_argument("--paddle-lang", help="PaddleOCR language override. Defaults to OCRmyPDF -l first language.")
    group.add_argument("--paddle-det-model-name", help="PaddleOCR text detection model name.")
    group.add_argument("--paddle-rec-model-name", help="PaddleOCR text recognition model name.")
    group.add_argument("--paddle-det-model-dir", help="Local text detection model directory.")
    group.add_argument("--paddle-rec-model-dir", help="Local text recognition model directory.")
    group.add_argument(
        "--paddle-engine",
        choices=("paddle", "paddle_static", "paddle_dynamic", "onnxruntime"),
        help="PaddleX inference engine.",
    )
    group.add_argument("--paddle-enable-hpi", action="store_true", help="Enable PaddleX high-performance inference.")
    group.add_argument(
        "--paddle-use-tensorrt", action="store_true", help="Use Paddle Inference TensorRT when available."
    )
    group.add_argument("--paddle-precision", choices=("fp32", "fp16"), default="fp32", help="TensorRT precision.")
    group.add_argument("--paddle-cpu-threads", type=int, help="PaddleOCR CPU inference threads.")
    group.add_argument("--paddle-rec-batch-size", type=int, help="PaddleOCR recognition batch size.")
    group.add_argument("--paddle-debug-jsonl", help="Append page-level word/line OCR records to this JSONL.")
    group.add_argument(
        "--paddle-enable-orientation",
        action="store_true",
        help="Enable PaddleOCR document orientation and textline orientation modules.",
    )
    group.add_argument(
        "--paddle-enable-unwarping",
        action="store_true",
        help="Enable PaddleOCR document image unwarping. Disabled by default so boxes map to the source raster.",
    )


@hookimpl
def check_options(options: OcrOptions) -> None:
    backend = _ocr_backend(options)
    if backend == "paddle" and paddle_backend.available() is False:
        message = "PaddleOCR is unavailable. Install project dependencies with uv sync."
        raise MissingDependencyError(message)
    if backend == "rapidocr" and rapidocr_backend.available() is False:
        message = "RapidOCR is unavailable. Install project dependencies with uv sync."
        raise MissingDependencyError(message)


class SearchablePdfOcrEngine(OcrEngine):
    @staticmethod
    def version() -> str:
        return paddle_backend.version()

    @staticmethod
    def creator_tag(options: Any) -> str:  # noqa: ANN401
        if _ocr_backend(options) == "rapidocr":
            return f"RapidOCR {rapidocr_backend.version()}"
        version = SearchablePdfOcrEngine.version()
        family = getattr(options, "paddle_ocr_version", DEFAULT_OCR_VERSION)
        return f"PaddleOCR {version} ({family})"

    def __str__(self) -> str:
        return f"Searchable PDF OCR ({DEFAULT_OCR_BACKEND})"

    @staticmethod
    def languages(options: Any) -> set[str]:  # noqa: ANN401, ARG004
        return set(SUPPORTED_LANGUAGES)

    @staticmethod
    def get_orientation(input_file: Path, options: Any) -> OrientationConfidence:  # noqa: ARG004, ANN401
        return OrientationConfidence(angle=0, confidence=0.0)

    @staticmethod
    def get_deskew(input_file: Path, options: Any) -> float:  # noqa: ARG004, ANN401
        return 0.0

    @staticmethod
    def supports_generate_ocr() -> bool:
        return True

    @staticmethod
    def generate_ocr(input_file: Path, options: Any, page_number: int = 0) -> tuple[OcrElement, str]:  # noqa: ANN401
        with Image.open(input_file) as image:
            width, height = image.size
            dpi_value = _image_dpi(image.info.get("dpi"), getattr(options, "image_dpi", None))
        record = _recognize_page(
            input_file=input_file,
            options=options,
            source_pdf=_source_pdf(options, input_file),
            page_number=page_number + 1,
            width=width,
            height=height,
            dpi=float(dpi_value),
        )
        debug_jsonl = getattr(options, "paddle_debug_jsonl", None)
        if debug_jsonl:
            append_jsonl(Path(debug_jsonl), record.model_dump(mode="json"))
        return page_record_to_element(record), record.plain_text

    @staticmethod
    def generate_hocr(
        input_file: Path,
        output_hocr: Path,
        output_text: Path,
        options: OcrOptions,
    ) -> None:
        del input_file, output_hocr, output_text, options
        raise NotImplementedError("PaddleOCR uses OCRmyPDF's generate_ocr() API.")

    @staticmethod
    def generate_pdf(
        input_file: Path,
        output_pdf: Path,
        output_text: Path,
        options: OcrOptions,
    ) -> None:
        del input_file, output_pdf, output_text, options
        raise NotImplementedError("PaddleOCR uses OCRmyPDF's generate_ocr() API.")


def _recognize_page(
    *,
    input_file: Path,
    options: Any,  # noqa: ANN401
    source_pdf: Path,
    page_number: int,
    width: int,
    height: int,
    dpi: float,
) -> PageRecord:
    backend = _ocr_backend(options)
    if backend == "rapidocr":
        return rapidocr_backend.recognize_page(
            input_file=input_file,
            options=options,
            source_pdf=source_pdf,
            page_number=page_number,
            width=width,
            height=height,
            dpi=dpi,
        )
    return paddle_backend.recognize_page(
        input_file=input_file,
        options=options,
        source_pdf=source_pdf,
        page_number=page_number,
        width=width,
        height=height,
        dpi=dpi,
    )


def _image_dpi(raw_dpi: object, option_dpi: object) -> float:
    fallback = float(option_dpi) if isinstance(option_dpi, int | float) and option_dpi > 0 else 300.0
    if isinstance(raw_dpi, list | tuple) and raw_dpi:
        value = raw_dpi[0]
        if isinstance(value, int | float) and value > 0:
            return float(value)
    return fallback


def _source_pdf(options: Any, fallback: Path) -> Path:  # noqa: ANN401
    source = getattr(options, "input_file", None)
    if isinstance(source, str | Path):
        return Path(source)
    return fallback


def _ocr_backend(options: Any) -> str:  # noqa: ANN401
    backend = str(getattr(options, "ocr_backend", DEFAULT_OCR_BACKEND))
    if backend in OCR_BACKENDS:
        return backend
    return DEFAULT_OCR_BACKEND


@hookimpl(tryfirst=True)
def get_ocr_engine(options: Any | None = None) -> SearchablePdfOcrEngine | None:  # noqa: ANN401
    if options is None:
        return SearchablePdfOcrEngine()
    selected = getattr(options, "ocr_engine", "auto")
    if selected in ("auto", OCR_ENGINE_NAME):
        return SearchablePdfOcrEngine()
    return None
