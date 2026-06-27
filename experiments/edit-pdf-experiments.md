# Edit PDF — Experiments Log

Running log for the digital-PDF editing lane (Acrobat "Edit PDF" analog). Newest at the bottom.

See `README.md` for what this lane is vs `clearscan/`.

## State of play

Digital PDFs already carry real text + embedded fonts, so editing them needs neither OCR nor glyph reconstruction. We extract the embedded font and re-typeset edited text in it. Two known limitations: (1) embedded fonts are **subsetted** (only used glyphs present), so a brand-new character may be missing — fixed by supplying the full real font; (2) **reflow** — changing text length shifts following text (same-length / single-field edits are trivial; paragraph reflow is the harder Acrobat-grade case).

## 2026-06-26 — Classification: resume and FBI docs are both digital

- `Chibuzor Ejimofor - Resume.pdf`: text_chars=2959, 8 embedded fonts (FranklinGothic Book/Demi/BookItalic + ArialMT/SymbolMT), 0 images -> digital.
- `fbi-criminial-background-check-{2022,2026}.pdf`: text_chars=1667, 8–9 fonts, 3 images -> digital (real text + embedded fonts + seal images). Same easy category as the resume, NOT a scan. (Not being edited; classification only.)

So both belong in this lane, not `clearscan/`. The scan lane is only for true image-only pages like the FSI typewriter front matter.

## 2026-06-26 — Experiment 1: native-looking edit on the resume

Built `tools/edit_pdf.py` (`classify` + `edit`). `edit` finds the text, extracts the matching embedded font (preferring the subset that covers the replacement chars), redacts the old text, and re-inserts the replacement at the same baseline/size/color.

```bash
uv run editpdf/tools/edit_pdf.py edit \
  "<jobkit>/archive/old-resumes/Chibuzor Ejimofor - Resume.pdf" \
  editpdf/artifacts/resume-edited.pdf --find 'May 2018' --replace 'May 2019' --page 1
```

Result: changed the graduation date `May 2018` -> `May 2019` in `FranklinGothic-Book` @ 10pt. No missing-glyph warning (`9` was in the subset). Full-page diff: only **1059 px** changed, confined to x494–536 y139–148 pt — exactly the date, nothing else moved. Rendered crop (`artifacts/edu-after.png`) is indistinguishable from native: the new `9` matches the typeface because it is the document's own font.

This is the Acrobat "Edit PDF" experience on a real file, and it confirms the meta: for digital PDFs the font is handed to us — no invention, no image-based font ID.

Next options: (1) multi-edit + longer/shorter replacements with reflow of following text; (2) full-real-font fallback for characters missing from a subset; (3) a "show all editable text boxes" pass (the Acrobat bounding-box overlay) to make it feel like editing a Word doc.
