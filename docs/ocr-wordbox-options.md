# OCR Word-Box Options

Last checked: 2026-06-25.

Scope: local/open-source engines only. Exclude hosted OCR APIs, signup-gated services, and Tesseract from this pipeline.

## What Searchable PDF Needs

The searchable PDF text layer needs text plus geometry in source page coordinates. Markdown, HTML, paragraphs, or block boxes alone are useful for content review, but precise hidden-text placement needs tighter geometry.

The practical split is:

- Locator: finds text boxes in page coordinates.
- Recognizer: supplies the text for those boxes.
- Rebuilder: inserts hidden text back into the PDF.

For Arabic-script languages, native word tokens can be worse than line text. PaddleOCR and RapidOCR both returned good-direction line text on the DLI Persian page 7 fixture while their raw word tokens were reversed. The current local strategy is therefore:

- Trust native geometry when it is usable.
- For Arabic-script lines, use line-level recognized text as the canonical text source.
- Use native word boxes only as placement hints when their count cleanly matches the line text.

## Current Local Versions

PyPI latest checks on 2026-06-25:

| Package | Latest | Current State |
| --- | ---: | --- |
| `paddleocr` | 3.7.0 | locked |
| `paddlex` | 3.7.2 | locked |
| `paddlepaddle` | 3.3.1 | locked |
| `onnxruntime` | 1.27.0 | locked |
| `ocrmypdf` | 17.7.0 | locked |
| `pymupdf` | 1.27.2.3 | locked |
| `rapidocr` | 3.9.0 | locked; available through `--ocr-backend rapidocr` |
| `easyocr` | 1.7.2 | queued |
| `surya-ocr` | 0.20.0 | tested via `uvx`; review adapter ready for `results.json`; engine install stays external |
| `chandra-ocr` | 0.2.0 | tested via `uvx`; review adapter ready for saved chunk JSON; engine install stays external |
| `python-doctr` | 1.0.1 | queued |

`uv 0.11.24` reports itself current by `uv self update --dry-run`.

## Ranked Local Candidates

1. PaddleOCR / PaddleX PP-OCR

   Best current local baseline for searchable PDF geometry. The integration already calls `PaddleOCR.predict(..., return_word_box=True)` and stores line/word boxes in JSONL. PP-OCRv6 is the current default OCR family, but for Persian/Farsi use the Arabic-script PP-OCRv5 recognizer explicitly.

   Current Persian recipe:

   - Detector: `PP-OCRv6_medium_det_onnx`
   - Recognizer: `arabic_PP-OCRv5_mobile_rec_onnx`
   - Engine: `onnxruntime`
   - Device: `cpu`

2. RapidOCR 3.9.0

   Second local A/B backend. It is local, ONNX Runtime works on CPU, and it exposes `return_word_box=True`. The repo backend uses `LangRec.ARABIC` and PP-OCRv5 Arabic mobile recognition for Arabic-script languages. On the DLI Persian page 7 fixture, RapidOCR gives tighter word placement in several Persian entries, but recognition quality varies against Paddle.

3. dots.ocr / dots.mocr

   Useful for document layout and content extraction on GPU, but its public local path is block/layout JSON rather than a proven word-level text-layer engine. Keep it as a layout/content sidecar unless word coordinates are confirmed locally.

4. Surya 0.20.0

   Useful for local layout and line detection. Current OCR output is block HTML / layout-oriented, so it fits geometry-helper or quality-reference work better than direct word-box replacement. The repo now has `review-surya` to draw Surya OCR/layout boxes from `results.json` on top of the source PDF. Runtime is heavier than Paddle/RapidOCR: the tested CLI path launched `vllm/vllm-openai:v0.20.1` in Docker and that image is `31.8GB`.

5. Chandra OCR 2 / `chandra-ocr 0.2.0`

   Strong local document OCR/content benchmark candidate, including Arabic-script benchmark coverage. The official CLI writes Markdown, HTML, and metadata; the repo has `review-chandra` for saved chunk JSON from the Python API. Local runs on the FSI and DLI fixtures produced useful table/section layout blocks, but the boxes are coarse document chunks rather than line or word placement.

6. EasyOCR 1.7.2

   Local and simple, with text-region boxes. Keep it as a quick sanity test for documents where Paddle/RapidOCR fail, behind the primary word-placement engines.

