#!/usr/bin/env bash
# Refresh the built Hibiscus artwork (pixel sprites, glyphs, Nunito, favicons, CSS tokens and the
# PixelAnim component) from a checkout of the Hibiscus design system. Maintainers only: the design
# system is not public, and only its built outputs are committed here (see ASSETS-LICENSE).
# Usage: HIBISCUS_ASSETS=/path/to/hibiscus-assets web/scripts/sync-assets.sh
set -euo pipefail
web="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
assets="${HIBISCUS_ASSETS:?set HIBISCUS_ASSETS to a hibiscus-assets checkout}"
bash "$assets/tools/sync.sh" "$web" --favicon
