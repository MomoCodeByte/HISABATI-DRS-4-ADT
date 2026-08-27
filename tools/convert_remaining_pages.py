from __future__ import annotations

import argparse
import html
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import pymupdf
except ImportError as exc:
    raise SystemExit("PyMuPDF is required. Add it to PYTHONPATH before running this converter.") from exc


SOURCE_WIDTH = 540.8980102539062
SOURCE_HEIGHT = 750.6610107421875
CONTENT_BOTTOM = 680.0
WATERMARK_WORDS = {"FOR", "ONLINE", "READING", "ONLY"}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def strip_svg_text(svg: str) -> str:
    root = ET.fromstring(svg)
    for parent in root.iter():
        for child in list(parent):
            if local_name(child.tag) == "text":
                parent.remove(child)
    root.set("aria-hidden", "true")
    root.set("focusable", "false")
    return ET.tostring(root, encoding="unicode")


def rgb_hex(value: int) -> str:
    return f"#{value & 0xFFFFFF:06x}"


def clean_font_name(name: str) -> str:
    lower = name.lower()
    if "arial" in lower or "nimbus" in lower or "helvetica" in lower:
        return "Arial"
    return "Arial"


def is_watermark(text: str, direction: tuple[float, float], color: int) -> bool:
    normalized = re.sub(r"[^A-Z]+", " ", text.upper()).strip()
    words = set(normalized.split())
    angled = abs(direction[1]) > 0.15
    salmon = ((color >> 16) & 255) > 180 and ((color >> 8) & 255) > 70
    return bool(words and words <= WATERMARK_WORDS and (angled or salmon)) or "FOR ONLINE READING ONLY" in normalized


def page_spans(page) -> list[str]:
    output: list[str] = []
    data = page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            direction = tuple(line.get("dir", (1.0, 0.0)))
            angle = math.degrees(math.atan2(-direction[1], direction[0]))
            for span in line.get("spans", []):
                text = span.get("text", "")
                if not text.strip():
                    continue
                x0, y0, x1, y1 = span["bbox"]
                if y0 < 18 or y0 >= CONTENT_BOTTOM:
                    continue
                color = int(span.get("color", 0))
                if is_watermark(text, direction, color):
                    continue
                size = float(span.get("size", 12.0))
                flags = int(span.get("flags", 0))
                family = clean_font_name(span.get("font", "Arial"))
                weight = 700 if flags & 16 else 400
                italic = "italic" if flags & 2 else "normal"
                transform = f"rotate({angle:.3f}deg)" if abs(angle) > 0.05 else "none"
                style = (
                    f"left:{x0:.3f}px;top:{y0:.3f}px;width:{max(x1-x0, 0.1):.3f}px;"
                    f"font-family:{family},sans-serif;font-size:{size:.3f}px;"
                    f"font-weight:{weight};font-style:{italic};color:{rgb_hex(color)};"
                    f"transform:{transform};"
                )
                output.append(f'<span class="pdf-span" style="{style}">{html.escape(text)}</span>')
    return output


def page_html(page_number: int, spans: list[str]) -> str:
    page_id = f"pg{page_number:03d}_sec001"
    title = f"Hisabati: Kitabu cha Mwanafunzi - Ukurasa wa wavuti {page_number}"
    background = f"./images/vector-pages/pg{page_number:03d}-background.svg"
    text_markup = "".join(spans)
    return f'''<!DOCTYPE html>
<html lang="sw-TZ"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><meta name="title-id" content="{page_id}"><meta name="page-section-id" content="{page_number}">
<link href="./content/tailwind_output.css" rel="stylesheet"><link href="./assets/libs/fontawesome/css/all.min.css" rel="stylesheet">
<link href="./assets/fonts.css" rel="stylesheet"><link href="./content/book-page-layouts.css" rel="stylesheet"><link href="./content/pdf-dom-pages.css" rel="stylesheet">
</head><body><main><div id="content" class="opacity-0"><section role="article" data-section-type="pdf_accessible_page" data-section-id="{page_id}" aria-label="Ukurasa wa wavuti {page_number}" class="book-page pdf-dom-page"><div class="page-narration-hook" data-id="pg{page_number:03d}_gp001_tx001"></div><div class="pdf-dom-canvas"><img class="pdf-dom-background" src="{background}" alt=""><div class="pdf-dom-text">{text_markup}</div></div></section></div></main>
<div class="relative z-50" id="interface-container"></div><div class="relative z-50" id="nav-container"></div>
<script src="./assets/offline-preloader.js?v=audiofix-20260824-1"></script><script src="./assets/scorm.js"></script><script src="./assets/book-runtime-fixes.js?v=layout-audio-20260827-1"></script><script src="./assets/base.bundle.local.js?v=audiofix-20260824-1"></script></body></html>'''


def convert(pdf_path: Path, output_dir: Path, start: int, end: int) -> None:
    vector_dir = output_dir / "images" / "vector-pages"
    vector_dir.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(pdf_path)
    end = min(end, len(document))
    for page_number in range(start, end + 1):
        page = document[page_number - 1]
        svg = strip_svg_text(page.get_svg_image(text_as_path=False))
        (vector_dir / f"pg{page_number:03d}-background.svg").write_text(svg, encoding="utf-8")
        markup = page_html(page_number, page_spans(page))
        (output_dir / f"pg{page_number:03d}_sec001.html").write_text(markup, encoding="utf-8")
        print(f"Converted page {page_number}/{end}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert remaining Hisabati PDF pages into vector-backed HTML text pages.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", type=int, default=41)
    parser.add_argument("--end", type=int, default=184)
    args = parser.parse_args()
    convert(args.pdf.resolve(), args.output.resolve(), args.start, args.end)


if __name__ == "__main__":
    main()
