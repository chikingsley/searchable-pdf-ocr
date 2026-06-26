# Searchable PDF OCR

Build searchable PDFs from scanned/image PDFs using local OCR word boxes plus optional content sidecars.

This is a searchable-PDF creator built on OCRmyPDF's writer/raster pipeline. The repo adds local word-box OCR backends, review overlays, Mistral content extraction, and optional text reconciliation.

## Active Stack

- **PDF writer:** OCRmyPDF 17 `generate_ocr()` / `OcrElement` creates the hidden text layer.
- **Default locator/recognizer:** RapidOCR ONNX provides the first-pass local OCR boxes and text.
- **Fallback locator/recognizer:** PaddleOCR / PaddleX stays available for documents where it beats RapidOCR.
- **Content sidecar:** Mistral OCR Markdown.
- **Layout review sidecar:** Surya `results.json` overlays through `review-surya`.
- **Correction pass:** Superwhisper/Sonnet reconciliation edits word JSONL while keeping box coordinates fixed.

No Tesseract path is used.

The project license is MPL-2.0 because this started as an MPL-licensed OCRmyPDF plugin fork. Keep `LICENSE` with source distributions and keep MPL notices intact.

## Model Roles

DET and REC models are different pieces of an OCR pipeline:

- **DET** means text detection. It finds text regions or line boxes on the page.
- **REC** means text recognition. It reads the cropped text image and returns characters.

They are paired stages with different jobs. For example, `PP-OCRv6_medium_det_onnx` finds text areas, while `arabic_PP-OCRv5_mobile_rec_onnx` reads Arabic-script text inside those areas. A better detector can find cleaner boxes; a better recognizer can read text better inside a box. Bad output can come from either side.

RapidOCR also uses detector/recognizer models internally. In this repo, “RapidOCR ONNX” means the RapidOCR runtime plus its ONNX detector/recognizer model set.

## One-Shot Searchable PDF

Run the whole workflow into one output directory:

```bash
uv run searchable-pdf-ocr pipeline input.pdf runs/input \
  --ocr-backend rapidocr \
  --pages 1-10 \
  --device cpu
```

The pipeline writes:

- `searchable/input.searchable.pdf`
- `searchable/input.words.jsonl`
- optional `review-bboxes/input.words.bboxes.pdf`
- optional `review-bboxes/previews/input.words.bboxes-0001.png`
- `sidecars/input/input.mistral.md`
- `input.pipeline.json`
- `final/input-OCR.pdf`

When `SUPERWHISPER_API_KEY` is available, the pipeline can run reconciliation and rebuild:

- `reconcile/input.corrected.words.jsonl`
- `rebuild/input.corrected.searchable.pdf`

Use `--reconcile` to require reconciliation, `--no-reconcile` to skip it, and `--no-rebuild` to keep corrected JSONL without regenerating the PDF. `--env-file` is passed to Mistral and can also supply `SUPERWHISPER_API_KEY`.

The `final` PDF copies the best generated PDF for quick review: the corrected rebuild when reconciliation runs, otherwise the first searchable PDF. Use `--final-suffix -OCR` or `--final-pdf /path/to/output-OCR.pdf` to control that review copy.

Use `--font-file /home/simon/.local/share/fonts/NotoNaskhArabic.ttf` when rebuilding Persian or Arabic text layers.

## Important Options

```bash
--ocr-backend rapidocr
--ocr-backend paddle
--device cpu
--device gpu:0
--language eng
--language ara
--pages 1-10
--jobs 2
--force-ocr
--skip-text
--deskew
--rotate-pages
--det-model-name PP-OCRv6_medium_det
--rec-model-name PP-OCRv6_medium_rec
--engine onnxruntime
--enable-hpi
--rec-batch-size 8
--words-jsonl runs/doc.words.jsonl
```

`--force-ocr` tells OCRmyPDF to rasterize and OCR pages even if the source PDF already has a text layer. Use it for scanned PDFs, bad existing OCR, or tests where you want the chosen backend to produce fresh boxes. Avoid it when the existing text layer is already good and you only need PDF optimization.

`--skip-text` is the opposite: skip pages that already have text.

## Persian/Farsi Recipe

RapidOCR is the default first pass:

```bash
uv run searchable-pdf-ocr pipeline input.pdf runs/input-fa \
  --ocr-backend rapidocr \
  --language fas \
  --force-ocr \
  --review-bboxes \
  --preview-page 7
```

Use the Paddle fallback when RapidOCR placement or recognition is worse on a fixture:

```bash
uv run searchable-pdf-ocr pipeline input.pdf runs/input-fa-paddle \
  --ocr-backend paddle \
  --language fas \
  --ocr-version PP-OCRv5 \
  --rec-model-name arabic_PP-OCRv5_mobile_rec \
  --engine onnxruntime \
  --force-ocr
```

For Paddle Arabic-script runs, the current local model pairing is:

- Detector: `PP-OCRv6_medium_det_onnx`
- Recognizer: `arabic_PP-OCRv5_mobile_rec_onnx`
- Engine: `onnxruntime`
- Device: `cpu`

