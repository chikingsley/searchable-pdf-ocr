# ClearScan — Experiments Log

Running log for the editable-text layer (Acrobat ClearScan-style): turn a scanned page into text that looks identical to the scan but is real, searchable, editable Unicode text. Newest entries at the bottom. Run something, record what happened.

Companion docs: `README.md` (what this is + how to run the harness), `targets.toml` (upstream clones to triage).

## State of play

What works (proven):

- The PDF-side editability gate. We can mask a scanned region, drop in real visible PDF text, extract it back, and measure visual drift. See 2026-06-26 entries.
- A scan-derived font. We crop the actual glyph shapes off the scanned page, trace them to outlines, build a tiny document-specific TTF **mapped to real Unicode**, embed it, and place editable text in it. This is the part the old SmoothScan C tool never finished (it used arbitrary code points).

What is NOT done yet (the gap between this proof and "ClearScan"):

1. Whole-page automation. The proof is handed the exact region, the source text, and a metrics PDF that already knows each character's position. ClearScan does that itself for a whole page. This is the glyph-discovery front-end — the open V1/V2 decision below.
1. One shape per character vs. every character. The proof builds one `o` and reuses it. A faithful result keeps each occurrence's own observed shape (SmoothScan's clustering idea).
1. Missing-glyph synthesis ("the frontier"). The font is built only from characters that already appear on the page. Typing a character that appears nowhere (e.g. a `7` when the page has no `7`) has no source shape. Options: borrow from a fallback font, generate one in the page's style with a font model (the `repos/` font-generation clones), or restrict edits to characters already present.

Open decision: V1 (OCR-centric — let this repo's OCR find characters + positions, extend the proof to whole pages) vs V2 (clustering-centric — port SmoothScan's connected-component clustering, then label clusters with OCR). V1 → V2 is incremental: the font-build / mask / place / verify code is shared; only the glyph-discovery front-end changes.

## Verification harness

- `tools/make_fixture.py` — build a controlled scanned fixture with known text.
- `tools/simple_visible_edit.py` — mask + insert Helvetica text (editability gate).
- `tools/scanfont_edit.py` — build a scan-derived Unicode font and edit with it.
- `tools/verify_pdf.py` — `probe` a PDF's text/fonts, `compare` two PDFs by pixels.

## 2026-06-26 — Editability gate proven (control fixture)

```bash
uv run clearscan/tools/make_fixture.py clearscan/fixtures/control --dpi 300

uv run clearscan/tools/simple_visible_edit.py \
  clearscan/fixtures/control/control_scan.pdf \
  clearscan/artifacts/control-visible-edit.pdf \
  --erase 70 84 522 131 --pos 72 120 \
  --text 'CLEARSCAN EDIT TEST 2027' --font-size 32
```

`verify_pdf.py` evidence:

- `control_scan.pdf`: `span_count=0`, extracted text empty (it is just an image).
- `control-visible-edit.pdf`: `span_count=1`, font `Helvetica`, text `CLEARSCAN EDIT TEST 2027`.
- Scan vs visible edit at 150 DPI: changed-pixel ratio `0.0051`.
- Ideal vector source vs visible edit at 150 DPI: changed-pixel ratio `0.0020`.

## 2026-06-26 — Scan-derived font proven (control fixture)

```bash
uv run clearscan/tools/scanfont_edit.py \
  clearscan/fixtures/control/control_scan.pdf \
  clearscan/fixtures/control/control_source.pdf \
  clearscan/artifacts/scanfont-control/control-scanfont-edit.pdf \
  --font-out clearscan/artifacts/scanfont-control/ScanGlyphControl-Regular.ttf \
  --crops-dir clearscan/artifacts/scanfont-control/crops \
  --manifest clearscan/artifacts/scanfont-control/manifest.json \
  --source-text 'CLEARSCAN EDIT TEST 2026' \
  --text 'CLEARSCAN EDIT TEST 2022' \
  --erase 70 84 522 131 --pos 72 120 --font-size 32
```

