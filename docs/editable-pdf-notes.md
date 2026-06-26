# Editable PDF Notes

This project currently produces searchable PDFs. Fully editable PDFs are a separate export target.

## Searchable PDF

A searchable PDF keeps the scanned page image as the visible page. The OCR engine supplies text and word boxes, then OCRmyPDF writes an invisible text layer over the image.

That gives:

- search
- copy/paste
- text selection if boxes align well
- a stable visual match to the scanned source

The visible page text remains part of the scanned image, so click-to-edit text requires another pipeline.

## Editable PDF

An editable PDF needs visible PDF text objects. For scanned input, that means the pipeline has to recreate the page instead of only overlaying a hidden text layer.

The extra work is a visible-page reconstruction problem: detect layout regions, lines, and words; recognize the text; infer fonts, sizes, style, baselines, spacing, and writing direction; remove, cover, or redraw the original scanned text area; insert visible PDF text objects in the same place; preserve images, tables, diagrams, and page geometry; then QA the result because small font and spacing errors become visible.

## Practical Path

There are two realistic export targets:

1. Best-effort editable PDF

   Use the current word boxes and layout sidecars, write visible text with PyMuPDF, and cover the original scan text where needed. This can work for simple pages but will be visually fragile because font matching and background cleanup are hard.

1. Editable document export

   Use OCR/layout output to produce DOCX, HTML, or Markdown, then regenerate a PDF from that editable document. This gives genuinely editable text but sacrifices exact scan fidelity.

For this repo, the better next step is to keep searchable PDF as the primary product and add an explicit editable export command later. That command should use RapidOCR/Paddle word boxes for anchors, Surya or another layout engine for structure, and Mistral or reconciled words as canonical text.
