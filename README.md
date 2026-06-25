# OCRmyPDF PaddleOCR

Modern OCRmyPDF engine plugin for searchable PDFs using PaddleOCR PP-OCRv6 word boxes.

This repo is intentionally narrow:

- **Searchable PDF text layer:** PaddleOCR general OCR / PP-OCRv6 with `return_word_box=True`.
- **PDF writing:** OCRmyPDF 17 `generate_ocr()` / `OcrElement`; no hand-written hOCR path.
- **Structure sidecars:** separate Markdown/JSON passes such as Mistral OCR, dots.mocr, PP-StructureV3, or PaddleOCR-VL.
- **Reconciliation:** LLM corrections edit the word JSONL, then the PDF is regenerated from corrected data.

No Tesseract path is used.

## One-Shot Searchable PDF

Run the whole local-plus-API workflow into one output directory:

```bash
uv run paddle-searchable-pdf pipeline input.pdf runs/input \
  --pages 1-10 \
  --device cpu
```

The pipeline writes:

- `searchable/input.searchable.pdf`
- `searchable/input.words.jsonl`
- optional `review-bboxes/input.words.bboxes.pdf`
- optional `review-bboxes/previews/input.words.bboxes-0001.png`
- `sidecars/input/input.mistral.md`
- optional `sidecars/chandra/input/input.chandra.*`
- `input.pipeline.json`
- `final/input-OCR.pdf`

By default it also runs Superwhisper/Sonnet reconciliation when `SUPERWHISPER_API_KEY` is present, then rebuilds:

- `reconcile/input.corrected.words.jsonl`
- `rebuild/input.corrected.searchable.pdf`

Use `--reconcile` to require reconciliation, `--no-reconcile` to skip it, and `--no-rebuild` to keep corrected JSONL without regenerating the PDF. `--env-file` is passed to Mistral and can also supply `SUPERWHISPER_API_KEY` for the pipeline.

The `final` PDF copies the best generated PDF for quick review: the corrected rebuild when reconciliation runs, otherwise the first searchable PDF. Use `--final-suffix -OCR` or `--final-pdf /path/to/output-OCR.pdf` to control that review copy. Use `--font-file /path/to/NotoNaskhArabic.ttf` when rebuilding Persian or Arabic text layers.

Add `--review-bboxes --preview-page N` to render the word-level placement overlay during the same pipeline run.

Add Chandra as a structure sidecar in the same pipeline run when a Chandra vLLM server is already running:

```bash
uv run --with chandra-ocr==0.2.0 paddle-searchable-pdf pipeline input.pdf runs/input \
  --pages 39 \
  --ocr-backend rapidocr \
  --language fas \
  --engine onnxruntime \
  --force-ocr \
  --review-bboxes \
  --preview-page 39 \
  --chandra-sidecar \
  --chandra-vllm-api-base http://127.0.0.1:8000/v1 \
  --chandra-review-bboxes \
  --chandra-preview-page 39
```

Run only the searchable PDF step:

```bash
uv run paddle-searchable-pdf input.pdf output.searchable.pdf \
  --device cpu \
  --words-jsonl runs/input.words.jsonl
```

The command is equivalent to:

```bash
uv run paddle-searchable-pdf searchable input.pdf output.searchable.pdf
```

Useful options:

```bash
--ocr-backend paddle
--ocr-backend rapidocr
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

For Persian/Farsi A/B runs, compare the Paddle path against RapidOCR in separate run folders:

```bash
uv run paddle-searchable-pdf searchable input.pdf runs/input-fa/paddle/output.searchable.pdf \
  --ocr-backend paddle \
  --language fas \
  --ocr-version PP-OCRv5 \
  --rec-model-name arabic_PP-OCRv5_mobile_rec \
  --engine onnxruntime \
  --words-jsonl runs/input-fa/paddle/words.jsonl

uv run paddle-searchable-pdf searchable input.pdf runs/input-fa/rapidocr/output.searchable.pdf \
  --ocr-backend rapidocr \
  --language fas \
  --words-jsonl runs/input-fa/rapidocr/words.jsonl
```

Review box placement directly on the PDF:

```bash
uv run paddle-searchable-pdf review-bboxes input.pdf \
  --words-jsonl runs/input-fa/paddle/words.jsonl \
  --out runs/input-fa/review-bboxes/paddle.bboxes.pdf
```

Review Surya OCR/layout JSON boxes directly on the PDF:

```bash
uv run paddle-searchable-pdf review-surya input.pdf runs/surya/results.json \
  --out runs/surya/review-bboxes/input.surya.bboxes.pdf \
  --pages 7 \
  --labels \
  --preview-page 7
```

Run Chandra OCR sidecar JSON, Markdown, HTML, and metadata through an existing Chandra vLLM server:

```bash
uv run --with chandra-ocr==0.2.0 paddle-searchable-pdf chandra-ocr input.pdf runs/chandra \
  --pages 39 \
  --method vllm \
  --vllm-api-base http://127.0.0.1:8000/v1 \
  --max-output-tokens 2048 \
  --batch-size 1 \
  --review-bboxes \
  --preview-page 39