7. docTR 1.0.1

   Good object model with page/block/line/word output, but language coverage is the blocker. Treat Persian/Arabic readiness as unproven until a suitable recognizer passes a fixture.

## DLI Persian A/B

Fixture:

`runs/dli-persian/units-01-05-listening/triage-pages-1-10/input/Units 01-05 Listening.pages-1-10.pdf`

| Variant | Models | Pages | Words | Page 7 Words | Time / Status |
| --- | --- | ---: | ---: | ---: | --- |
| `current-explicit-no-orient` | `PP-OCRv6_medium_det_onnx` + `arabic_PP-OCRv5_mobile_rec_onnx` | 10 | 693 | 97 | 1:54.89 wall |
| `explicit-orientation` | orientation classifiers + `PP-OCRv6_medium_det_onnx` + `arabic_PP-OCRv5_mobile_rec_onnx` | 10 | 696 | 97 | 2:09.98 wall |
| `auto-lang-fa-ppocrv5` | selected `PP-OCRv5_server_det_onnx` + `en_PP-OCRv5_mobile_rec_onnx` | 6 partial | 241 | 0 | stopped; wrong recognizer |
| `server-det-arabic-rec` | `PP-OCRv5_server_det_onnx` + `arabic_PP-OCRv5_mobile_rec_onnx` | 4 partial | 168 | 0 | stopped at 8:22.93 wall / 3328.84s user |
| `current-explicit-no-orient-rtl-line-text` | same as current, with Arabic-script line text used for word text | 10 | 693 | 97 | 1:55.15 wall |
| `rapidocr-arabic-ppocrv5` | RapidOCR PP-OCRv6 small detector + Arabic PP-OCRv5 mobile recognizer | 1 page | 36 text lines | n/a | 3.45s engine elapse / 3.83s wall |
| `paddle-compare-page7` | `compare-backends` Paddle run on page 7 | 1 selected page | 97 | 97 | 14.985s backend elapsed |
| `rapidocr-compare-page7` | `compare-backends` RapidOCR run on page 7 | 1 selected page | 109 | 109 | 4.621s backend elapsed |

The original broken Paddle page 7 examples were:

| Line Text | Old Native Word Text | Fixed Text |
| --- | --- | --- |
| `ب كره زمين` | `نيمز هرك ب` | `ب كره زمين` |
| `الفالودكى` | `ىكدولافلا` | `الفالودكى` |
| `تنمايندگان` | `ناگدنيامنت` | `تنمايندگان` |
| `پسازمان` | `نامزاسپ` | `پسازمان` |
| `جتدابير` | `ريبادتج` | `جتدابير` |

The patched Paddle output is here:

`runs/dli-persian/units-01-05-listening/triage-pages-1-10/ab-wordloc/paddle-rtl-line-text/`

The first-class RapidOCR backend output is here:

`runs/dli-persian/units-01-05-listening/triage-pages-1-10/compare-page7/`

RapidOCR line-level Persian examples:

| Text | Score |
| --- | ---: |
| `ب كره زمين` | 0.93664 |
| `الفآلودى` | 0.85295 |
| `تنمايندگان` | 0.85653 |
| `سازمان` | 0.99521 |
| `تدابير` | 0.85318 |
| `ج` | 0.93159 |
| `ث توسعه` | 0.91461 |
| `حهمكاری` | 0.81748 |
| `ج  طرح` | 0.79913 |

## FSI Spoken Persian A/B

Fixture:

`/home/simon/github/pimsleur-hub/course-creation-research/persian/farsi/FSI Persian/Spoken Persian.PDF`

Compared pages 1-10 with:

```bash
uv run paddle-searchable-pdf compare-backends \
  '/home/simon/github/pimsleur-hub/course-creation-research/persian/farsi/FSI Persian/Spoken Persian.PDF' \
  runs/fsi-persian/spoken-persian/compare-pages-1-10 \
  --language fas \
  --ocr-version PP-OCRv5 \
  --rec-model-name arabic_PP-OCRv5_mobile_rec \
  --engine onnxruntime \
  --force-ocr \
  --jobs 1 \
  --pages 1-10 \
  --preview-page 1 \
  --preview-page 5 \
  --preview-page 10
```

