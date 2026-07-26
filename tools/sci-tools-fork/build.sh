#!/usr/bin/env bash
# Clone + patch + build sci-tools with the JSON IR emitter, then emit a game's IR.
# Usage: build.sh [GAME_DIR] [OUT_DIR]
#   GAME_DIR  original SCI game resources (default: /mnt/i/sierra/lsl2)
#   OUT_DIR   where to write .sc + <game>.ir.json (default: build/ir)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FORK="$REPO_ROOT/vendor/sci-tools"
# OUR FORK of sci-tools (MIT, sluicebox). Our changes -- the --json IR emitter and the export
# table -- are ordinary commits on the `json-ir` branch rather than a patch applied at build
# time. That patch had grown to two independent changes, and because vendor/ is gitignored an
# edit made here could silently vanish on the next build; commits cannot.
# Upstream stays available as the `upstream` remote for syncing:
#   git -C vendor/sci-tools fetch upstream && git -C vendor/sci-tools rebase upstream/main
FORK_URL=https://github.com/katiahayati/sci-tools
UPSTREAM_URL=https://github.com/sluicebox/sci-tools
PIN=3895bc1a54515dc1d62e53570090a91b015afe52     # katiahayati/sci-tools json-ir
GAME_DIR="${1:-/mnt/i/sierra/lsl2}"
OUT_DIR="${2:-$REPO_ROOT/build/ir}"

export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1

if [ ! -d "$FORK/.git" ]; then
  git clone "$FORK_URL" "$FORK"
fi
cd "$FORK"
git remote get-url upstream >/dev/null 2>&1 || git remote add upstream "$UPSTREAM_URL"
git fetch --depth 50 origin || true
git checkout -q "$PIN" 2>/dev/null || echo "warning: pinned commit $PIN not found; using current HEAD"

dotnet build Snuffer/Snuffer.csproj -c Release
mkdir -p "$OUT_DIR"
dotnet Snuffer/bin/Release/net8.0/Snuffer.dll -d --json "$GAME_DIR" "$OUT_DIR"
echo "IR written under: $OUT_DIR/*.ir.json"
