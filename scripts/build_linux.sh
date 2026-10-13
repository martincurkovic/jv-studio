#!/usr/bin/env bash
set -e

# build_linux.sh - builds the JV-Studio standalone Linux app
# Can be run from anywhere. Handles uv sync and the packaging (pyside6-deploy / Nuitka).
# Requires build-essential and patchelf installed first (Nuitka compiles C).

APP_NAME="JV-Studio"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$ROOT_DIR/src"

if ! command -v gcc >/dev/null 2>&1 && ! command -v cc >/dev/null 2>&1; then
    echo "No C compiler found - install one first (Nuitka needs it):"
    echo "  sudo apt update && sudo apt install build-essential patchelf"
    exit 1
fi

cd "$ROOT_DIR"
echo "Syncing environment with uv..."
uv sync
uv pip install pip

cd "$SRC_DIR"

# derive version from nearest git tag - falls back to dev placeholder if no tags exist yet
RAW_TAG=$(git -C "$ROOT_DIR" describe --tags --abbrev=0 2>/dev/null || true)
if [ -z "$RAW_TAG" ]; then
    VERSION="0.0.0-dev"
else
    VERSION=$(echo "$RAW_TAG" | sed 's/^v//')
fi
echo "Building version: $VERSION"
echo "APP_VERSION = \"$VERSION\"" >"$SRC_DIR/jv_studio/_build_version.py"

if [ ! -f "pysidedeploy.spec" ]; then
    echo "No spec file found - generating from defaults"

    uv run pyside6-deploy --init main.py

    sed -i "s/^title = .*/title = $APP_NAME/" pysidedeploy.spec
    sed -i "s|^icon = .*|icon = ../assets/icon/icon_512x512.png|" pysidedeploy.spec
    sed -i 's/^mode = .*/mode = standalone/' pysidedeploy.spec

    echo "Spec generated and configured."
fi

# Data the app reads at run time, paths relative to src/ (where this runs), as SRC=DEST inside the app:
#   the parameter and wave-name tables, the stylesheet template, icons and diagrams, and the licence
DATA_ARGS="--include-data-dir=jv_studio/data=jv_studio/data --include-data-dir=jv_studio/ui/icons=jv_studio/ui/icons --include-data-files=jv_studio/ui/style.qss.template=jv_studio/ui/style.qss.template --include-data-dir=jv_studio/ui/help=jv_studio/ui/help --include-data-files=../LICENSE=LICENSE"

# re-generate extra_args on EVERY run, that way version number can update correctly
sed -i "s|^extra_args = .*|extra_args = --quiet --noinclude-qt-translations --assume-yes-for-downloads $DATA_ARGS|" pysidedeploy.spec

echo "Building $APP_NAME..."
uv run pyside6-deploy -c pysidedeploy.spec

echo ""
echo "Done - check the output above for exactly where the build landed."
