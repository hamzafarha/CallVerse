"""Build docs/CallVerse_Technical_Guide.pdf from guide.html and the screenshots in img/.

    python docs/guide/build_guide.py

Tall screenshots are split at blank rows (the gaps between cards) so that every
piece fits on an A4 page; `<!--FIG name "caption"-->` markers in guide.html are
replaced by the figures; Microsoft Edge (or Chrome) prints the result to PDF.
Screenshots are captured from the running apps (front office :5173, back office :5174).
"""

import html
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
PDF = HERE.parent / "CallVerse_Technical_Guide.pdf"
MAX_HEIGHT = 1500  # px of a 1440-px-wide screenshot that fit on one A4 page with a caption
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "msedge",
    "google-chrome",
]


def cut_rows(image: Image.Image) -> list[int]:
    """Row indexes where to cut: the most uniform row in the lower part of each window."""
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    spread = gray.std(axis=1)
    cuts, top = [], 0
    while gray.shape[0] - top > MAX_HEIGHT:
        window = spread[top + MAX_HEIGHT - 500 : top + MAX_HEIGHT]
        calm = np.flatnonzero(window <= window.min() + 0.5)
        cut = top + MAX_HEIGHT - 500 + int(calm[-1] if len(calm) else window.argmin())
        cuts.append(cut)
        top = cut
    return cuts


def split(name: str) -> list[str]:
    """Pieces of one screenshot (file names in build/img)."""
    image = Image.open(HERE / "img" / f"{name}.png").convert("RGB")
    bounds = [0, *cut_rows(image), image.height]
    names = []
    for index, (start, end) in enumerate(zip(bounds, bounds[1:]), start=1):
        piece = f"{name}_{index}.png" if len(bounds) > 2 else f"{name}.png"
        image.crop((0, start, image.width, end)).save(BUILD / "img" / piece, optimize=True)
        names.append(piece)
    return names


def figure_html(match: re.Match) -> str:
    name, caption = match.group(1), match.group(2)
    pieces = split(name)
    blocks = []
    for index, piece in enumerate(pieces, start=1):
        part = f" (part {index}/{len(pieces)})" if len(pieces) > 1 else ""
        blocks.append(
            f'<figure><img src="img/{piece}" alt="{html.escape(name)}">'
            f"<figcaption>{html.escape(caption)}{part}</figcaption></figure>"
        )
    return "\n".join(blocks)


def main() -> None:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    (BUILD / "img").mkdir(parents=True)
    source = (HERE / "guide.html").read_text(encoding="utf-8")
    built = re.sub(r'<!--FIG (\w+) "([^"]*)"-->', figure_html, source)
    page = BUILD / "guide.html"
    page.write_text(built, encoding="utf-8")
    browser = next(b for b in BROWSERS if shutil.which(b) or Path(b).exists())
    subprocess.run(
        [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--virtual-time-budget=15000",
            f"--print-to-pdf={PDF}",
            page.as_uri(),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    print(f"{PDF} ({PDF.stat().st_size / 2**20:.1f} MB)")


if __name__ == "__main__":
    main()