Artifacts: `ScanGlyphControl-Regular.ttf` (2104 bytes), edited PDF (62010 bytes), per-glyph crops, and a manifest of source boxes / contour counts / advances.

Evidence:

- Extracted text `CLEARSCAN EDIT TEST 2022`; visible span font `ScanGlyphControl-Regular`.
- PDF font entry: embedded `ttf`, `Type0`, `Identity-H`.
- cmap includes `space 0 2 A C D E I L N R S T`.
- Scan vs scan-font edit at 150 DPI: changed-pixel ratio `0.0087`.
- Ideal `2022` vector source vs scan-font edit at 150 DPI: ratio `0.0091`.

`2026` → `2022` works because every replacement glyph is observed in the scan. `2026` → `2027` would need a `7` source (fallback font or synthesis).

## 2026-06-26 — Real document, single-character edit (Persian FSI scan)

First run on a real scan rather than the synthetic control: `fixtures/persian-real/fsi-page-001.pdf` (FSI Persian title page).

- `reports/persian-real/title-scan-vs-edit/` and `title-final-e-to-d/` — edited a single title character; `verify_pdf.py probe` confirms one real visible span in `ScanGlyphControl-Regular` (`Type0`, `Identity-H`) reading `D`.

So the scan-derived-font path runs on a real document — but so far only at single-glyph / single-line scale, with boxes supplied rather than discovered.

## 2026-06-26 — Upstream triage

Cloned under ignored `repos/`: `smoothscan`, `vecglypher`, `gar-font`, `glyphspatialnet`, `fontanimate`, `fontdiffuser`, `gc-font`.

- SmoothScan (2013 C, ~800 lines + a FontForge script): correlation-clusters connected components → potrace-traces each unique symbol → embeds a TTF via libharu → places each blob as a one-char reference. Maps symbols to **arbitrary** code points, so its text is not real text; its own TODO says "map symbols from OCR." Build deps (`fontforge`, `potrace`, `leptonica`, `libharu`) are all absent on this box, and it is GPLv3 (potrace is GPL too) while this repo is MPL-2.0. Decision: keep as architecture reference, do not compile or port its code; the clustering idea can be reimplemented in Python (OpenCV/fontTools) license-clean.
- VecGlypher: HF model `VecGlypher/VecGlypher-27b-it`, Gemma3, ~27.4B BF16, ~54.9 GB. Strongest vector-glyph candidate but needs heavy/remote inference.
- FontDiffuser: HF Space checkpoints cached under `cache/fontdiffuser-space` (~421 MB); a 20-step sample ran locally in ~1.1 s producing raster glyphs (would need vectorizing before font embedding).

The font-generation clones (vecglypher, gar-font, gc-font, fontdiffuser, fontanimate) are only relevant to missing-glyph synthesis (the frontier), not to V1 or V2 of the editable pipeline.

## 2026-06-26 — Finding: OCR is word-level, and Persian is the wrong first fixture

Checked what this repo's OCR actually emits (`runs/.../*.words.jsonl`): boxes are **line- and word-level, not character-level**. For the FSI Persian page, each "word" box is a whole connected cursive cluster (e.g. `قسمت بسك` is one box). The backends expose no per-character boxes.

Consequences for the editable layer:

- Glyph-per-character cutting needs per-letter boxes. For Latin/printed text a word box can be split into letters (connected components / spacing). For Persian it cannot be split cleanly: the script is cursive + RTL, letters connect and take different positional forms (isolated/initial/medial/final). "One glyph per Unicode character" does not even apply.
- So FSI Persian is not "the hardest version of the same method" — it needs a *different* method (word-level retype in a matched Persian font, which the main repo already does for the searchable layer with NotoNaskhArabic), not glyph-cutting. It is a bad first test of the glyph-cutting machine: it would fail for script-shaping reasons, not pipeline reasons.

Two distinct products fall out of this:

