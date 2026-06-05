# CV — FastAPI + WeasyPrint

A FastAPI app serving a small hash-routed portfolio SPA (HomePage + CV page) plus a print-ready PDF, all from a single Jinja CV fragment, styled with Tailwind CSS v4 and generated via WeasyPrint v67.

---

## Routes

* `GET /` — SPA: HomePage at `/` (or `#/`), CV at `#/cv` (client-side hash routing, works on static hosts)
* `GET /cv.pdf` — the same CV fragment rendered to PDF (returned inline)
* `GET /health` — health check

---

## Stack

* **FastAPI[standard] ≥ 0.124.4** + **Jinja2** templates
* **WeasyPrint ≥ 67.0** for PDF generation
* **Tailwind CSS v4** via the standalone CLI binary (no Node required)
* **tinycss2** — used by the build script to post-process Tailwind's output for WeasyPrint compatibility (see *How the CSS pipeline works* below)
* **uv** for Python dependency management

---

## Local development

### 1. Prerequisites

[uv](https://docs.astral.sh/uv/):
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install

```
uv sync                            # Python deps
./scripts/install-tailwind.sh      # downloads Tailwind v4 binary into bin/tailwindcss
```

### 3. Run (two terminals)

```
# terminal 1 — build CSS on every template / source CSS change
./scripts/build-css.py --watch

# terminal 2 — FastAPI dev server
uv run fastapi dev app/main.py
```

* HomePage: http://localhost:8000/
* CV view: http://localhost:8000/#/cv
* PDF: http://localhost:8000/cv.pdf

---

## Project structure

```
app/main.py                  FastAPI app: GET / (SPA), GET /cv.pdf (WeasyPrint), GET /health
templates/
  base.html                  HTML scaffolding, loads /static/cv.css
  cv.html                    CV content fragment (hardcoded content, two-column layout)
  index.html                 SPA shell: home + CV sections, inline hash router (includes cv.html)
  cv_pdf.html                PDF wrapper: base.html + cv.html, rendered only for WeasyPrint
static/
  src/cv.css                 Tailwind entry (@import "tailwindcss" + @source + @import "./styles.css")
  src/styles.css             custom CSS (@font-face + @theme tokens + @layer components + @page / @media print)
  cv.css                     built output (loaded by the browser AND WeasyPrint)
scripts/
  install-tailwind.sh        downloads the platform's Tailwind v4 standalone binary
  build-css.py               runs Tailwind, then transforms output for WeasyPrint
bin/tailwindcss              standalone Tailwind binary (gitignored)
```

To change the CV: edit `templates/cv.html` (content) and `static/src/styles.css` (theme tokens, fonts, and components). The watcher rebuilds `static/cv.css` automatically.

---

## How the CSS pipeline works

Tailwind v4 uses several modern CSS features WeasyPrint 67 doesn't read (cascade layers, CSS nesting, `:root, :host` selector lists, `@property` initial values, `oklch()` colours). `scripts/build-css.py` runs the Tailwind CLI and then post-processes the output using tinycss2 to:

1. Unwrap every `@layer NAME { … }` block (so design tokens at `:root` are visible)
2. Hoist nested rules to top level, combining selectors and wrapping in their enclosing `@media` / `@supports`
3. Strip `:host` / `::file-selector-button` / `::backdrop` from selector lists (WeasyPrint drops the whole rule if any one is unparseable — that silently kills both Tailwind's `:root, :host` token block and the universal `*, ::after, ::before, ::backdrop` reset)
4. Convert each `@property` into a plain `:root { --name: <initial-value>; }`
5. Resolve every `oklch(L C H [/A])` literal to sRGB hex / `rgba()`
6. Replace `calc(infinity * 1px)` (what Tailwind emits for `rounded-full`) with `9999px` — WeasyPrint can't evaluate `infinity` and otherwise serializes the result as the literal text `nan` into the PDF content stream

Browsers see the same effective styles — they just don't need the transform. WeasyPrint reads the post-processed file directly.

---

## Production

### Docker

The `Dockerfile` is multi-stage:

* **builder** — installs Python deps via `uv`, downloads the Tailwind v4 standalone binary via `scripts/install-tailwind.sh`, and runs `scripts/build-css.py` to produce `static/cv.css`.
* **runtime** — `python:3.13-slim-bookworm` with WeasyPrint's native libs (Pango, Cairo, HarfBuzz, etc.), the venv, `app/`, `templates/`, and the built `static/cv.css`. Runs as a non-root `appuser` on port `8000`.

Build and run locally:
```
docker build -t cv-fastapi .
docker run --rm -p 8000:8000 cv-fastapi
```

Hit `http://localhost:8000/`, `/#/cv`, `/cv.pdf`, and `/health`.

`.dockerignore` excludes `.venv/`, `bin/`, `future/`, the prebuilt `static/cv.css`, etc., so the CSS is always built fresh inside the image.

### Coolify

Coolify deploys this repo from the `Dockerfile` directly — no compose file, no extra config:

1. Create a new resource → **Application**, point it at this Git repo.
2. **Build pack**: Dockerfile (auto-detected).
3. **Exposed port**: `8000`.
4. **Healthcheck**: picked up automatically from the `HEALTHCHECK` directive in the Dockerfile (`curl /health`).
5. Set a domain / Cloudflare proxy as you would for any Coolify app.

On every push, Coolify runs the same build that completes locally (`docker build .`), so the Tailwind binary download + CSS pipeline happens server-side. Nothing needs to be committed to ship — the only build artefact is `static/cv.css`, which is regenerated by the builder stage.

### GitHub Pages

The same CV is also published as a fully static bundle to GitHub Pages via the `.github/workflows/deploy-pages.yml` Actions workflow. On every push to `master` it runs the same Tailwind + WeasyPrint pipeline used locally and Coolify, then publishes `dist/` via `actions/deploy-pages`.

**One-time setup**: repo → Settings → Pages → Source = **GitHub Actions**.

After that, `git push origin master` does everything — the workflow builds (~1–2 min) and the site goes live at `https://<your-username>.github.io/<repo-name>/`.

Local preview of exactly what Pages will serve:

```
./scripts/build-static.py
python -m http.server -d dist 8765
```

The Coolify deploy and the Pages deploy are independent — pushing to `master` triggers both if both are configured; either can be disabled without affecting the other.

---

## Typography

Two self-hosted families from `static/fonts/`:

* [**IBM Plex Sans**](https://www.ibm.com/plex/) for body text — one variable `.woff2` covering weights 400–600 normal, one for italic (Latin subset).
* [**IBM Plex Mono**](https://www.ibm.com/plex/) for contact details, GitHub handle, and tech tags — three static `.woff2` files: regular 400, italic 400, semibold 600 (Latin subset). IBM Plex Mono is not variable on Google Fonts, so each weight/style ships separately. WeasyPrint won't synthesize italics, so the dedicated italic file is required for slanted text in the PDF.

Five `.woff2` files. Because the fonts ship with the app, PDFs are typographically identical whether they come out of `uv run fastapi dev` on macOS, the Coolify container, or the GitHub Pages CI build.

To swap or update, replace the files in `static/fonts/`. The current files came from Google Fonts — to refresh, fetch each CSS endpoint with a recent Chrome User-Agent and grab the latin-subset `.woff2` URL from the response:

* IBM Plex Sans: `https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400..600;1,400..600&display=swap`
* IBM Plex Mono: `https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,600;1,400&display=swap`

Both fonts are licensed under the [SIL Open Font License](https://opensource.org/licenses/OFL-1.1).

---

## License
MIT