```

The Chandra metadata includes total tokens, chunk counts, chunk-label counts, generated artifact paths, and review-preview paths.

Review Chandra OCR/layout chunk JSON boxes directly on the PDF:

```bash
uv run paddle-searchable-pdf review-chandra input.pdf runs/chandra/page.chandra.json \
  --out runs/chandra/review-bboxes/input.chandra.bboxes.pdf \
  --pages 7 \
  --labels \
  --preview-page 7
```

When Surya was run on a selected page, its `results.json` page numbers were local to that run. Use `--page-base` and `--page-offset` to map those boxes back to the original PDF:

```bash
uv run paddle-searchable-pdf review-surya input.pdf runs/surya/results.json \
  --document-key "Units 01-05 Listening" \
  --page-base 1 \
  --page-offset 6 \
  --out runs/surya/review-bboxes/page-7.surya.bboxes.pdf \
  --pages 7 \
  --preview-page 7
```

Run both local word-box backends into one organized comparison folder:

```bash
uv run paddle-searchable-pdf compare-backends input.pdf runs/input-fa/compare-page7 \
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

## Structure Sidecar

Mistral OCR sidecar:

```bash
uv run paddle-searchable-pdf mistral-ocr input.pdf \
  --out-dir runs/sidecars
```

`MISTRAL_API_KEY` is read from the process environment first, then from `/home/simon/github/pimsleur-hub/.env.local`. Use `--env-file` to point at a different file.

Other sidecars should follow the same idea:

- dots.mocr layout JSON/Markdown from `/home/simon/docker/vllm-dots-mocr`
- Surya OCR/layout/table `results.json`, reviewed with `review-surya`
- Chandra OCR/layout Markdown, HTML, and chunk JSON, reviewed with `review-chandra`
- PP-StructureV3 JSON/Markdown
- PaddleOCR-VL full pipeline JSON/Markdown

They are sidecars: semantic structure feeds correction and review, while exact word boxes remain the PDF text-layer contract.

## Reconcile

Use Sonnet through the local Superwhisper API to correct OCR word text against one or more sidecars:

```bash
SUPERWHISPER_API_KEY=... uv run paddle-searchable-pdf reconcile \
  --words-jsonl runs/input.words.jsonl \
  --sidecar runs/sidecars/input/input.mistral.md \
  --out runs/input.corrected.words.jsonl
```

The reconciler keeps `word_id` and `bbox` fixed. It only writes `corrected_text`.

## Rebuild From Corrected Words

```bash
uv run paddle-searchable-pdf rebuild input.pdf \
  --words-jsonl runs/input.corrected.words.jsonl \
  --out output.corrected.searchable.pdf
```

Normal production should prefer the OCRmyPDF one-shot renderer. `rebuild` exists so corrected OCR data can be regenerated without running PaddleOCR again.

## Runtime Notes

The CLI bypasses OCRmyPDF's built-in Tesseract binary probe while keeping OCRmyPDF's normal PDF pipeline. CPU PP-OCRv6 also sets `PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=0`, because current PaddlePaddle CPU inference can hit a oneDNN/PIR crash with PP-OCRv6.

The one-shot OCRmyPDF path is validated on scanned/image PDFs. Vector-only synthetic PDFs currently hit an OCRmyPDF 17 zero-DPI renderer edge case in the modern `generate_ocr()` path; for those, use `rebuild` from generated word JSONL or rasterize first.

Acceleration flags are exposed through the CLI, but the installed environment must provide the matching backend. Use `paddlepaddle-gpu` from a CUDA-specific PaddlePaddle index for GPU execution, and install PaddleX HPI / Paddle2ONNX / ONNX Runtime before using `--enable-hpi` or `--engine onnxruntime`.

The current PP-OCRv6 50-language set covers Chinese, English, Japanese, and Latin-script languages. Use the PP-OCRv5 Arabic-family recognizer for Persian text:

```bash
uv run paddle-searchable-pdf pipeline input.pdf runs/input-fa \
  --language fas \
  --ocr-version PP-OCRv5 \
  --rec-model-name arabic_PP-OCRv5_mobile_rec \
  --engine onnxruntime
```

RapidOCR is available as a second local backend for A/B runs. For Arabic-script languages, it uses RapidOCR 3.9.0 with a PP-OCRv6 small detector and Arabic PP-OCRv5 mobile recognizer.

## Architecture

```text
PDF
  -> OCRmyPDF raster page
  -> selected word-box backend
       -> PaddleOCR PP-OCRv6 predict(return_word_box=True)
       -> RapidOCR return_word_box=True
  -> PAGE/LINE/WORD OcrElement tree
  -> OCRmyPDF searchable PDF
  -> optional word JSONL
  -> optional sidecar parsers
       -> Mistral OCR Markdown
       -> Surya block/layout JSON review overlays
       -> Chandra chunk/layout JSON review overlays
  -> optional LLM reconciliation
  -> optional corrected rebuild
```

## Why PP-OCRv6 Here

PaddleOCR's current general OCR pipeline defaults to PP-OCRv6 medium in PaddleOCR 3.7. The docs also expose `return_word_box`, the data contract needed for a real searchable PDF text layer; PaddleOCR-VL and document parsers still help with structure, table/context review, and correction prompts, while PP-OCRv6 remains the stronger source for word-level PDF placement.

## Development

```bash
uv lock
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
uv run vulture src
uv run dslop README.md AGENTS.md docs src
```
