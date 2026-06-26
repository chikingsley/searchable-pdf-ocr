# ClearScan Experiments

Workspace for Acrobat ClearScan-style experiments: scanned text to editable/vector PDF text while preserving the original page look.

## Layout

- `repos/` ignored clones of upstream research/code.
- `fixtures/` ignored local PDFs and rendered images.
- `artifacts/` ignored generated outputs.
- `cache/` ignored model/runtime cache when a repo needs local files.
- `reports/` ignored run reports and metrics.
- `tools/` tracked local harness scripts for fixtures and verification.

## Working Target

The target is a same-looking editable PDF while regenerated document export stays outside this experiment lane.

Experiment loop:

1. Create or choose a scanned PDF fixture with known source text.
1. Extract OCR boxes and candidate text from this repo.
1. Segment source glyph crops from the rendered page image with traceable page coordinates.
1. Vectorize observed glyphs or synthesize missing glyphs when the scan lacks a needed character.
1. Build an embedded document-specific font with usable Unicode mappings.
1. Mask source scan text and insert visible Unicode text with the generated font.
1. Verify rendered similarity, visible text objects, embedded fonts, and text extraction.

## Candidate Upstreams

| Repo                     | Role                                                                  | First question                                                         |
| ------------------------ | --------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `ncraun/smoothscan`      | Old ClearScan-like symbol table, vectorization, custom TTF PDF output | Can its extraction/vectorization architecture still run or be ported?  |
| `xk-huang/VecGlypher`    | CVPR 2026 vector glyph generation from prompts or image exemplars     | Can it generate usable SVG outlines for missing glyphs?                |
| `xtryer-s/GAR-Font`      | CVPR 2026 few-shot multimodal font generation                         | Can it generate raster glyphs from scan-derived style references?      |
| `sp777g/GlyphSpatialNet` | CVPR 2026 glyph spatial preservation/font generation                  | Is its preprocessing or spatial rendering useful for glyph extraction? |
| `zichongc/FontAnimate`   | ICCV 2025 few-shot diffusion font generation                          | Is it practical on this GPU and usable as style completion?            |

## Local Verification

Create a controlled scanned fixture:

```bash
uv run experiments/clearscan/tools/make_fixture.py experiments/clearscan/fixtures/control
```

Probe a PDF:

```bash
uv run experiments/clearscan/tools/verify_pdf.py probe experiments/clearscan/fixtures/control/control_scan.pdf
```

Compare two PDFs by rendered page pixels:

```bash
uv run experiments/clearscan/tools/verify_pdf.py compare \
  experiments/clearscan/fixtures/control/control_scan.pdf \
  experiments/clearscan/artifacts/some-output.pdf \
  --out-dir experiments/clearscan/reports/some-output
```
