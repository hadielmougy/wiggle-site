#!/usr/bin/env python3
"""Static site generator for wiggle.sh — zero Node, zero server.

Reads content/ (markdown + raw-HTML fragments), wraps everything in templates/base.html,
and writes a fully static site to dist/. Markdown gets fenced code + syntax highlighting
(pygments), tables, and heading anchors. Links to vendored docs are rewritten to site
paths; links to repo files that are NOT on the site go to GitHub.

    .venv/bin/python build.py        # -> dist/
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from string import Template

import markdown
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
DIST = ROOT / "dist"
GITHUB = "https://github.com/hadielmougy/wiggle"

# ---- navigation ---------------------------------------------------------------------------

# (slug, title) — order defines the sidebar. Slugs are content/docs/<slug>.md.
DOCS_NAV = [
    ("index", "Overview"),
    ("onboarding", "Onboarding & configuration"),
    ("dsl-cookbook", "DSL cookbook"),
    ("queues", "Queues"),
    ("sharding-and-epochs", "Sharding & epochs"),
    ("local-execution", "Local execution"),
    ("clients", "Go & Python clients"),
]

PATTERNS_NAV = [
    ("index", "All patterns"),
    ("fork-join", "Parallel fork / join"),
    ("approval", "Human-in-the-loop approval"),
    ("fan-out", "Dynamic fan-out (forEach)"),
    ("retries", "Retries & failure isolation"),
    ("scheduled", "Cron & scheduled work"),
    ("microservices", "One flow, many services"),
    ("cells", "Per-tenant isolation (cells)"),
]

TOP_NAV = [  # (href, label) for the header
    ("/docs/", "Docs"),
    ("/patterns/", "Patterns"),
    ("/why/", "Why Wiggle"),
    ("/performance/", "Performance"),
    ("/community/", "Community"),
]

# docs that exist in the wiggle repo but are not vendored on the site
_REPO_DOC = re.compile(r"\]\((?!https?://|#|/)([\w./-]+?\.md)(#[\w-]+)?\)")


def md_engine() -> markdown.Markdown:
    return markdown.Markdown(extensions=[
        "fenced_code", "codehilite", "tables", "toc", "attr_list", "md_in_html", "sane_lists",
    ], extension_configs={
        "codehilite": {"guess_lang": False, "css_class": "codehilite"},
        "toc": {"permalink": "§", "permalink_title": "link to this section"},
    })


def rewrite_links(text: str, section: str) -> str:
    """Rewrite markdown links: vendored docs -> pretty site paths; other repo files -> GitHub."""
    vendored = {slug for slug, _ in DOCS_NAV}

    def repl(m: re.Match) -> str:
        path, frag = m.group(1), m.group(2) or ""
        name = Path(path).stem
        if name in vendored and "/" not in path.strip("./"):
            return f"](/docs/{name}/{frag})"
        clean = re.sub(r"^(\.\./)+", "", path)
        return f"]({GITHUB}/blob/main/{'docs/' if '/' not in clean else ''}{clean}{frag})"

    text = _REPO_DOC.sub(repl, text)
    # non-doc repo files (java sources, README) linked with ../
    text = re.sub(r"\]\((\.\./)+([\w./-]+)\)", rf"]({GITHUB}/blob/main/\2)", text)
    return text


def sidebar_html(nav: list[tuple[str, str]], section: str, active: str) -> str:
    items = []
    for slug, title in nav:
        href = f"/{section}/" if slug == "index" else f"/{section}/{slug}/"
        cls = ' class="active"' if slug == active else ""
        items.append(f'<li{cls}><a href="{href}">{title}</a></li>')
    return "<ul>" + "".join(items) + "</ul>"


def nav_html(active: str) -> str:
    out = []
    for href, label in TOP_NAV:
        cls = ' class="here"' if href.strip("/") == active else ""
        out.append(f'<a{cls} href="{href}">{label}</a>')
    return "".join(out)


def page(tpl: Template, *, title: str, description: str, content: str,
         active: str = "", sidebar: str = "", path: str = "") -> str:
    body = (f'<div class="docwrap wrap"><aside class="sidebar">{sidebar}</aside>'
            f'<article class="doc">{content}</article></div>') if sidebar else content
    return tpl.substitute(title=title, description=description, content=body,
                          nav=nav_html(active), canonical=f"https://wiggle.sh{path}")


def emit(path: str, html: str) -> None:
    out = DIST / path.strip("/") / "index.html" if path.strip("/") else DIST / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")


def first_paragraph(md_text: str) -> str:
    for block in md_text.split("\n\n"):
        block = block.strip()
        if block and not block.startswith("#"):
            return re.sub(r"[*_`\[\]]|\(.*?\)", "", block.replace("\n", " "))[:300]
    return ""


def build_section(tpl: Template, section: str, nav: list[tuple[str, str]]) -> None:
    engine = md_engine()
    for slug, title in nav:
        src = CONTENT / section / f"{slug}.md"
        if not src.exists():
            raise SystemExit(f"missing {src}")
        raw = rewrite_links(src.read_text(encoding="utf-8"), section)
        engine.reset()
        html = engine.convert(raw)
        path = f"/{section}/" if slug == "index" else f"/{section}/{slug}/"
        emit(path, page(tpl, title=f"{title} · Wiggle", description=first_paragraph(raw),
                        content=html, active=section, path=path,
                        sidebar=sidebar_html(nav, section, slug)))


def build_page(tpl: Template, name: str, title: str, active: str = "") -> None:
    """A standalone markdown page (content/<name>.md) rendered full-width in a prose column."""
    engine = md_engine()
    raw = rewrite_links((CONTENT / f"{name}.md").read_text(encoding="utf-8"), "")
    html = f'<div class="wrap prose">{engine.convert(raw)}</div>'
    emit(f"/{name}/", page(tpl, title=f"{title} · Wiggle", description=first_paragraph(raw),
                           content=html, active=active or name, path=f"/{name}/"))


def pygments_css() -> str:
    light = HtmlFormatter(style="default").get_style_defs(".codehilite")
    dark = HtmlFormatter(style="one-dark").get_style_defs(".codehilite")
    return (f"{light}\n@media (prefers-color-scheme: dark) {{\n{dark}\n"
            ".codehilite { background: var(--code-bg); }\n}\n")


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    tpl = Template((ROOT / "templates" / "base.html").read_text(encoding="utf-8"))

    # assets
    shutil.copytree(ROOT / "assets", DIST / "assets")
    (DIST / "assets" / "css" / "code.css").write_text(pygments_css(), encoding="utf-8")
    (DIST / "CNAME").write_text("wiggle.sh\n", encoding="utf-8")

    # landing (raw HTML fragment, full-bleed)
    landing = (CONTENT / "index.html").read_text(encoding="utf-8")
    emit("/", page(tpl, title="Wiggle — durable workflows, cellular by design",
                   description="An open-source durable workflow engine with no replay and no "
                               "determinism rules: the workflow is data, not code. One JAR plus a "
                               "database; cellular sharding built in. Java, Go, and Python workers.",
                   content=landing, active="", path="/"))

    build_section(tpl, "docs", DOCS_NAV)
    build_section(tpl, "patterns", PATTERNS_NAV)
    build_page(tpl, "why", "Why Wiggle")
    build_page(tpl, "performance", "Performance")
    build_page(tpl, "community", "Community")

    # 404 (GitHub Pages picks up /404.html)
    nf = page(tpl, title="Not found · Wiggle", description="Page not found",
              content='<div class="wrap prose" style="text-align:center;padding:90px 0">'
                      "<h1>404</h1><p>That page doesn't exist. Try the "
                      '<a href="/docs/">docs</a> or the <a href="/">home page</a>.</p></div>',
              path="/404.html")
    (DIST / "404.html").write_text(nf, encoding="utf-8")

    n = sum(1 for _ in DIST.rglob("index.html"))
    print(f"built {n} pages -> {DIST}")


if __name__ == "__main__":
    main()
