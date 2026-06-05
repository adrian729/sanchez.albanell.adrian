#!/usr/bin/env -S uv run --quiet python3
"""Assemble dist/ — a self-contained static bundle of the CV that can be
served by any static host (GitHub Pages, S3, a plain `python -m http.server`).

What ends up in dist/:
  index.html         — rendered index.html (SPA shell: home + CV behind hash routes)
  cv.pdf             — PDF generated via WeasyPrint from cv_pdf.html (filename matches the <a href>)
  static/cv.css      — built Tailwind output (post-processed for WeasyPrint compat)
  static/photo.jpg   — copied as-is
  static/fonts/*     — IBM Plex Sans + IBM Plex Mono .woff2 files, copied as-is
  .nojekyll          — opt out of Jekyll on GitHub Pages

Usage:
  scripts/build-static.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

import jinja2
from weasyprint import CSS, HTML

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"

sys.path.insert(0, str(ROOT))
from app import PDF_FILENAME  # noqa: E402


def main() -> None:
    shutil.rmtree(DIST, ignore_errors=True)
    (DIST / "static").mkdir(parents=True)

    subprocess.run([str(ROOT / "scripts" / "build-css.py")], check=True, cwd=ROOT)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATES),
        autoescape=jinja2.select_autoescape(["html"]),
    )
    html = env.get_template("index.html").render(pdf_filename=PDF_FILENAME)
    (DIST / "index.html").write_text(html, encoding="utf-8")

    pdf_html = env.get_template("cv_pdf.html").render(pdf_filename=PDF_FILENAME)
    # base_url needs a trailing slash so urljoin keeps the cwd path segment
    # when resolving relative asset URLs like "static/photo.jpg".
    pdf_bytes = HTML(string=pdf_html, base_url=ROOT.as_uri() + "/").write_pdf(
        stylesheets=[CSS(str(STATIC / "cv.css"))]
    )
    (DIST / "cv.pdf").write_bytes(pdf_bytes)

    shutil.copy(STATIC / "cv.css", DIST / "static" / "cv.css")
    shutil.copy(STATIC / "photo.jpg", DIST / "static" / "photo.jpg")
    shutil.copytree(STATIC / "fonts", DIST / "static" / "fonts")

    (DIST / ".nojekyll").touch()

    print(f"built {DIST.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
