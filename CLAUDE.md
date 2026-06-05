# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Personal CV/portfolio site: a FastAPI app serving a small hash-routed SPA (home + CV) plus a print-ready PDF, all rendered from a single Jinja CV fragment. Tailwind CSS v4 via the standalone CLI (no Node), WeasyPrint for the PDF, Python 3.13 managed with uv. There is no test suite and no linter.

## Commands

```bash
uv sync                          # install Python deps
./scripts/install-tailwind.sh    # one-time: download Tailwind binary into bin/

./scripts/build-css.py --watch   # terminal 1: rebuild static/cv.css on template/CSS changes
uv run fastapi dev app/main.py   # terminal 2: dev server at http://localhost:8000

./scripts/build-static.py            # build dist/ (the static bundle GitHub Pages serves)
python -m http.server -d dist 8765   # preview dist/

docker build -t cv-fastapi . && docker run --rm -p 8000:8000 cv-fastapi
```

After CV changes, verify both `/#/cv` (browser) and `/cv.pdf` (WeasyPrint): the engines differ, and a change can look right in one and broken in the other.

## Architecture

One content fragment, three outputs:

- `templates/cv.html` is the CV: a Jinja fragment (it also defines the SVG icon macros that `index.html` imports) included by both
  - `templates/index.html`: SPA shell with an inline hash router (home at `#/`, CV at `#/cv`), served at `GET /`, and
  - `templates/cv_pdf.html`: thin wrapper rendered only for WeasyPrint (`GET /cv.pdf`). The PDF's first page is also rasterized into the home thumbnail (`GET /cv-preview.png`, `app/pdf_preview.py`).
- `index.html` and `cv_pdf.html` both extend `templates/base.html`, the scaffold that links `static/cv.css`. Browser and WeasyPrint load that same built stylesheet.

Three deploy targets run this same pipeline: local dev, Docker/Coolify (multi-stage `Dockerfile`), and GitHub Pages (`.github/workflows/deploy-pages.yml` rebuilds `dist/` on every push to master; `dist/` is gitignored).

### CSS pipeline

`static/cv.css` is generated; never edit it directly. Sources: `static/src/cv.css` (Tailwind entry) and `static/src/styles.css` (fonts, `@theme` design tokens, `@layer components`, print rules). `scripts/build-css.py` runs the Tailwind CLI, then post-processes the output with tinycss2 because WeasyPrint 67 cannot read much of what Tailwind v4 emits (cascade layers, CSS nesting, `oklch()`, `@property`, logical properties, and more). The transforms are documented in the script itself (docstring plus inline comments).

The generated `static/cv.css` is committed. After any template or `static/src/` change, rerun `./scripts/build-css.py` and include the rebuilt file in the commit, or the committed copy goes stale (Docker and CI rebuild it fresh, so only local serving and the git history drift).

WeasyPrint workarounds already encoded in the templates and CSS; preserve them when editing:

- SVG icon fills are inline `style` attributes (WeasyPrint ignores class CSS for SVG fill). The default fill `#71717a` must stay in sync with `--color-cv-muted`.
- `@font-face` declares single weights only (WeasyPrint rejects range descriptors like `font-weight: 400 600`): IBM Plex Sans points its 400 and 600 faces at the one variable file; IBM Plex Mono ships a static file per face.
- List bullets are `::before` boxes, not native `disc` markers (the engines paint those differently).
- `_static_url_fetcher` in `app/main.py` reroutes `/static/...` URLs to disk for WeasyPrint.

## Content rules

- The three `.cv-page` articles in `cv.html` are fixed print pages. Never reflow content across them: WeasyPrint pagination cannot be predicted from text length.
- `future/final_cv.md` is a markdown mirror of `cv.html` maintained by the `cv-sync` skill (`.claude/skills/cv-sync/SKILL.md`); run it after editing CV content. The app never reads the mirror. Never edit `dist/` or `future/original_cv.md`.
- The profile paragraph is deliberately duplicated in `cv.html` and `index.html` (both sides carry a "Keep in sync" comment); edit both. Apart from that, each piece of content lives in exactly one place: reuse authored text verbatim when restructuring, don't reword it in passing.
- The PDF filename lives in `app/__init__.py` (`PDF_FILENAME`); it is app config, not CV content.

## Conventions

- Colors: zinc is the gray family. Never `bg-white`, `text-white`, `text-black`, `#fff`, or `#000`; use `zinc-50`/`zinc-900` and the `cv-*` tokens. Accents: teal for labels, tags, and bullet markers (applied via Tailwind `teal-*` utilities; the teal `--color-cv-primary` token is defined but intentionally unused) and rose for links (the `--color-cv-link` token). The `cv-*` tokens live in `@theme` in `static/src/styles.css`.
- Tech naming on homepage project cards: product names ("LÖVE", not "Love2D"), full API names ("Web Audio API"), no build tooling in the tag line; the audio plugin cards use "C++ · JUCE". The CV page keeps "Love2D" as is.
- In new prose, avoid the em dash; use commas, colons, or parentheses. Existing "Role — Company" headers and ` · ` separators are established formats and stay.

## Gotchas

- `/cv-preview.png` is cached in-process after the first render; in dev the thumbnail goes stale after CV edits until the server restarts.
- WeasyPrint drops anything it cannot parse silently (the whole rule, no error). If a style disappears from the PDF only, suspect a missing transform in `scripts/build-css.py`.
