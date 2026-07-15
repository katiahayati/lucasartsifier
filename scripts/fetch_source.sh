#!/usr/bin/env bash
# Vendor the decompiled LSL2 scripts the analyzer reads as input.
#
# We do NOT redistribute the decompilation; we fetch it (sparse) from its source
# repo. The version (lsl2-dos-1.002.000) is matched to the user's game files.
#
# Usage:  ./scripts/fetch_source.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/vendor/sci-scripts"

if [ -d "$DEST/lsl2-dos-1.002.000/src" ]; then
  echo "already vendored: $DEST/lsl2-dos-1.002.000/src"
  exit 0
fi

echo "sparse-cloning sluicebox/sci-scripts (lsl2-dos-1.002.000) ..."
rm -rf "$DEST"
git clone --depth 1 --filter=blob:none --sparse \
    https://github.com/sluicebox/sci-scripts "$DEST"
git -C "$DEST" sparse-checkout set lsl2-dos-1.002.000

n=$(find "$DEST/lsl2-dos-1.002.000/src" -name '*.sc' | wc -l)
echo "done: $n .sc scripts under $DEST/lsl2-dos-1.002.000/src"