| Backend | Pages | Lines | Words | Arabic-Script Lines | Time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Paddle | 10 | 530 | 1501 | 1 | 163.820s |
| RapidOCR | 10 | 534 | 1735 | 0 | 39.894s |

The first 10 pages are mostly English front matter and introduction pages, so this is a placement/speed baseline rather than a Persian-script recognition test. Paddle's one Arabic-script line was noise from a page number: `٣ 8`.

Manifest:

`runs/fsi-persian/spoken-persian/compare-pages-1-10/Spoken Persian.compare.json`

### Page 39 Persian-Script Fixture

Page 39 was selected from the scanned FSI PDF because it is mostly Persian script, unlike the first 10 front-matter pages.

Paddle/RapidOCR command:

```bash
uv run paddle-searchable-pdf compare-backends \
  '/home/simon/github/pimsleur-hub/course-creation-research/persian/farsi/FSI Persian/Spoken Persian.PDF' \
  runs/fsi-persian/spoken-persian/compare-page39 \
  --language fas \
  --ocr-version PP-OCRv5 \
  --rec-model-name arabic_PP-OCRv5_mobile_rec \
  --engine onnxruntime \
  --force-ocr \
  --jobs 1 \
  --pages 39 \
  --preview-page 39
```

| Backend | Pages | Lines | Words | Arabic-Script Lines | Arabic-Script Words | Time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Paddle | 1 | 34 | 34 | 32 | 32 | 18.106s |
| RapidOCR | 1 | 33 | 82 | 33 | 82 | 5.551s |

Manifest:

`runs/fsi-persian/spoken-persian/compare-page39/Spoken Persian.compare.json`

Preview files:

- `runs/fsi-persian/spoken-persian/compare-page39/review-bboxes/previews/Spoken Persian.paddle.bboxes-0039.png`
- `runs/fsi-persian/spoken-persian/compare-page39/review-bboxes/previews/Spoken Persian.rapidocr.bboxes-0039.png`

RapidOCR produced more useful word-level geometry on this page. Paddle mostly fell back to one word per Arabic-script line because that is safer than emitting reversed native word tokens. Recognition quality was rough in both engines.

Surya command:

```bash
mkdir -p 'runs/fsi-persian/spoken-persian/surya-ocr-page39/Spoken Persian'

uvx --from surya-ocr==0.20.0 surya_ocr \
  '/home/simon/github/pimsleur-hub/course-creation-research/persian/farsi/FSI Persian/Spoken Persian.PDF' \
  --page_range 38 \
  --images \
  --output_dir runs/fsi-persian/spoken-persian/surya-ocr-page39
```

Surya wrote `results.json`, stopped its Docker container cleanly, and left the GPU idle afterward. Output:

`runs/fsi-persian/spoken-persian/surya-ocr-page39/Spoken Persian/results.json`

Review command:

```bash
uv run paddle-searchable-pdf review-surya \
  '/home/simon/github/pimsleur-hub/course-creation-research/persian/farsi/FSI Persian/Spoken Persian.PDF' \
  'runs/fsi-persian/spoken-persian/surya-ocr-page39/Spoken Persian/results.json' \
  --document-key 'Spoken Persian' \
  --page-base 1 \
  --page-offset 38 \
  --out 'runs/fsi-persian/spoken-persian/surya-ocr-page39/Spoken Persian.surya.bboxes.pdf' \
  --pages 39 \
  --labels \
  --preview-page 39
```

Result: `pages=1`, `boxes=35`.

Output files:

- `runs/fsi-persian/spoken-persian/surya-ocr-page39/Spoken Persian.surya.bboxes.pdf`
- `runs/fsi-persian/spoken-persian/surya-ocr-page39/previews/Spoken Persian.surya.bboxes-0039.png`

Surya's visible boxes aligned well with the page image and its text was more coherent than the Paddle/RapidOCR recognition on this FSI page. It emits line/block boxes, while RapidOCR remains the stronger current locator for word-level hidden text placement.

Chandra command:

```bash
uvx --from chandra-ocr==0.2.0 chandra \
  '/home/simon/github/pimsleur-hub/course-creation-research/persian/farsi/FSI Persian/Spoken Persian.PDF' \
  runs/fsi-persian/spoken-persian/chandra-ocr-page39 \
  --method vllm \
  --page-range 38 \
  --max-workers 1 \
  --max-retries 1 \
  --max-output-tokens 2048 \
  --batch-size 1 \
  --no-images \
  --save-html
```

