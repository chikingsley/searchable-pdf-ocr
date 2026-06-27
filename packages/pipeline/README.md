# pdf-pipeline

The OCR -> searchable PDF -> ClearScan text-layer pipeline (steps 1-2 of the PDF-manipulation workspace).

- `pdf_pipeline.ocr` — OCR a scanned/image PDF into a searchable PDF + word boxes (RapidOCR / PaddleOCR via OCRmyPDF). CLI: `searchable-pdf-ocr`. See the repo root README for usage.
- `pdf_pipeline.clearscan` — turn the OCR word boxes into a faithful, searchable ClearScan-style re-render (`clearscan_page`), assemble multi-page documents with bookmarks (`build_document`), extract a TOC (`toc_from_ocr`), and segment letters (`letter_boxes`).
- `pdf_pipeline.verify` — probe/compare PDFs for verification.

Per-script recipes (English / Cyrillic-Tajik / Persian) are in `recipes.md`.