## Review Commands

Render word-box placement directly on the PDF:

```bash
uv run searchable-pdf-ocr review-bboxes input.pdf \
  --words-jsonl runs/input-fa/rapidocr/words.jsonl \
  --out runs/input-fa/review-bboxes/rapidocr.bboxes.pdf \
  --pages 7 \
  --labels \
  --preview-page 7
```

Compare RapidOCR and Paddle in one folder:

```bash
uv run searchable-pdf-ocr compare-backends input.pdf runs/input-fa/compare-page7 \
  --language fas \
  --ocr-version PP-OCRv5 \
  --rec-model-name arabic_PP-OCRv5_mobile_rec \
  --engine onnxruntime \
  --force-ocr \
  --jobs 1 \
  --pages 7 \
  --preview-page 7
```

`compare-backends` writes one backend folder per engine, review bbox PDFs, optional preview PNGs, and a `*.compare.json` manifest with page/line/word counts, Arabic-script counts, per-page stats, and elapsed time.

## Sidecars

Mistral OCR creates Markdown content for review and reconciliation:

```bash
uv run searchable-pdf-ocr mistral-ocr input.pdf \
  --out-dir runs/sidecars
```

`MISTRAL_API_KEY` is read from the process environment first, then from `/home/simon/github/pimsleur-hub/.env.local`. Use `--env-file` to point at a different file.

Surya is retained as a local layout/content review sidecar. The automatic pipeline currently uses Mistral for content sidecars; run Surya separately, then use this repo to draw its boxes on the source PDF:

```bash
uv run searchable-pdf-ocr review-surya input.pdf runs/surya/results.json \
  --out runs/surya/review-bboxes/input.surya.bboxes.pdf \
  --pages 7 \
  --labels \
  --preview-page 7
```

When Surya was run on a selected page, its `results.json` page numbers are local to that run. Use `--page-base` and `--page-offset` to map those boxes back to the original PDF:

```bash
uv run searchable-pdf-ocr review-surya input.pdf runs/surya/results.json \
  --document-key "Units 01-05 Listening" \
  --page-base 1 \
  --page-offset 6 \
  --out runs/surya/review-bboxes/page-7.surya.bboxes.pdf \
  --pages 7 \
  --preview-page 7
```

Chandra and dots.mocr experiments are archived in [docs/ocr-backend-experiments.md](docs/ocr-backend-experiments.md). Active code uses RapidOCR, Paddle, Surya review, Mistral, and OCRmyPDF.

## Reconcile

Use Sonnet through the local Superwhisper API to correct OCR word text against one or more sidecars:

```bash
SUPERWHISPER_API_KEY=... uv run searchable-pdf-ocr reconcile \
  --words-jsonl runs/input.words.jsonl \
  --sidecar runs/sidecars/input/input.mistral.md \
  --out runs/input.corrected.words.jsonl
```

The reconciler keeps `word_id` and `bbox` fixed. It only writes `corrected_text`.

## Rebuild From Corrected Words

```bash
uv run searchable-pdf-ocr rebuild input.pdf \
  --words-jsonl runs/input.corrected.words.jsonl \
  --out output.corrected.searchable.pdf
```

Normal production should prefer the OCRmyPDF one-shot renderer. `rebuild` exists so corrected OCR data can be regenerated without running OCR again.

## Architecture

```text
PDF
  -> OCRmyPDF raster page
  -> selected word-box backend
       -> RapidOCR return_word_box=True
       -> PaddleOCR predict(return_word_box=True)
  -> PAGE/LINE/WORD OcrElement tree
  -> OCRmyPDF searchable PDF
  -> optional word JSONL
  -> optional sidecar content
       -> Mistral OCR Markdown
       -> Surya block/layout JSON review overlays
  -> optional LLM reconciliation
  -> optional corrected rebuild
```

## Runtime Notes

The CLI bypasses OCRmyPDF's built-in Tesseract binary probe while keeping OCRmyPDF's normal PDF pipeline. CPU PP-OCRv6 also sets `PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=0`, because current PaddlePaddle CPU inference can hit a oneDNN/PIR crash with PP-OCRv6.

The one-shot OCRmyPDF path is validated on scanned/image PDFs. Vector-only synthetic PDFs currently hit an OCRmyPDF 17 zero-DPI renderer edge case in the modern `generate_ocr()` path; for those, use `rebuild` from generated word JSONL or rasterize first.

Acceleration flags are exposed through the CLI, but the installed environment must provide the matching backend. Use `paddlepaddle-gpu` from a CUDA-specific PaddlePaddle index for GPU execution, and install PaddleX HPI / Paddle2ONNX / ONNX Runtime before using `--enable-hpi` or `--engine onnxruntime`.

## Development

```bash
uv lock
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
uv run vulture src tests --min-confidence 80
uv run dslop README.md AGENTS.md docs src
uv run mdformat --check README.md AGENTS.md docs
```