Warm result: `34.132s` total.

Saved parsed chunk JSON:

`runs/fsi-persian/spoken-persian/chandra-ocr-page39/Spoken Persian/Spoken Persian.chandra.json`

Chunk result: `error=false`, `token_count=686`, `chunks=6`.

Review command:

```bash
uv run paddle-searchable-pdf review-chandra \
  '/home/simon/github/pimsleur-hub/course-creation-research/persian/farsi/FSI Persian/Spoken Persian.PDF' \
  'runs/fsi-persian/spoken-persian/chandra-ocr-page39/Spoken Persian/Spoken Persian.chandra.json' \
  --out 'runs/fsi-persian/spoken-persian/chandra-ocr-page39/Spoken Persian.chandra.bboxes.pdf' \
  --pages 39 \
  --labels \
  --preview-page 39
```

Output files:

- `runs/fsi-persian/spoken-persian/chandra-ocr-page39/Spoken Persian.chandra.bboxes.pdf`
- `runs/fsi-persian/spoken-persian/chandra-ocr-page39/previews/Spoken Persian.chandra.bboxes-0039.png`

Chandra produced a more structured table-like Markdown/HTML representation than Paddle/RapidOCR, but the body text was one large table block in geometry. Use it as a structure sidecar alongside RapidOCR/Paddle word boxes.

## Current Conclusion

Use PaddleOCR as the production local searchable-PDF locator for now. With the Arabic-script line-text fix, it emits correct-direction Persian text for the tested DLI page 7 failure cases, and runtime stayed within the earlier baseline.

RapidOCR is now integrated as a second local A/B engine. It is faster on both checked fixtures and gives more granular word boxes in places, but its Persian recognition differs from Paddle on the DLI fixture.

For FSI Persian-script page 39 specifically, Surya and Chandra are useful local content/layout sidecars, while RapidOCR gives the most useful word-level locator boxes. The practical next pipeline is to keep RapidOCR/Paddle geometry for the PDF text layer, then reconcile text against Surya, Chandra, or another high-quality content sidecar without moving the boxes.

The main pipeline can include Chandra as an optional sidecar when a Chandra vLLM server is already running:

```bash
uv run --with chandra-ocr==0.2.0 paddle-searchable-pdf pipeline input.pdf runs/input \
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

## Visual Box Review

Use `--review-bboxes --preview-page N` on `pipeline` to inspect word placement in the same run. The pipeline writes `review-bboxes/<input>.words.bboxes.pdf` and optional PNG previews.

Use the standalone `review-bboxes` command to inspect placement quality directly on the PDF:

```bash
uv run paddle-searchable-pdf review-bboxes input.pdf \
  --words-jsonl runs/.../words.jsonl \
  --out runs/.../review-bboxes/output.bboxes.pdf
```

The output draws blue line boxes and green word boxes. Add `--labels` for text labels when a page is sparse enough to stay readable.

Example A/B commands:

```bash
uv run paddle-searchable-pdf compare-backends input.pdf runs/doc/compare-page7 \
  --language fas \
  --ocr-version PP-OCRv5 \
  --rec-model-name arabic_PP-OCRv5_mobile_rec \
  --engine onnxruntime \
  --force-ocr \
  --jobs 1 \
  --pages 7 \
  --preview-page 7
```

The comparison command writes one backend folder per engine, review bbox PDFs, optional preview PNGs, and a `*.compare.json` manifest.

Use `review-surya` for Surya OCR/layout `results.json` files:

```bash
uv run paddle-searchable-pdf review-surya input.pdf runs/surya/results.json \
  --out runs/surya/review-bboxes/input.surya.bboxes.pdf \
  --pages 7 \
  --labels \
  --preview-page 7
