#!/bin/sh
# Re-vendor the docs + diagrams this site publishes from the main wiggle repo (../wiggle), then
# regenerate the Java in site-only pages from compiled source there (scripts/snippets.py).
#
# Vendored docs cannot go stale -- they are copies. Site-only pages can, and did: the saga page
# published a removed API for weeks because nothing in this pipeline compiled its Java. Anything
# it now shows comes from a fixture the main repo's build checks.
#
# Site-only prose (content/docs/index.md, content/docs/clients.md) is not touched.
set -eu
cd "$(dirname "$0")/.."
SRC=../wiggle/docs
for f in onboarding versioning cookbook queues local-execution observed-execution; do
  cp "$SRC/$f.md" content/docs/
done
for img in architecture bench-sojourn bench-adaptive queues-flow; do
  cp "$SRC/img/$img.svg" assets/img/
done
for img in console-instance-trace console-performance; do
  cp "$SRC/img/$img.png" assets/img/
done
python3 scripts/snippets.py

echo "synced. rebuild with: .venv/bin/python build.py"
