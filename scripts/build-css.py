#!/usr/bin/env -S uv run --quiet python3
"""Build static/cv.css via the Tailwind standalone CLI, then transform the
output for WeasyPrint compatibility.

WeasyPrint 67 doesn't handle several modern CSS features that Tailwind v4
emits heavily, so each Tailwind rebuild gets run through `transform_for_weasyprint`:

  1. Cascade layers (`@layer theme { :root {...} }`) — WeasyPrint doesn't propagate
     custom properties across layers. The transform unwraps every `@layer NAME { ... }`
     block so rules sit at the top level.

  2. CSS nesting (`.cv-download-btn { ...; @media print { display: none; } }`) —
     WeasyPrint silently ignores nested at-rules and selector rules. The transform
     hoists nested rules to the top level, combining selectors (and `&`) and
     wrapping declarations in their enclosing `@media` / `@supports`.

  3. Unsupported selectors (`:host`, `::file-selector-button`, `::backdrop`) —
     WeasyPrint drops the entire selector list if it can't parse any selector in
     it. Two practical consequences: (a) Tailwind v4's `:root, :host { ... }`
     token block silently disappears, taking every design token variable with
     it; (b) the preflight reset `*, ::after, ::before, ::backdrop { margin: 0;
     padding: 0; ... }` is discarded entirely, so every element falls back to
     UA defaults (body 8px margin, ul 40px padding-left, etc.) and the PDF
     layout drifts from the on-screen view. The transform drops the offending
     selectors from each list; rules with no remaining selectors are removed.

  4. `@property` declarations (`@property --tw-border-style { initial-value: solid }`)
     register custom properties with default values. WeasyPrint doesn't honor
     @property, so utilities like `.border-b` (`border-style: var(--tw-border-style)`)
     resolve to no value → no border. The transform converts each `@property` into
     a plain `:root { --name: <initial-value>; }` rule.

  5. `oklch()` colors. Tailwind v4's default palette (every `bg-blue-500`,
     `text-red-700`, etc., plus `--color-stone-100`) is emitted in oklch.
     WeasyPrint can't parse it, so those properties silently drop. The transform
     pre-resolves each oklch(L C H[/A]) literal to an equivalent sRGB hex /
     rgba() value before tinycss2 sees the CSS.

  6. `calc(infinity * 1px)` — Tailwind v4 emits this for `rounded-full` so the
     pill shape works at any height. WeasyPrint can't evaluate `infinity` and
     serializes the result as the literal text `nan` into the PDF content
     stream, breaking downstream PDF tooling. The transform substitutes a
     finite large value (9999px) before tinycss2 sees the CSS.

The transform uses tinycss2 (already a WeasyPrint dependency), so it's robust to
new utility class combinations the user adds — every Tailwind v4 build goes
through the same pipeline. Browsers are unaffected: they see the same end result.

Usage:
  scripts/build-css.py            # one-shot build
  scripts/build-css.py --watch    # rebuild on template / source CSS changes
"""
import re
import subprocess
import sys
import time
from pathlib import Path

import tinycss2
from tinycss2 import serialize

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "static" / "src" / "cv.css"
TARGET = ROOT / "static" / "cv.css"
TEMPLATE_DIR = ROOT / "templates"
TAILWIND = ROOT / "bin" / "tailwindcss"

UNSUPPORTED_PSEUDO_RE = re.compile(
    r":host(?:\([^)]*\))?|::file-selector-button|::backdrop"
)

OKLCH_RE = re.compile(
    r"oklch\(\s*([\d.]+%?)\s+([\d.]+)\s+([\d.-]+)(?:deg)?(?:\s*/\s*([\d.]+%?))?\s*\)"
)

INFINITY_CALC_RE = re.compile(r"calc\(\s*infinity\s*\*\s*1px\s*\)")


def transform_for_weasyprint(css: str) -> str:
    css = _replace_oklch(css)
    css = INFINITY_CALC_RE.sub("9999px", css)
    rules = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)
    out: list[str] = []
    _process(out, rules, selector_chain=None, media_chain=None, supports_chain=None)
    return "\n".join(out)


def _replace_oklch(css: str) -> str:
    return OKLCH_RE.sub(_oklch_match_to_color, css)


def _oklch_match_to_color(m: re.Match) -> str:
    l_str, c_str, h_str, a_str = m.groups()
    L = float(l_str[:-1]) / 100 if l_str.endswith("%") else float(l_str)
    C = float(c_str)
    H = float(h_str)
    r, g, b = _oklch_to_srgb(L, C, H)
    if a_str is None:
        return f"#{r:02x}{g:02x}{b:02x}"
    A = float(a_str[:-1]) / 100 if a_str.endswith("%") else float(a_str)
    return f"rgba({r}, {g}, {b}, {A:g})"