```

That command draws orange OCR/layout boxes from Surya `blocks` or `bboxes`. It is for geometry/content review. Searchable PDF text-layer creation still belongs to Paddle/RapidOCR because Surya's current public JSON contract is block/layout oriented rather than per-word placement.

For selected-page Surya runs, map Surya's local result page back to the source PDF with `--page-base` and `--page-offset`:

```bash
uv run paddle-searchable-pdf review-surya input.pdf runs/surya/results.json \
  --document-key "Units 01-05 Listening" \
  --page-base 1 \
  --page-offset 6 \
  --out runs/surya/review-bboxes/page-7.surya.bboxes.pdf \
  --pages 7 \
  --labels \
  --preview-page 7
```

Use `review-chandra` for saved Chandra chunk JSON from the Python API:

```bash
uv run paddle-searchable-pdf review-chandra input.pdf runs/chandra/page.chandra.json \
  --out runs/chandra/page.chandra.bboxes.pdf \
  --pages 7 \
  --labels \
  --preview-page 7
```

Use `chandra-ocr` to create that JSON shape directly from this repo:

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

That runner writes `*.chandra.json`, `*.chandra.md`, `*.chandra.html`, `*.chandra_metadata.json`, and optional bbox review files under `runs/chandra/<input-stem>/`. The metadata file includes total tokens, chunk counts, chunk-label counts, generated artifact paths, and review-preview paths. `review-chandra` still draws orange layout chunk boxes from Chandra `chunks` and accepts the runner JSON.

## Surya DLI Page 7 Proof

Input:

`runs/dli-persian/units-01-05-listening/triage-pages-1-10/input/Units 01-05 Listening.pages-1-10.pdf`

Surya command:

```bash
mkdir -p \
  'runs/dli-persian/units-01-05-listening/triage-pages-1-10/surya-ocr-page7/Units 01-05 Listening'

uvx --from surya-ocr==0.20.0 surya_ocr \
  'runs/dli-persian/units-01-05-listening/triage-pages-1-10/input/Units 01-05 Listening.pages-1-10.pdf' \
  --page_range 6 \
  --images \
  --output_dir 'runs/dli-persian/units-01-05-listening/triage-pages-1-10/surya-ocr-page7'
```

The `mkdir` matters because Surya 0.20.0 attempted to write the nested result folder without creating it on the first run. The first attempt failed with `FileNotFoundError`; the rerun succeeded.

Real Surya output:

`runs/dli-persian/units-01-05-listening/triage-pages-1-10/surya-ocr-page7/Units 01-05 Listening/results.json`

Review command:

```bash
uv run paddle-searchable-pdf review-surya \
  'runs/dli-persian/units-01-05-listening/triage-pages-1-10/input/Units 01-05 Listening.pages-1-10.pdf' \
  'runs/dli-persian/units-01-05-listening/triage-pages-1-10/surya-ocr-page7/Units 01-05 Listening/results.json' \
  --document-key 'Units 01-05 Listening' \
  --page-base 1 \
  --page-offset 6 \
  --out 'runs/dli-persian/units-01-05-listening/triage-pages-1-10/surya-ocr-page7/Units 01-05 Listening.surya.bboxes.pdf' \
  --pages 7 \
  --labels \
  --preview-page 7
```

Result: `pages=1`, `boxes=23`.

Output files:

- `runs/dli-persian/units-01-05-listening/triage-pages-1-10/surya-ocr-page7/Units 01-05 Listening.surya.bboxes.pdf`
- `runs/dli-persian/units-01-05-listening/triage-pages-1-10/surya-ocr-page7/previews/Units 01-05 Listening.surya.bboxes-0007.png`

Surya recognized the Persian entries as block text, including `ب - کره زمین`; `الف - آلودگی`; `ت - نمایندگان`; `پ - سازمان`; `ج - تدابیر`; `ث - توسعه`; `ح - همکاری`; and `چ - طرح`. The boxes are aligned well enough for layout/content review, but they are block boxes rather than word boxes.

## Chandra DLI Page 7 Proof

Input:

`runs/dli-persian/units-01-05-listening/triage-pages-1-10/input/Units 01-05 Listening.pages-1-10.pdf`

Runtime:

- Package: `chandra-ocr==0.2.0`
- Server image: `vllm/vllm-openai:v0.20.1`
- Model: `datalab-to/chandra-ocr-2`
- Working local server config on the RTX 5070 12GB: `--max-model-len 8192`, `--max-num-seqs 1`, `--max-num-batched-tokens 2048`, `--gpu-memory-utilization 0.90`

The first 4096-token server attempt loaded but the page image prompt failed with `Input length (4698) exceeds model's maximum context length (4096)`. The 8192-token server reached readiness. It reported a 9.86 GiB checkpoint, 8.61 GiB model-load memory, 0.98 GiB available KV cache, 22,341 KV tokens, and maximum concurrency `2.73x` for 8192-token requests.

