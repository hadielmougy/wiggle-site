# wiggle-site

The source of **[wiggle.sh](https://wiggle.sh)** — a fully static site (no Node, no server), built
by a small Python generator.

## Layout

```
content/           the site's content
  index.html       landing page (raw HTML fragment, full-bleed)
  docs/*.md        documentation (vendored from wiggle/docs + site-only pages)
  patterns/*.md    the patterns library
  why.md, performance.md, community.md
templates/base.html  the shared shell (nav + footer)
assets/            css + images (svg diagrams vendored from wiggle/docs/img)
build.py           md → html, link rewriting, sidebars, pygments highlighting
scripts/sync-docs.sh  re-vendor docs + images from ../wiggle
dist/              build output (gitignored)
```

## Build

```bash
python3 -m venv .venv && .venv/bin/pip install markdown pygments   # once
.venv/bin/python build.py                                          # -> dist/
open dist/index.html                                               # or: python3 -m http.server -d dist
```

## Updating vendored docs

The docs pages under `content/docs/` (onboarding, cookbook, queues, sharding, local-execution)
are vendored snapshots of `../wiggle/docs`. After docs change in the main repo:

```bash
scripts/sync-docs.sh && .venv/bin/python build.py
```

`index.md` and `clients.md` are site-only — the sync script does not touch them.

## Deploying

`.github/workflows/deploy.yml` builds and publishes `dist/` to GitHub Pages on every push to
`main`. Note: **GitHub Pages does not serve private repositories on the free plan** — either make
this repo public, or point a host that supports private repos (Cloudflare Pages, Netlify) at it
with build command `python build.py` and output dir `dist`.

The custom domain (`wiggle.sh`) can only be attached to **one** Pages site at a time; cutting over
from the `wiggle` repo's Pages means removing the domain there and adding it here.
