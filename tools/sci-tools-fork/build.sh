#!/usr/bin/env bash
# Clone + patch + build sci-tools with the JSON IR emitter, then emit a game's IR.
# Usage: build.sh [GAME_DIR] [OUT_DIR]
#   GAME_DIR  original SCI game resources (default: /mnt/i/sierra/lsl2)
#   OUT_DIR   where to write .sc + <game>.ir.json (default: build/ir)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FORK="$REPO_ROOT/vendor/sci-tools"
PATCH="$REPO_ROOT/tools/sci-tools-fork/json-ir.patch"
PIN=46b19e8983286fab2f632d74c6bb84ee44172f07     # sci-tools commit this patch targets
GAME_DIR="${1:-/mnt/i/sierra/lsl2}"
OUT_DIR="${2:-$REPO_ROOT/build/ir}"

export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1

if [ ! -d "$FORK/.git" ]; then
  git clone https://github.com/sluicebox/sci-tools "$FORK"
fi
cd "$FORK"
git fetch --depth 50 origin || true
git checkout -q "$PIN" 2>/dev/null || echo "warning: pinned commit $PIN not found; using current HEAD"
git checkout -- . 2>/dev/null || true         # drop any prior patch application
git apply --check "$PATCH" && git apply "$PATCH"

dotnet build Snuffer/Snuffer.csproj -c Release
mkdir -p "$OUT_DIR"
dotnet Snuffer/bin/Release/net8.0/Snuffer.dll -d --json "$GAME_DIR" "$OUT_DIR"
echo "IR written under: $OUT_DIR/*.ir.json"
