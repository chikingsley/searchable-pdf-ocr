# OCR Stack Decisions

Last updated: 2026-06-26.

This repo is a searchable-PDF creator. OCRmyPDF is the PDF writer/raster pipeline, while RapidOCR and PaddleOCR provide local OCR word boxes.

## Active Stack

1. RapidOCR ONNX is the default searchable-PDF locator. It is local, CPU-friendly, uses ONNX Runtime, and produced the best tested speed/word-box granularity on the Persian fixtures.

1. PaddleOCR stays as a fallback locator. It remains useful because OCRmyPDF integration is conservative and Paddle's Arabic-script line-text fix produced correct-direction text on the DLI Persian failure cases. It is slower than RapidOCR on the checked fixtures.

1. Surya is the retained local layout/content sidecar. It gives readable line/block layout and useful review overlays. Word-level PDF placement still comes from RapidOCR or PaddleOCR.

1. Mistral OCR is retained for content extraction and reconciliation input. It is external/API-backed, lightweight in this repo, and feeds the reconciler without taking over box placement.

1. OCRmyPDF remains the PDF writer. The hidden text layer is generated through OCRmyPDF's `generate_ocr()` path from the selected local word-box backend.

## Model Roles

- DET models detect text boxes.
- REC models recognize text inside detected boxes.

They are paired stages. In the Paddle Persian fallback, `PP-OCRv6_medium_det_onnx` finds the text areas and `arabic_PP-OCRv5_mobile_rec_onnx` reads the Arabic-script text.

## Archived Or Removed

| Engine                        | Local Result                                                                                                                                                                 | Decision                                                                                                                              |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Chandra OCR 2                 | Good structured content on FSI/DLI pages, but geometry was coarse chunk/list/table blocks rather than usable line/word placement. It also required a large vLLM/model cache. | Removed from active code. Experiment evidence stays in [ocr-backend-experiments.md](ocr-backend-experiments.md) and commit `4fc0f99`. |
| dots.mocr                     | Interesting layout/content model, outside the chosen searchable-PDF locator path.                                                                                            | Removed from this repo's active plan.                                                                                                 |
| PaddleOCR-VL / PP-StructureV3 | Useful research candidates for document structure, outside the active word-box backend set here.                                                                             | Keep as research notes only.                                                                                                          |

## Fixture Evidence

| Fixture                |                Paddle |             RapidOCR | Result                                                    |
| ---------------------- | --------------------: | -------------------: | --------------------------------------------------------- |
| FSI Persian page 39    |    34 words / 18.106s |    82 words / 5.551s | RapidOCR gave the more useful word-level locator output.  |
| DLI Persian page 7     |    97 words / 14.985s |   109 words / 4.621s | RapidOCR was faster and more granular.                    |
| FSI Persian pages 1-10 | 1501 words / 163.820s | 1735 words / 39.894s | RapidOCR was much faster on the broader scanned baseline. |

## Current Recipe

```bash
uv run searchable-pdf-ocr pipeline input.pdf runs/input \
  --ocr-backend rapidocr \
  --language fas \
  --force-ocr \
  --review-bboxes \
  --preview-page 7
```

Use `--ocr-backend paddle --engine onnxruntime --ocr-version PP-OCRv5 --rec-model-name arabic_PP-OCRv5_mobile_rec` when RapidOCR placement or recognition is worse on a fixture.
