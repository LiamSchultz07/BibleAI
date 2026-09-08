#!/usr/bin/env bash
# Download the open-license source texts.
#
# Every translation here is public domain or openly licensed, so this needs no
# API key, account, or publisher agreement.
set -euo pipefail

DEST="${1:-$(cd "$(dirname "$0")/.." && pwd)/sources}"

if [ -d "$DEST/.git" ]; then
  echo "Sources already present at $DEST — pulling updates."
  git -C "$DEST" pull --ff-only
else
  echo "Cloning open-license Bible texts into $DEST"
  git clone --depth 1 https://github.com/seven1m/open-bibles.git "$DEST"
fi

echo
echo "Done. English translations available:"
ls "$DEST" | grep '^eng-' || true
