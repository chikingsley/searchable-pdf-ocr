# ClearScan Status

Current date: 2026-06-26.

## Workspace

Tracked files live under `experiments/clearscan/`.

Ignored local state:

- `repos/` upstream clones
- `cache/` downloaded model/checkpoint files
- `fixtures/` local PDF/image fixtures
- `artifacts/` generated PDFs/images
- `reports/` rendered comparisons and JSON probes

## Verification Harness

Created:

- `tools/make_fixture.py`
- `tools/simple_visible_edit.py`
- `tools/verify_pdf.py`

Controlled fixture:

```bash
uv run experiments/clearscan/tools/make_fixture.py experiments/clearscan/fixtures/control --dpi 300
```

Visible-edit proof:

```bash
uv run experiments/clearscan/tools/simple_visible_edit.py \
  experiments/clearscan/fixtures/control/control_scan.pdf \
  experiments/clearscan/artifacts/control-visible-edit.pdf \
  --erase 70 84 522 131 \
  --pos 72 120 \
  --text 'CLEARSCAN EDIT TEST 2027' \
  --font-size 32
```

Evidence from `verify_pdf.py`:

- `control_scan.pdf`: `span_count=0`, extracted text empty.
- `control-visible-edit.pdf`: `span_count=1`, font `Helvetica`, extracted text `CLEARSCAN EDIT TEST 2027`.
- Render comparison, scan versus visible edit at 150 DPI: changed pixel ratio `0.0050642899584076055`.
- Render comparison, ideal edited vector source versus visible edit at 150 DPI: changed pixel ratio `0.002016399286987522`.

This proves the PDF-side editability gate: we can mask a scanned region, insert real visible PDF text, extract that text, and measure visual drift.

## Upstream Clone Triage

Cloned under ignored `repos/`:

- `smoothscan`
- `vecglypher`
- `gar-font`
- `glyphspatialnet`
- `fontanimate`
- `fontdiffuser`
- `gc-font`

### SmoothScan

`autoreconf -fi && ./configure` stops at missing `fontforge`.

System dependency check showed:

- `pkg-config`, `autoreconf`, `make`, and `gcc` are present.
- Leptonica runtime is present as `1.6.58`.
- `fontforge`, `potrace`, and `libhpdf` are absent from PATH/pkg-config output.

Useful architecture from source:

- Leptonica `JBCLASSER` groups connected components into symbols.
- Templates are written as per-symbol PNGs.
- FontForge `autoTrace()` vectorizes symbol PNGs into glyph outlines.
- A generated TrueType font is embedded into PDF with libharu.
- Existing mapping uses arbitrary KOI8-R code points, so Unicode/OCR mapping needs replacement.

### VecGlypher

Released HF model: `VecGlypher/VecGlypher-27b-it`.

HF metadata: Gemma3 architecture, 27.432B BF16 parameters, public and ungated access, and about `54.9GB` storage.

VecGlypher appears to be the strongest vector-glyph candidate, but it needs remote/heavier inference or quantized/offloaded serving before local runs on the 12 GB GPU.

### FontDiffuser

Downloaded HF Space files to ignored cache:

```text
experiments/clearscan/cache/fontdiffuser-space
```

Cache size: `421M`.

Important files:

- `ckpt/unet.pth`
- `ckpt/content_encoder.pth`
- `ckpt/style_encoder.pth`

Working isolated runtime:

```bash
uv run --no-project --python 3.11 \
  --index https://download.pytorch.org/whl/cu128 \
  --index-strategy unsafe-best-match \
  --with torch \
  --with torchvision \
  --with diffusers==0.22.0 \
  --with accelerate==0.23.0 \
  --with transformers==4.33.1 \
  --with huggingface-hub==0.19.4 \
  --with pyyaml \
  --with opencv-python \
  --with info-nce-pytorch \
  --with kornia \
  --with scipy \
  --with safetensors \
  --with pygame \
  --with fonttools \
  sample.py \
  --ckpt_dir ckpt \
  --content_image_path figures/source_imgs/source_灨.jpg \
  --style_image_path figures/ref_imgs/ref_壤.jpg \
  --save_image \
  --save_image_dir /home/simon/docker/searchable-pdf-ocr/experiments/clearscan/artifacts/fontdiffuser-20step \
  --device cuda:0 \
  --num_inference_steps 20
```

Runtime facts:

- Python `3.11.15` via uv.
- Torch `2.12.1+cu130`.
- CUDA visible on `NVIDIA GeForce RTX 5070`.
- 20-step sample completed in about `1.13s`.
- Output is raster glyph imagery, so it is useful for style completion tests, then needs vectorization before PDF font embedding.

## Current Direction

The promising build path is SmoothScan architecture plus modern glyph generation:

1. Use OCR word/character boxes from this repo as placement anchors.
1. Segment glyph crops from scanned pages into reusable symbol images.
1. Cluster repeated glyphs with a SmoothScan-style dictionary step.
1. Generate observed glyph outlines through tracing or a vector model.
1. Generate missing glyphs with VecGlypher, GAR-Font, or FontDiffuser plus vectorization.
1. Build a Unicode-mapped embedded font from the final glyph set.
1. Use PyMuPDF to mask scanned text and place visible text objects.
1. Verify visual drift and real text extraction with the local harness.