def _oklch_to_srgb(L: float, C: float, H: float) -> tuple[int, int, int]:
    import math

    h_rad = math.radians(H)
    a = C * math.cos(h_rad)
    b = C * math.sin(h_rad)

    # OKLab → LMS' (cube root space), then cube to LMS
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    L_, M_, S_ = l_**3, m_**3, s_**3

    # LMS → linear sRGB
    r_lin = +4.0767416621 * L_ - 3.3077115913 * M_ + 0.2309699292 * S_
    g_lin = -1.2684380046 * L_ + 2.6097574011 * M_ - 0.3413193965 * S_
    b_lin = -0.0041960863 * L_ - 0.7034186147 * M_ + 1.7076147010 * S_

    def to_srgb(x: float) -> int:
        x = max(0.0, min(1.0, x))
        if x <= 0.0031308:
            s = 12.92 * x
        else:
            s = 1.055 * (x ** (1 / 2.4)) - 0.055
        return round(max(0.0, min(1.0, s)) * 255)

    return to_srgb(r_lin), to_srgb(g_lin), to_srgb(b_lin)


def _process(
    out: list[str],
    items: list,
    selector_chain: list[str] | None,
    media_chain: str | None,
    supports_chain: str | None,
) -> None:
    """Walk a list of CSS items. Direct declarations get attributed to the current
    selector chain (wrapped in current @media/@supports). Nested rules update the
    chain and recurse."""
    pending_decls: list = []

    def flush_decls() -> None:
        if pending_decls and selector_chain:
            decls_text = " ".join(_serialize_declaration(d) for d in pending_decls)
            rule_text = f"{', '.join(selector_chain)} {{ {decls_text} }}"
            if media_chain:
                rule_text = f"@media {media_chain} {{ {rule_text} }}"
            if supports_chain:
                rule_text = f"@supports {supports_chain} {{ {rule_text} }}"
            out.append(rule_text)
        pending_decls.clear()

    for item in items:
        if item.type == "declaration":
            pending_decls.append(item)
            continue

        flush_decls()

        if item.type == "qualified-rule":
            inner_sels = _split_selectors(serialize(item.prelude))
            inner_sels = [s for s in inner_sels if not UNSUPPORTED_PSEUDO_RE.search(s)]
            if not inner_sels:
                continue
            new_chain = _combine_chain(selector_chain, inner_sels)
            inner_items = tinycss2.parse_blocks_contents(
                item.content, skip_comments=True, skip_whitespace=True
            )
            _process(out, inner_items, new_chain, media_chain, supports_chain)
        elif item.type == "at-rule":
            keyword = item.lower_at_keyword
            if keyword == "layer":
                if item.content is None:
                    continue
                inner_items = tinycss2.parse_blocks_contents(
                    item.content, skip_comments=True, skip_whitespace=True
                )
                _process(out, inner_items, selector_chain, media_chain, supports_chain)
            elif keyword == "media" and item.content is not None:
                cond = serialize(item.prelude).strip()
                new_media = cond if not media_chain else f"{media_chain} and {cond}"
                inner_items = tinycss2.parse_blocks_contents(
                    item.content, skip_comments=True, skip_whitespace=True
                )
                _process(out, inner_items, selector_chain, new_media, supports_chain)
            elif keyword == "supports" and item.content is not None:
                cond = serialize(item.prelude).strip()
                new_supports = (
                    cond if not supports_chain else f"{supports_chain} and ({cond})"
                )
                inner_items = tinycss2.parse_blocks_contents(
                    item.content, skip_comments=True, skip_whitespace=True
                )
                _process(
                    out, inner_items, selector_chain, media_chain, new_supports
                )
            elif keyword == "property" and item.content is not None:
                prop_name = serialize(item.prelude).strip()
                initial_value = None
                inner_items = tinycss2.parse_blocks_contents(
                    item.content, skip_comments=True, skip_whitespace=True
                )
                for d in inner_items:
                    if d.type == "declaration" and d.name == "initial-value":
                        initial_value = serialize(d.value).strip()
                        break
                if initial_value:
                    out.append(f":root {{ {prop_name}: {initial_value}; }}")
            elif item.content is None:
                out.append(serialize([item]).rstrip() + ";")
            else:
                out.append(serialize([item]))

    flush_decls()


def _serialize_declaration(decl) -> str:
    text = f"{decl.name}: {serialize(decl.value).strip()}"
    if decl.important:
        text += " !important"
    return text + ";"


def _split_selectors(s: str) -> list[str]:
    return [sel.strip() for sel in s.split(",") if sel.strip()]


def _combine_chain(
    parent_sels: list[str] | None, own_sels: list[str]
) -> list[str]:
    if parent_sels is None:
        return own_sels
    combined: list[str] = []
    for p in parent_sels:
        for o in own_sels:
            if "&" in o:
                combined.append(o.replace("&", p))
            else:
                combined.append(f"{p} {o}")
    return combined


def build() -> None:
    subprocess.run(
        [str(TAILWIND), "-i", str(SOURCE), "-o", str(TARGET)],
        check=True,
    )
    TARGET.write_text(transform_for_weasyprint(TARGET.read_text()))
    print(f"built {TARGET.relative_to(ROOT)}")


def _watched_mtime() -> float:
    paths = [SOURCE, *TEMPLATE_DIR.rglob("*.html")]
    return max(p.stat().st_mtime for p in paths if p.exists())


def watch() -> None:
    print("watching templates and source CSS — Ctrl-C to stop")
    last_seen = 0.0
    while True:
        latest = _watched_mtime()
        if latest > last_seen:
            try:
                build()
            except subprocess.CalledProcessError as e:
                print(f"build failed: {e}")
            last_seen = latest
        time.sleep(0.5)


if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch()
    else:
        build()
