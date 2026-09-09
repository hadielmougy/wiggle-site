#!/bin/sh
# Re-vendor the docs + diagrams this site publishes from the main wiggle repo (../wiggle).
# Site-only pages (content/docs/index.md, content/docs/clients.md) are not touched.
set -eu
cd "$(dirname "$0")/.."
SRC=../wiggle/docs
for f in onboarding dsl-cookbook queues sharding-and-epochs local-execution; do
  cp "$SRC/$f.md" content/docs/
done
for img in architecture bench-sojourn bench-adaptive queues-flow; do
  cp "$SRC/img/$img.svg" assets/img/
done
echo "synced. rebuild with: .venv/bin/python build.py"
