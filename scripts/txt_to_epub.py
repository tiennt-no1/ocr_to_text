#!/usr/bin/env python3
"""Convert a list of .txt files into a single .epub ebook.

Usage:
    python txt_to_epub.py <input...> <output.epub> [--title TITLE] [--author AUTHOR]

Inputs can be:
  - one or more .txt files (each becomes a chapter), or
  - directories containing .txt files (chapters sorted naturally), or
  - a single merged .txt plus --split-chapters to split on headings.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

CSS = """
body { font-family: serif; line-height: 1.5; margin: 5%; }
h1 { text-align: center; font-size: 1.4em; margin-bottom: 1em; }
p { text-indent: 1.5em; margin: 0 0 0.5em 0; text-align: justify; }
"""


def natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def collect_txts(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for inp in inputs:
        p = Path(inp)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.txt"), key=natural_key))
        elif p.is_file() and p.suffix.lower() == ".txt":
            files.append(p)
        else:
            sys.exit(f"not a .txt file or directory: {p}")
    if not files:
        sys.exit("no .txt files found")
    return sorted(files, key=natural_key)


_SENT_END = tuple('.!?:;…"”\')»]')


def merge_lines(lines: list[str]) -> list[str]:
    """Merge wrapped OCR lines into logical paragraphs.

    A break starts a new paragraph when the previous line ended the
    paragraph early (short line) or it ended a sentence and the next line
    begins with a capital letter. Blank lines keep a hard break unless the
    text clearly continues mid-sentence (e.g. a page turn).
    """
    nonblank = [l for l in lines if l.strip()]
    if not nonblank:
        return []
    lens = sorted(len(l.strip()) for l in nonblank)
    median = lens[len(lens) // 2] or 1
    short = 0.65 * median

    paras: list[list[str]] = [[]]
    prev = ""
    prev_blank = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            prev_blank = True
            continue
        is_upper = stripped[0].isupper()
        prev_ended = prev.rstrip().endswith(_SENT_END)
        new_para = False
        if prev:
            if prev_blank:
                # hard break, but keep the paragraph open when the text
                # clearly continues mid-sentence (page turn, etc.)
                new_para = prev_ended or is_upper
            else:
                new_para = prev_ended and (
                    len(prev) <= short or (len(prev) <= median and is_upper)
                )
        if new_para:
            paras.append([])
        paras[-1].append(stripped)
        prev = stripped
        prev_blank = False
    return [" ".join(p) for p in paras if p]


def paragraphs(text: str) -> str:
    out = []
    for para in merge_lines(text.strip().splitlines()):
        out.append(f"    <p>{html.escape(para)}</p>")
        out.append("")
    return "\n".join(out)


def chapter_title(path: Path, text: str) -> str:
    for line in text.strip().splitlines():
        line = line.strip().strip("#").strip()
        if line:
            return line[:80]
    return path.stem


def split_chapters(text: str) -> list[tuple[str, str]]:
    """Split a big text into (title, body) chapters on heading-like lines."""
    lines = text.splitlines()
    chapters = []
    title, buf = "Chapter 1", []
    heading = re.compile(r"^\s*(chương|chapter|phần|part|hồi|bài)\b", re.I)
    for line in lines:
        if heading.match(line) and buf:
            chapters.append((title, "\n".join(buf)))
            title, buf = line.strip(), []
        else:
            if heading.match(line):
                title = line.strip()
            buf.append(line)
    chapters.append((title, "\n".join(buf)))
    return [(t, b.strip()) for t, b in chapters if b.strip()]


def build_epub(chapters: list[tuple[str, str, str]], out: Path, title: str, author: str, language: str) -> None:
    """chapters: list of (chapter_id, title, body_text)."""
    book_id = str(uuid.uuid4())
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

    manifest_items = [
        '<item id="css" href="style.css" media-type="text/css"/>',
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
    ]
    spine_items = []
    nav_links = []
    ncx_points = []
    chapter_files = []

    for i, (cid, ctitle, body) in enumerate(chapters, 1):
        fname = f"chapter_{i:03d}.xhtml"
        chapter_files.append((fname, ctitle, body))
        manifest_items.append(f'<item id="{cid}" href="{fname}" media-type="application/xhtml+xml"/>')
        spine_items.append(f'<itemref idref="{cid}"/>')
        nav_links.append(f'      <li><a href="{fname}">{html.escape(ctitle)}</a></li>')
        ncx_points.append(
            f'    <navPoint id="navPoint-{i}" playOrder="{i}">\n'
            f'      <navLabel><text>{html.escape(ctitle)}</text></navLabel>\n'
            f'      <content src="{fname}"/>\n'
            f'    </navPoint>'
        )

    content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:{book_id}</dc:identifier>
    <dc:title>{html.escape(title)}</dc:title>
    <dc:creator>{html.escape(author)}</dc:creator>
    <dc:language>{language}</dc:language>
    <meta property="dcterms:modified">{modified}</meta>
  </metadata>
  <manifest>
    {chr(10).join('    ' + m for m in manifest_items)}
  </manifest>
  <spine toc="ncx">
    {chr(10).join('    ' + s for s in spine_items)}
  </spine>
</package>
"""

    nav_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>{html.escape(title)}</title><link rel="stylesheet" href="style.css"/></head>
<body>
  <nav epub:type="toc">
    <h1>Mục lục</h1>
    <ol>
{chr(10).join(nav_links)}
    </ol>
  </nav>
</body>
</html>
"""

    toc_ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:{book_id}"/></head>
  <docTitle><text>{html.escape(title)}</text></docTitle>
  <navMap>
{chr(10).join(ncx_points)}
  </navMap>
</ncx>
"""

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w") as z:
        # mimetype must be first and uncompressed
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container_xml)
        z.writestr("OEBPS/content.opf", content_opf)
        z.writestr("OEBPS/style.css", CSS)
        z.writestr("OEBPS/nav.xhtml", nav_xhtml)
        z.writestr("OEBPS/toc.ncx", toc_ncx)
        for fname, ctitle, body in chapter_files:
            chapter = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{html.escape(ctitle)}</title><link rel="stylesheet" href="style.css"/></head>
<body>
  <h1>{html.escape(ctitle)}</h1>
{paragraphs(body)}
</body>
</html>
"""
            z.writestr(f"OEBPS/{fname}", chapter)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("inputs", nargs="+", help=".txt files and/or directories")
    p.add_argument("-o", "--output", required=True, help="output .epub path")
    p.add_argument("--title", default=None)
    p.add_argument("--author", default="Unknown")
    p.add_argument("--language", default="vi")
    p.add_argument("--split-chapters", action="store_true",
                   help="treat each input .txt as one book body, split on Chương/Chapter/Part headings")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out = Path(args.output)
    if out.suffix.lower() != ".epub":
        out = out.with_suffix(".epub")

    chapters: list[tuple[str, str, str]] = []
    if args.split_chapters:
        files = collect_txts(args.inputs)
        for f in files:
            for i, (t, b) in enumerate(split_chapters(f.read_text(encoding="utf-8")), 1):
                chapters.append((f"ch{len(chapters)+1}", t, b))
    else:
        for i, f in enumerate(collect_txts(args.inputs), 1):
            text = f.read_text(encoding="utf-8")
            chapters.append((f"ch{i}", chapter_title(f, text), text))

    title = args.title or (Path(args.inputs[0]).stem if len(args.inputs) == 1 else "Ebook")
    build_epub(chapters, out, title, args.author, args.language)
    print(f"wrote {out} ({len(chapters)} chapters, {out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
