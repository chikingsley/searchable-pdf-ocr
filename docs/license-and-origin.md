# License and Origin

This repo is still derived from the original `ocrmypdf-paddleocr` fork.

Current evidence:

- The GitHub repository is a fork of `clefru/ocrmypdf-paddleocr`.
- Local Git history still includes the original plugin lineage, including the initial commit by Clemens Fruhwirth.
- The active plugin code has been heavily renamed and refactored, while the current codebase still carries that implementation lineage.

## What MPL-2.0 Means Here

MPL-2.0 is the Mozilla Public License 2.0. It is a weak copyleft license at the source-file level.

Practical impact:

- You can use, modify, and distribute the project.
- You can use it commercially.
- You can combine MPL-covered files with differently licensed code in a larger project.
- If you distribute modified MPL-covered source files, keep those files and modifications available under MPL-2.0.
- Keep the MPL license text and notices with source distributions.

Unlike GPL in the broad project-wide sense, MPL keeps the copyleft boundary at covered source files and their modifications. Separate files and larger applications around this repo can keep their own license.

## Can This Be Changed To MIT?

Changing this project to MIT requires relicensing rights from every relevant copyright holder or a clean-room rewrite that removes the inherited MPL-covered implementation.

New files can be MIT in a mixed-license project if we explicitly mark them that way. The inherited plugin-derived files remain MPL-covered, so the conservative project-level license stays MPL-2.0 until there is a clean-room rewrite or relicensing permission.

## Current Repo State

The local project and GitHub fork are named `searchable-pdf-ocr`.

The project remains a searchable-PDF creator built around OCRmyPDF's PDF writer, local word-box OCR backends, review sidecars, and optional text reconciliation.
