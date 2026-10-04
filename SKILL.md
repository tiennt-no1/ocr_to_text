---
name: ocr-tool
description: Use when the user wants to convert a Vietnamese image or PDF into a txt file, or convert txt output into an epub ebook — e.g. "convert this image to txt", "OCR this scanned PDF", "extract Vietnamese text from a photo", "convert txt to epub", "make an ebook from these txt files". Uses VietOCR (VGG Transformer), a Vietnamese-specific OCR model.
---

# OCR Tool — Vietnamese Image/PDF → TXT (VietOCR)

OCR for Vietnamese text using [VietOCR](https://github.com/pbcquoc/vietocr)
(`vgg_transformer` pretrained model). Runs on CPU; GPU optional.

## Setup (once)

Python 3.9–3.11 recommended (torch wheels):

```bash
cd /Users/macos01/Desktop/ocr_tool
pip install uv
uv venv .ocr --python 3.11
uv pip install --python .ocr/bin/python -r requirements.txt
```

Pretrained weights (~300MB) auto-download to `data/vgg_transformer.pth` on
first run.

## Usage

```bash
.ocr/bin/python scripts/ocr_to_txt.py <input> <output.txt>
```

Examples:

```bash
.ocr/bin/python scripts/ocr_to_txt.py photo.jpg photo.txt
.ocr/bin/python scripts/ocr_to_txt.py scan.pdf scan.txt
```

Options:

- `--device cpu|cuda` — default `cpu`
- `--engine vision|vietocr` — default `vision` (fast); `vietocr` = the VietOCR model
- `--weights PATH` — custom pretrained weights
- `--config NAME` — VietOCR model name (default `vgg_transformer`)

## TXT → EPUB (ebook)

Convert the OCR `.txt` output into a `.epub` readable on ebook devices
(Kindle, Apple Books, Kobo, ...). No extra dependencies — uses only the
Python stdlib.

```bash
.ocr/bin/python scripts/txt_to_epub.py <txt files or dirs...> -o book.epub --title "Title" --author "Author"
```

Examples:

```bash
# each page_NNN.txt becomes one chapter
.ocr/bin/python scripts/txt_to_epub.py exports/test_vision2 -o book.epub --title "Thinking in Bets"

# one merged txt, split on "Chương/Chapter/Phần/Hồi/..." headings
.ocr/bin/python scripts/txt_to_epub.py book.txt -o book.epub --split-chapters
```

Options: `--language` (default `vi`), `--author`, `--split-chapters`.
Produces a valid EPUB 3 with an EPUB 2 NCX fallback.

Paragraph handling: OCR output is one wrapped line per source line with no
blank lines, so `txt_to_epub.py` merges wrapped lines into logical
paragraphs (new paragraph when the previous line ended a sentence early on
the page). Mid-paragraph page breaks are re-joined automatically.

## Important caveat

VietOCR is a **line-level** recognizer: `predict()` works best on cropped
lines of text. For full-page scans you should add text detection / line
segmentation first (e.g. CRAFT, PaddleOCR detection, or OpenCV line
projection) and feed each cropped line to the predictor. The current script
passes whole pages/images directly, which works for single-line images and
simple cases — extend it with a detector for document pages.

## Notes

- Images: png, jpg, jpeg, webp, bmp, tiff. PDFs are rendered at 200 dpi.
- Output is UTF-8 `.txt`; Vietnamese diacritics preserved.
