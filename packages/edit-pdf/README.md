# edit-pdf

Step 3 of the PDF-manipulation workspace, and a separate product from the `pdf-pipeline` (ClearScan) lane. ClearScan is for *scanned* pages (pixels, no text, no font). This lane is for **digital PDFs that already carry real text and embedded fonts** (resumes, modern docs, most forms): the Acrobat "Edit PDF / treat it like a Word doc" experience.

Key idea: we do not invent or identify glyphs. The real font is already embedded in the file, so we **extract it and edit text on top of it**, keeping the native look.

## Which lane does a PDF belong in?

```bash
uv run edit-pdf classify path/to/file.pdf
```

- DIGITAL (real text layer + embedded fonts) -> this lane.
- SCAN (image, little/no text) -> the `pdf-pipeline` ClearScan lane.

## Edit text in its own font

```bash
uv run edit-pdf edit input.pdf out.pdf --find 'May 2018' --replace 'May 2019'
```

The tool finds the text, extracts the matching embedded font, removes the old text, and re-inserts the replacement in that font at the same baseline/size/color. It reports any replacement characters missing from the embedded font subset (the one real limitation — fixed by supplying the full real font). Running notes: `experiments/edit-pdf-experiments.md`.