Chandra CLI command:

```bash
uvx --from chandra-ocr==0.2.0 chandra \
  'runs/dli-persian/units-01-05-listening/triage-pages-1-10/input/Units 01-05 Listening.pages-1-10.pdf' \
  'runs/dli-persian/units-01-05-listening/triage-pages-1-10/chandra-ocr-page7' \
  --method vllm \
  --page-range 6 \
  --max-workers 1 \
  --max-retries 1 \
  --max-output-tokens 2048 \
  --batch-size 1 \
  --no-images \
  --save-html
```

Warm result: `10.591s` total.

Saved parsed chunk JSON:

`runs/dli-persian/units-01-05-listening/triage-pages-1-10/chandra-ocr-page7/Units 01-05 Listening.pages-1-10/Units 01-05 Listening.pages-1-10.chandra.json`

Chunk result: `error=false`, `token_count=556`, `chunks=8`.

Review command:

```bash
uv run paddle-searchable-pdf review-chandra \
  'runs/dli-persian/units-01-05-listening/triage-pages-1-10/input/Units 01-05 Listening.pages-1-10.pdf' \
  'runs/dli-persian/units-01-05-listening/triage-pages-1-10/chandra-ocr-page7/Units 01-05 Listening.pages-1-10/Units 01-05 Listening.pages-1-10.chandra.json' \
  --out 'runs/dli-persian/units-01-05-listening/triage-pages-1-10/chandra-ocr-page7/Units 01-05 Listening.pages-1-10.chandra.bboxes.pdf' \
  --pages 7 \
  --labels \
  --preview-page 7
```

Output files:

- `runs/dli-persian/units-01-05-listening/triage-pages-1-10/chandra-ocr-page7/Units 01-05 Listening.pages-1-10.chandra.bboxes.pdf`
- `runs/dli-persian/units-01-05-listening/triage-pages-1-10/chandra-ocr-page7/previews/Units 01-05 Listening.pages-1-10.chandra.bboxes-0007.png`

Visual result: Chandra correctly grouped the page into section/text/list blocks. The Persian/English exercise table became one coarse `List-Group` block, so it is useful for content/layout sidecar work but too coarse for searchable-PDF word placement.

## Next Practical Work

1. Run the patched Paddle path on the first 10 pages of additional language fixtures, especially Arabic-script and Latin-script PDFs, and compare extracted text plus bbox overlays.
2. Run more recurring A/B fixtures through both `--ocr-backend paddle` and `--ocr-backend rapidocr`.
3. Add a first reconciliation experiment that keeps RapidOCR word boxes and substitutes content from Surya/Chandra where the sidecar clearly improves recognition.
4. Test a GPU Paddle container only after `paddlepaddle-gpu` supports this RTX 5070 stack cleanly and `paddle.utils.run_check()` passes.
5. Keep dots.ocr, Surya, and Chandra as content/layout sidecars unless one proves reliable word-level PDF coordinates locally.

## Sources

- PaddleOCR GitHub: https://github.com/PaddlePaddle/PaddleOCR
- PaddleOCR pipeline output docs: http://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html
- PP-OCRv5 multilingual docs: http://www.paddleocr.ai/main/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html
- Arabic PP-OCRv5 recognizer model card: https://huggingface.co/PaddlePaddle/arabic_PP-OCRv5_mobile_rec
- RapidOCR usage docs: https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/
- RapidOCR model list: https://rapidai.github.io/RapidOCRDocs/main/model_list/
- dots.ocr GitHub: https://github.com/rednote-hilab/dots.ocr
- dots.ocr Hugging Face: https://huggingface.co/rednote-hilab/dots.ocr
- Surya GitHub: https://github.com/datalab-to/surya
- Chandra GitHub: https://github.com/datalab-to/chandra
- EasyOCR GitHub: https://github.com/JaidedAI/EasyOCR
- docTR GitHub: https://github.com/mindee/doctr
