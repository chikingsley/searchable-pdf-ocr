# ClearScan Recipes

Master recipes for turning a scanned page into a faithful, searchable PDF.

What this is and isn't: the visible layer is **traced vector ink** (per-word sampled colour, over the original page so photos survive) and the text layer is **invisible OCR text**. So the output looks like the scan and is **searchable** (substring find works), but it is **not type-to-edit** text and clean copy/paste is approximate (hidden-text spacing is word-box-based). For retype-able text on clean Latin/Cyrillic use the dedup-font `rebuild_page.py` (in `experiments/`, has a fidelity ceiling). Colour is sampled per word, so black-on-white, gray subtitles, and coloured boxes are preserved; very non-uniform backgrounds can show faint fill seams.

## The one engine

`clearscan-page` (`pdf_pipeline.clearscan.clearscan_page`) is **script-agnostic for display**: it traces the actual ink of each OCR text box into vector outlines and draws them in place, then adds an invisible OCR text layer for search/copy. Because the look comes from traced ink (not a rebuilt font), Latin, Cyrillic, and Persian cursive all render faithfully — the dedup-font approach could not do cursive or large display type. Photos/figures survive via compositing over the original page.

So the recipes differ in only two things: the **OCR model** (for the hidden text) and the **hidden-text font** (must cover the script). Pipeline for every script:

1. OCR -> `words.jsonl` with `searchable-pdf-ocr searchable ... --words-jsonl ...`
1. (optional, for accurate text) reconcile against a Mistral sidecar — see "Accurate text" below.
1. `clearscan-page words.jsonl <page> <out> --dpi <jsonl dpi> --dilate-px 2 --text-font <font>`
1. (optional, multi-page) `clearscan-build` to merge pages + add TOC bookmarks — see "Full document".

Pass `--dpi` equal to the `dpi` recorded in the `words.jsonl` (the OCR coordinate space), not a guess. `--dilate-px 2` thickens the traced ink to match scan stroke weight (measured best on a 400-dpi page; mean abs delta 4.2 -> 2.6). `--no-composite` renders on white instead of over the original page.

## Master recipe: English / Latin

OCR `rapidocr` is enough; hidden-text font Liberation Sans (default).

```bash
uv run searchable-pdf-ocr searchable INPUT.pdf out.pdf \
  --ocr-backend rapidocr --language eng --pages 9 --force-ocr --device cpu \
  --words-jsonl doc.words.jsonl
uv run clearscan-page doc.words.jsonl 9 out_dir --dpi 400 --dilate-px 2
```

Evidence: Tajik textbook p9 ("Introduction to Tajiki", clean English) rebuilt faithfully incl. the bold title; extracted text correct (`experiments/experiments.md`, Experiment 5).

## Master recipe: Cyrillic (Tajik)

OCR `paddle` with the generic Cyrillic recognizer; hidden-text font Liberation Sans (covers Latin + Cyrillic).

```bash
uv run searchable-pdf-ocr searchable INPUT.pdf out.pdf \
  --ocr-backend paddle --ocr-version PP-OCRv5 \
  --rec-model-name cyrillic_PP-OCRv5_mobile_rec \
  --pages 14 --force-ocr --device cpu --words-jsonl doc.words.jsonl
uv run clearscan-page doc.words.jsonl 14 out_dir --dpi 400 --dilate-px 2
```

Quality: base Cyrillic is ~90% correct, but the recognizer (Cyrillic ~= Russian) **drops Tajik-specific letters** in the hidden text: `ӣ`->`и/й`, `ӯ`->`у`, `ҷ`->`ц`, `ҳ`->`х`, `қ`->`к`. This does **not** affect the look — the engine traces those letters perfectly from the ink (verified on p14: `гӯштингирӣ`, `ҷаҳидан`, `Машқи` all display correctly). It only lowers searchable-text accuracy. Fix the text layer with reconcile (LLM) when accuracy matters. Alternative recognizer `eslav_PP-OCRv5_mobile_rec` exists but is East-Slavic-focused (no better for Tajik). Note: Liberation Sans covers the common Tajik letters; a Noto Sans would cover more edge cases in the hidden layer.

## Master recipe: Persian / Perso-Arabic (Dari, Farsi, Tajik-in-Arabic-script)

Script note: Persian is written in the **Perso-Arabic script** (Arabic script + پ چ ژ گ) — cursive, right-to-left. OCR `paddle` with the Arabic recognizer; hidden-text font NotoNaskhArabic.

```bash
uv run searchable-pdf-ocr searchable INPUT.pdf out.pdf \
  --ocr-backend paddle --ocr-version PP-OCRv5 \
  --rec-model-name arabic_PP-OCRv5_mobile_rec --engine onnxruntime \
  --language fas --pages 39 --force-ocr --device cpu --words-jsonl doc.words.jsonl
uv run clearscan-page doc.words.jsonl 39 out_dir --dpi 300 --dilate-px 2 \
  --text-font /home/simon/.local/share/fonts/NotoNaskhArabic.ttf
```

Quality: display is faithful — the engine reproduces the cursive ribbons as-is (verified on FSI Spoken Persian p39). The hidden text is the weakest of the three (cursive + positional forms are hard for OCR); treat Persian as "looks right, search approximate" until reconcile improves the text. The dedup-font path is **not** usable here — cursive has no separable per-letter glyphs.

## Accurate text (reconcile)

When OCR drops characters (e.g. Tajik diacritics, Persian), fix the *hidden text* with the consensus pass: Mistral provides a second reading, Sonnet picks corrections (bbox stays fixed, only `corrected_text` is written). Needs `MISTRAL_API_KEY` (in `~/github/pimsleur-hub/.env.local`) and the local superwhisper-api running at `127.0.0.1:8787` with `SUPERWHISPER_API_KEY` (in `~/github/peacock-asr/.env`).

```bash
uv run searchable-pdf-ocr mistral-ocr INPUT.pdf --out-dir sidecars --pages 14
SUPERWHISPER_API_KEY=... uv run searchable-pdf-ocr reconcile \
  --words-jsonl doc.words.jsonl --sidecar sidecars/<stem>/<stem>.mistral.md \
  --out doc.corrected.words.jsonl
# then run clearscan-page on doc.corrected.words.jsonl (it prefers corrected_text)
```

Verified on Tajik p14: 9 corrections, every diacritic fixed (`цахидан`->`ҷаҳидан`, `Машки`->`Машқи`), and they survive into searchable text. The display never needed this — traced ink is already correct; reconcile only improves search/copy.

## Full document (multi-page + TOC)

Merge many rebuilt pages into one searchable PDF with bookmarks:

```bash
# extract a TOC once from the contents page (clearscan-toc); produces *.bookmarks.json
uv run clearscan-build out.pdf \
  --jsonl a.words.jsonl b.words.jsonl --dilate-px 2 --toc toc.bookmarks.json
```

`clearscan-build` renders each page at its own recorded dpi and remaps TOC targets (original PDF page -> assembled page index). Verified: PDF p9–12 assembled into a 4-page "Introduction to Tajiki" section with a working bookmark.

## When to use the dedup font instead

The dedup-font prototype (`experiments/rebuild_page.py`) builds a real editable Unicode font (one glyph per character). It is only worth it for clean separated-letter scripts (Latin/Cyrillic) when you specifically need *type-to-edit* text rather than faithful display. For faithful, searchable output prefer `clearscan-page`.
