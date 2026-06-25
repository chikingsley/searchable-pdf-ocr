# Local Rules

- Use `uv` for all Python commands.
- Keep generated PDFs and JSONL under `runs/` or `outputs/`.
- The searchable text layer comes from PaddleOCR PP-OCRv6 word boxes.
- Structure parsers are sidecars for semantic review; the word-box text-layer engine stays primary.
- Reconciliation edits JSONL artifacts, then rebuilds the PDF from corrected data when a corrected layer is needed.
- Keep Tesseract outside this project path.
- Short rule: PP-OCRv6 places words, sidecars explain layout, Sonnet reconciles corrections.
