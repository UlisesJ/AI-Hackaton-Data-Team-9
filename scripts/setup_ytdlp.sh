#!/usr/bin/env bash
# Bootstrap YouTube download tooling (standalone yt-dlp + PO Token server deps).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/bin/yt-dlp-plugins"

if [[ ! -x "$ROOT/bin/yt-dlp" ]]; then
  echo "Downloading yt-dlp macOS binary…"
  curl -L -o "$ROOT/bin/yt-dlp" \
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
  chmod +x "$ROOT/bin/yt-dlp"
fi

if [[ ! -f "$ROOT/bin/yt-dlp-plugins/bgutil-ytdlp-pot-provider.zip" ]]; then
  echo "Downloading bgutil POT plugin…"
  curl -L -o "$ROOT/bin/yt-dlp-plugins/bgutil-ytdlp-pot-provider.zip" \
    "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/releases/latest/download/bgutil-ytdlp-pot-provider.zip"
fi

if [[ ! -d "$ROOT/vendor/bgutil-ytdlp-pot-provider" ]]; then
  echo "Cloning bgutil POT server…"
  git clone --depth 1 --branch 1.3.2 \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
    "$ROOT/vendor/bgutil-ytdlp-pot-provider"
fi

if [[ ! -f "$ROOT/vendor/bgutil-ytdlp-pot-provider/server/build/main.js" ]]; then
  echo "Building POT server…"
  (
    cd "$ROOT/vendor/bgutil-ytdlp-pot-provider/server"
    npm ci
    npx tsc
  )
fi

echo "OK — run POT server with:"
echo "  node $ROOT/vendor/bgutil-ytdlp-pot-provider/server/build/main.js --port 4416"
echo "App will also try to auto-start it on first download."