1. Pixel-faithful ClearScan (cut the font from the page's own ink, edit freely): natural for Latin/printed docs; the synthesis frontier extends it to unobserved characters. Prove the machine on a Latin page first.
1. Persian/Arabic editable layer: word-level retype in a good Persian font + mask the scan. Looks typeset/clean rather than pixel-identical. Closer to the existing rebuild path.

Note: some synthesis models are script-specific — FontDiffuser's examples are Chinese glyphs, so it may not transfer to Latin/Arabic; VecGlypher/GAR-Font would need checking for script coverage before relying on them for "generate the rest."

## 2026-06-26 — Direction locked: pixel-faithful ClearScan on Latin

Product decision: the only target is pixel-faithful ClearScan on Latin/printed pages (cut the font from the page's own ink, edit freely). Persian/RTL is out of scope. Test fixture: the FSI "Spoken Persian" book's English front matter (pages 1–15 are typewritten, degraded, skewed English — a real "bad scan"). OCR word boxes already exist for pages 1–10 in `runs/fsi-persian/spoken-persian/compare-pages-1-10/` (100% Latin; the scan is bad enough that OCR misreads `RESUME`→`RESUNE`, `SPOKEN`→`SPCKEN`).

## 2026-06-26 — Experiment 1: letter segmentation (the missing V1 front-end)

Built `tools/letter_boxes.py`. It renders a page from the source PDF at OCR resolution, crops each OCR word box, and splits it into per-letter boxes two ways, with overlay PNGs: `cc` (raw connected components, merged by x-overlap to rejoin i/j dots + accents) and `ocr` (same components forced to the OCR word's character count).

```bash
uv run clearscan/tools/letter_boxes.py \
  "runs/fsi-persian/spoken-persian/compare-pages-1-10/rapidocr/Spoken Persian.words.jsonl" \
  1 clearscan/reports/letterbox-page1 --crop 200 650 2300 400
```

Result on page 1 (179 words): `cc` found 1143 letters, `ocr` 1132, expected 1132 — within ~1%. Overlays at `reports/letterbox-page1/page1-{cc,ocr}-crop.png`.

Findings:

- Raw connected-components segmentation is **excellent** on degraded typewriter English: every letter cleanly isolated, i/j dots merged into stems, punctuation caught. Typewriter near-monospace + separated letters is the friendly case. No OCR string needed for the boxes.
- So **segmentation is not the hard part** for this class of document — the SmoothScan CC idea, reimplemented in a few lines of OpenCV, just works.
- The weak link is **labeling**: glyph *shapes* are perfect, but each glyph's Unicode label comes from OCR, so OCR misreads corrupt the font cmap. The title's `M` glyph is perfect but tagged `N` (OCR read `RESUNE`), so copy/search would return `RESUNE`. This is display-faithful but text-imperfect — the same error class the searchable layer has, fixable by the existing reconcile pass. Do not claim "editable ground-truth text"; claim "pixel-faithful display + OCR-accurate text."

Decision: use raw `cc` segmentation as the V1 front-end (label from OCR, reconcile later). Next: identity rebuild — cut one glyph per distinct letter, build the document font, re-render the whole page with the *same* text, and `verify_pdf.py compare` against the original. A low changed-pixel ratio on a no-op rebuild is the real "pixel-faithful at page scale" proof; edits come after that passes.

## 2026-06-26 — Experiment 2: whole-page identity rebuild (it works)

Built `tools/rebuild_page.py`: segment letters (cc) → per-line baseline + font size → cut one representative glyph per distinct char and build a Unicode TTF (reuses `scanfont_edit.build_font`) → place every letter occurrence at its own box → save PDF → compare.

```bash
uv run clearscan/tools/rebuild_page.py \
  "runs/fsi-persian/spoken-persian/compare-pages-1-10/rapidocr/Spoken Persian.words.jsonl" \
  1 clearscan/artifacts/rebuild-page1
uv run clearscan/tools/verify_pdf.py compare \
  "<source>/Spoken Persian.PDF" clearscan/artifacts/rebuild-page1/page1-rebuild.pdf \
  --page 1 --dpi 150 --out-dir clearscan/artifacts/rebuild-page1/compare
```

Result on page 1: 1130 letters placed from a 63-glyph document font. Rendered page (`compare/right.png`) is the whole "DOCUMENT RESUME" page reconstructed entirely from vector glyphs cut from the scan's own ink, as real extractable text (`get_text()` returns `DOCUMENT RESUNE / ED 053 ...`). Changed-pixel ratio **0.076** at 150 dpi; mean abs channel delta 9.4/255.

Diff analysis (`compare/diff.png`) — what the 7.6% actually is:

- **Registration is good.** Letters show as faint *edge* outlines, not doubled ghosts → per-line baseline + position are right. So the segmentation→placement chain is sound.
- **Biggest contributors are legitimate background removal:** the scan's torn dark top border and paper speckle are bright in the diff because the clean rebuild omits them. A fair "text fidelity" metric would composite over the original background or threshold the diff.
- **Stroke weight:** vector glyphs are slightly thinner than the typewriter ink → thin edge halos.
- **OCR mislabel propagates into the *picture*, not just the text:** the title `RESUME` rendered as `RESUNE` because placement is driven by the OCR label and OCR read the `M` as `N`, so the `N` glyph was placed. This is the key architecture lesson.

Architecture lesson → separates the user's two requirements cleanly:

- Pixel-faithful display = drive *placement* by the actual cut shape at each position (or by visual clustering of shapes), NOT by the OCR label. Then OCR errors never corrupt the image.
- "Edit the real text" = drive the *cmap / hidden text* by OCR labels corrected via the existing consensus/reconcile pass (Mistral + Sonnet). Shapes are physical; labels are correctable.

Levers to drop the ratio next: (1) composite text over the cleaned original page instead of pure white (also preserves non-text content); (2) match stroke weight (lower threshold / slight dilate); (3) shape-driven placement to kill mislabel artifacts.

## 2026-06-26 — Experiment 3: clean modern scan (Tajik textbook)

New fixture: `Tajiki - An Elementary Textbook (Volume 2).pdf` (321pp, scan, no text layer, mixed English + Tajik Cyrillic, photos/colored boxes). Ran the repo's lean `searchable` OCR on PDF p9 (printed `xiii`, "Introduction to Tajiki", clean English prose) at 400 dpi, then `rebuild_page`.

```bash
uv run searchable-pdf-ocr searchable "<tajik>" out.pdf --ocr-backend rapidocr \
  --language eng --pages 9 --force-ocr --device cpu --words-jsonl ...tajik-p9.words.jsonl
uv run clearscan/tools/rebuild_page.py ...tajik-p9.words.jsonl 9 ...rebuild-p9 --dpi 400
```

Result: 1927 letters, 55 glyphs. Rendered page (`rebuild-p9/rebuilt.png`) — body text is **much cleaner than the FSI typewriter**: the serif body font cut from the page is crisp and readable. changed_ratio 0.21, but inflated by (a) a building photo on the page that the text-only rebuild omits and (b) two real bugs below.

Two bugs surfaced (good — concrete next work):

- **Large display type breaks.** The title "Introduction to Tajiki" overlaps/garbles — big letters need per-line fontsize/placement that doesn't collide.
- **Recurring black-blob glyphs** for specific characters (every "Tajiki" and "Indo-European" smears). Likely cause: `build_font` picks the *first* occurrence of each char as the representative, and the first `T`/`I` got cut from the messy title or an italic word → a bad filled trace propagates to every occurrence. Fix: choose a better representative (median-size body occurrence) or go per-occurrence/visual-cluster.

Takeaways:

- On clean print the approach is clearly viable; the residual is fixable glyph-quality, not a dead end.
- This page was English. Tajik Cyrillic *content* pages need a Cyrillic OCR model for the labels (segmentation is language-agnostic). Cyrillic is separated-letter like Latin, so glyph-cutting fits (unlike Persian cursive).
- "Full PDF" needs compositing text over the original page (to keep photos/figures) + a real TOC/bookmarks — the user's three levels (OCR done; TOC + assembly next).

## 2026-06-26 — Experiment 4: composite mode + representative fix (Tajik p9)

Added `--composite` to `rebuild_page.py` (keep the original page as background, white out only the OCR text boxes, place vector text on top -> photos/figures survive) and changed representative selection from "first occurrence" to "median height with an outlier-width filter" (rejects a `T` whose crop swallowed its neighbor).

```bash
uv run clearscan/tools/rebuild_page.py ...tajik-p9.words.jsonl 9 ...rebuild-p9c --dpi 400 --composite
```

Results (see `artifacts/tajik/rebuild-p9c/`):

- Composite works: the page photo is preserved; only text is replaced.
- Black blobs gone; the `T`-ate-its-neighbor contamination (`The`->`Tahe`) is largely fixed.
- Body text is now clean and readable.

But a real ceiling remains, inherent to one-glyph-per-character (dedup):

- A few letters still render wrong because one representative serves all occurrences (`Tajiki`->`Taiiki`: the `j` representative is bad).
- The **title (large display type) is still broken** — mostly erased with only a few letters placed. Big-type segmentation/placement needs its own handling.

Conclusion: dedup-representative gets "mostly clean body text" but cannot be pixel-faithful — one bad crop per character and large type both defeat it. The decisive next step is **per-occurrence / shape-driven placement**: cut each letter's own shape and place it (title letters cut at their own size; OCR mislabels can no longer select a wrong shape). Searchability then comes from a separate hidden real-text layer (reconciled OCR), cleanly separating display (shapes) from text (labels). Cyrillic content pages (needs a Cyrillic OCR model) are deferred until the rebuild engine is solid.

All three experiment tools (`letter_boxes`, `rebuild_page`) plus `editpdf/tools/edit_pdf` are lint-clean.

## 2026-06-26 — Experiment 5: per-occurrence vector engine + 3-script validation

Built `tools/clearscan_page.py`. Instead of one shared glyph per character, it traces the **actual ink** of each OCR text box into vector outlines (even-odd fill for holes), draws it in the word's **sampled ink colour** over its sampled local background, then adds an **invisible OCR text layer** for search. Display = traced ink; text = hidden layer. This separates the two concerns the `RESUNE` bug exposed, and because the look is literal ink it is **script-agnostic**.

What it is / isn't (corrected after review): this is a faithful **searchable re-render**, not type-to-edit text — the visible layer is vector paths, the text layer is invisible. It is close to the repo's existing `searchable` output (scan image + OCR layer) but swaps raster text for sampled-colour vector. Search works; clean copy/paste is approximate (hidden-text spacing is word-box-based). The deduped editable font (`rebuild_page.py`) remains the only type-to-edit path (Latin/Cyrillic, fidelity ceiling).

Validated on three scripts (recipes saved in `recipes.md`):

- **English** — Tajik textbook p9. The dedup bugs are all gone: the bold title "Introduction to Tajiki" is perfect, italics render, "Proto-Indo-European" is clean, every glyph correct. Extracted text accurate. Drift vs original: mean abs 4.65/255; the ~10% changed-pixel count is anti-aliasing halos (crisp vector vs fuzzy scan edges), not structural error.
- **Cyrillic (Tajik)** — p14, photo-heavy. OCR `paddle cyrillic_PP-OCRv5_mobile_rec`. Display is pixel-faithful **including every Tajik diacritic** (`гӯштингирӣ`, `ҷаҳидан`, `Машқи`) even though the recognizer drops them in the hidden text (`ӣ`->`и`, `ӯ`->`у`, `ҷ`->`ц`, `ҳ`->`х`, `қ`->`к`). Proves display is OCR-independent.
- **Persian cursive** — FSI Spoken Persian p39. The vector engine reproduces the connected RTL ribbons faithfully — the case the dedup font fundamentally cannot do. Hidden text (Persian OCR) is approximate; display is faithful.

Conclusion: `clearscan_page.py` is the universal faithful-display + searchable engine (any script). One engine; recipes differ only in OCR model + hidden-text font. `rebuild_page.py` (dedup font) remains the type-to-edit path, limited to clean Latin/Cyrillic with a fidelity ceiling. Pick by need: faithful look + search -> clearscan_page; retype-able text -> rebuild_page.

Remaining work: reconcile the hidden text (esp. Tajik diacritics + Persian) for accurate search; match stroke weight if a lower pixel-diff is wanted; real TOC/bookmarks + multi-page assembly for a "full PDF".

## 2026-06-26 — Experiment 6: TOC extraction (the "first test")

Question posed: can an agent build the table of contents programmatically? Yes. Built `tools/toc_from_ocr.py`: OCR the contents page, pair each title with its trailing page token, map printed->PDF pages via a fixed offset, emit structured entries + a pymupdf `set_toc` bookmark list.

Offset for this book: PDF p14's first line is printed "2", so printed N = PDF N+12 (front matter shifts it). Run on the Tajik TOC (p3):

```bash
uv run searchable-pdf-ocr searchable INPUT.pdf out.pdf --ocr-backend rapidocr --language eng \
  --pages 3 --force-ocr --device cpu --words-jsonl toc.words.jsonl
uv run clearscan/tools/toc_from_ocr.py toc.words.jsonl toc.json --offset 12
```

Result: 13 entries — front matter + 7 chapters (Sport->PDF p23, Around the Dastarkhon->p51, Clothing->p101, At the University->p173, City and Village Life->p207, Welcome to Tajikistan->p255) + 3 appendices. Feasible end-to-end; `set_toc(bookmarks)` is then one line.

Limits (OCR, not method): some chapter headers merge into the title ("CHR 3 Sport"), and a page number was misread ("At the Hospital" -> 19 instead of 119 -> wrong PDF target). A reconcile/verify pass on the TOC text fixes both. Roman/appendix pages have no integer PDF target.

## 2026-06-26 — Experiment 7: reconcile + stroke match + multi-page assembly (all three follow-ups)

**Reconcile (accurate hidden text).** superwhisper-api is local at `127.0.0.1:8787` (model `claude-sonnet-4-6`); key `SUPERWHISPER_API_KEY` lives in `~/github/peacock-asr/.env`, `MISTRAL_API_KEY` in `~/github/pimsleur-hub/.env.local`. Pipeline: `mistral-ocr` page -> markdown sidecar (Mistral captures Tajik diacritics well) -> `reconcile --words-jsonl <paddle> --sidecar <mistral.md>` -> Sonnet returns per-word corrections (bbox fixed, writes `corrected_text`). On Tajik p14: 9 corrections, every diacritic fixed (`цахидан`->`ҷаҳидан`, `вазнбардори`->`вазнбардорӣ`, `Машки`->`Машқи`). Made `letter_boxes.iter_words` prefer `corrected_text`, so the corrected text flows into the engine; re-render confirms `ҷаҳидан`, `вазнбардорӣ`, `Машқи` are now in `get_text()` (Liberation Sans covers them).

**Stroke match.** Added `--dilate-px` to `clearscan_page.py` (thicken traced ink to match scan weight; colour still sampled from the un-dilated mask). On p9: dilate 0 -> mean_abs 4.24, dilate 2 -> 2.61 (best, ~38% lower), dilate 3 -> 5.43 (too thick). Default to `--dilate-px 2`.

**Multi-page full PDF.** Refactored the engine to expose `add_page()`; built `tools/build_document.py` — merges page records from one+ `words.jsonl` into one document (each page at its own dpi), and applies TOC bookmarks (remapping original PDF page -> assembled index). Assembled the "Introduction to Tajiki" section (PDF p9–12 = printed xiii–xvi) into a 4-page searchable PDF with the bookmark "Introduction to Tajiki" -> assembled p1. Scales to the whole book by OCR-ing the range and feeding `toc.bookmarks.json`.

State: the scan lane now has a complete pipeline — OCR (per-script recipe) -> optional Mistral+Sonnet reconcile for accurate text -> `clearscan_page` faithful searchable render (`--dilate-px 2`) -> `build_document` multi-page assembly + bookmarks. Tools: `letter_boxes`, `rebuild_page` (dedup/editable), `clearscan_page` (faithful searchable), `toc_from_ocr`, `build_document` — all lint-clean.
