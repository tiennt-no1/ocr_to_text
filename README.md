# ocr_tool

AI skill that converts Vietnamese images and PDFs to `.txt` using **VietOCR**
(VGG Transformer — a Vietnamese-specific OCR model).

## Layout

```
SKILL.md                 # skill definition (name, description, usage)
scripts/ocr_to_txt.py    # image/pdf -> txt via VietOCR
data/                    # pretrained weights (auto-downloaded)
references/              # extra notes / prompts (optional)
```

## 1. Setup (run once)

```bash
cd /Users/macos01/Desktop/ocr_tool
pip install uv
uv venv .ocr --python 3.11
uv pip install --python .ocr/bin/python -r requirements.txt
```

## 2. Run a conversion

```bash
cd /Users/macos01/Desktop/ocr_tool
.ocr/bin/python scripts/ocr_to_txt.py <input> <output.txt>
```

Examples:

```bash
.ocr/bin/python scripts/ocr_to_txt.py photo.jpg photo.txt
.ocr/bin/python scripts/ocr_to_txt.py scan.pdf scan.txt
.ocr/bin/python scripts/ocr_to_txt.py scan.pdf scan.txt --device cuda
```

Supported inputs: `png, jpg, jpeg, webp, bmp, tiff, pdf`.
Pretrained weights download automatically to `data/vgg_transformer.pth` on
first run (only needed with `--engine vietocr`).

- `--engine vision` (default): macOS Vision OCR — fast (~3s/page), good
  Vietnamese support.
- `--engine vietocr`: VieOCR model — slower (~30s/page), line-level model.

## 3. Use it as an opencode skill

```bash
ln -s /Users/macos01/Desktop/ocr_tool ~/.config/opencode/skills/ocr-tool
```

Then in opencode you can just say e.g. "convert this image to txt".

## Notes

- VietOCR recognizes text **line by line**. For full document pages, add a
  line segmentation step (CRAFT / PaddleOCR detection / OpenCV) and feed
  cropped lines to the predictor — see SKILL.md.
- Output is UTF-8 with Vietnamese diacritics preserved.
