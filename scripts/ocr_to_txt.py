#!/usr/bin/env python3
"""Convert an image or PDF to plain text using VietOCR (Vietnamese OCR).

Usage:
    python ocr_to_txt.py <input.(png|jpg|...|pdf)> <output.txt> [--config vgg_transformer]
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
WEIGHTS_URL = "https://vocr.vn/data/vietocr/vgg_transformer.pth"
WEIGHTS_PATH = Path(__file__).resolve().parent.parent / "data" / "vgg_transformer.pth"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--config", default="vgg_transformer", help="VietOCR model config name")
    p.add_argument("--weights", default=str(WEIGHTS_PATH))
    p.add_argument("--device", default="cpu")
    p.add_argument("--max-pages", type=int, default=None, help="limit number of PDF pages (for testing)")
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2), help="parallel page workers")
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--engine", choices=("vision", "vietocr"), default="vision", help="OCR engine (vision = macOS Vision, fast)")
    p.add_argument("--merge", action="store_true", help="also write a merged single .txt when all pages are done")
    return p.parse_args()


def ensure_weights(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading pretrained weights to {path} ...", file=sys.stderr)
    import urllib.request

    urllib.request.urlretrieve(WEIGHTS_URL, path)


def get_predictor(config_name: str, weights: str, device: str):
    try:
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor
    except ImportError:
        sys.exit("vietocr not installed. Run: pip install vietocr pypdfium2 Pillow torch")
    config = Cfg.load_config_from_name(config_name)
    config["cnn"]["pretrained"] = False
    config["predictor"]["beamsearch"] = False
    config["weights"] = weights
    config["device"] = device
    return Predictor(config)


def ocr_image(predictor, img_path: Path) -> str:
    lines = segment_lines(img_path)
    texts = [ocr_line(predictor, line).strip() for line in lines]
    return "\n".join(t for t in texts if t)


def segment_lines(img_path: Path, min_height: int = 12) -> list[Image.Image]:
    """Crop horizontal text lines out of a page/photo using OpenCV."""
    img = cv2.imread(str(img_path))
    if img is None:
        return [Image.open(img_path).convert("RGB")]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (img.shape[1] // 30, 5))
    merged = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = sorted(
        (cv2.boundingRect(c) for c in contours), key=lambda b: (b[1], b[0])
    )
    lines = []
    for x, y, w, h in boxes:
        if h < min_height or w < img.shape[1] * 0.05:
            continue
        crop = img[max(y - 3, 0): y + h + 3, max(x - 3, 0): x + w + 3]
        lines.append(Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)))
    return lines or [Image.open(img_path).convert("RGB")]


def ocr_line(predictor, line: Image.Image) -> str:
    return predictor.predict(line.convert("RGB"))


def render_pdf_pages(pdf_path: Path, dpi: int = 200, max_pages: int | None = None, out_dir: Path | None = None):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        sys.exit("pypdfium2 not installed. Run: pip install pypdfium2")
    pdf = pdfium.PdfDocument(str(pdf_path))
    tmp = out_dir if out_dir is not None else Path(tempfile.mkdtemp(prefix="ocr_pdf_"))
    tmp.mkdir(parents=True, exist_ok=True)
    paths = []
    scale = dpi / 72
    n = min(len(pdf), max_pages or len(pdf))
    for i in range(n):
        p = tmp / f"page_{i + 1:04d}.png"
        if not p.exists():
            page = pdf[i]
            pil = page.render(scale=scale).to_pil()
            pil.save(p)
            print(f"rendered {p.name}", file=sys.stderr)
        paths.append(p)
    return paths


def ocr_with_vision(img_path: Path) -> str:
    from PIL import Image
    from Vision import VNRecognizeTextRequest, VNImageRequestHandler
    import Quartz

    url = Quartz.CFURLCreateWithFileSystemPath(
        None, str(img_path), Quartz.kCFURLPOSIXPathStyle, False
    )
    handler = VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    req = VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(0)  # accurate
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        sys.exit(f"Vision OCR failed: {err}")
    lines = [obs.topCandidates_(1)[0].string() for obs in (req.results() or [])]
    return "\n".join(lines)


_PREDICTOR = None


def _worker_init(config_name: str, weights: str, device: str, engine: str) -> None:
    global _PREDICTOR, _ENGINE
    _ENGINE = engine
    _PREDICTOR = get_predictor(config_name, weights, device) if engine == "vietocr" else None


def _ocr_one(img_path: str) -> str:
    if _ENGINE == "vision":
        return ocr_with_vision(Path(img_path))
    return ocr_image(_PREDICTOR, Path(img_path))


def _ocr_page_to_file(args) -> str:
    """OCR one rendered page image and write page_NNN.txt; skip if it exists."""
    img_path, out_path = args
    out_path = Path(out_path)
    if out_path.exists() and out_path.stat().st_size > 0:
        return f"{out_path.name}: skipped (already done)"
    text = _ocr_one(img_path)
    out_path.write_text(text.strip() + "\n", encoding="utf-8")
    return f"{out_path.name}: done ({len(text)} chars)"


def group_lines(text_blocks: list[str]) -> str:
    return "\n".join(t.strip() for t in text_blocks if t.strip())


def main() -> None:
    args = parse_args()
    src = Path(args.input)
    if not src.exists():
        sys.exit(f"input not found: {src}")

    if args.engine == "vietocr":
        ensure_weights(Path(args.weights))
    predictor = None
    if args.engine == "vietocr" and not (src.suffix.lower() == ".pdf" and args.workers > 1):
        predictor = get_predictor(args.config, args.weights, args.device)

    ext = src.suffix.lower()
    if ext == ".pdf":
        out_dir = Path(args.output)
        if out_dir.suffix.lower() == ".txt":
            out_dir = out_dir.with_suffix("")
        out_dir.mkdir(parents=True, exist_ok=True)
        page_imgs = render_pdf_pages(src, dpi=args.dpi, max_pages=args.max_pages, out_dir=out_dir / "_pages")
        jobs = [
            (str(img), str(out_dir / f"page_{i:03d}.txt"))
            for i, img in enumerate(page_imgs, 1)
        ]
        if args.workers > 1:
            import multiprocessing as mp

            with mp.Pool(args.workers, initializer=_worker_init, initargs=(args.config, args.weights, args.device, args.engine)) as pool:
                for msg in pool.imap_unordered(_ocr_page_to_file, jobs):
                    print(msg, file=sys.stderr)
        else:
            _worker_init(args.config, args.weights, args.device, args.engine)
            for job in jobs:
                print(_ocr_page_to_file(job), file=sys.stderr)

        done = sum(1 for _, p in jobs if Path(p).exists())
        print(f"pages done: {done}/{len(jobs)} in {out_dir}")
        if args.merge and done == len(jobs):
            merged = "\n\n".join(
                Path(p).read_text(encoding="utf-8").strip() for _, p in jobs
            )
            merged_path = out_dir.parent / f"{out_dir.name}.txt"
            merged_path.write_text(merged + "\n", encoding="utf-8")
            print(f"wrote merged {merged_path} ({len(merged)} chars)")
    elif ext in IMAGE_EXTS:
        text = ocr_with_vision(src) if args.engine == "vision" else ocr_image(predictor, src)
        out = Path(args.output)
        if out.suffix.lower() != ".txt":
            out = out.with_suffix(".txt")
        out.write_text(text.strip() + "\n", encoding="utf-8")
        print(f"wrote {out}")
    else:
        sys.exit(f"unsupported input type: {ext} (images: {sorted(IMAGE_EXTS)}, pdf)")


if __name__ == "__main__":
    main()
