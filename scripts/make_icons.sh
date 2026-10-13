#!/usr/bin/env bash
set -e

# make_icons.sh - makes the two derived icons from the master, assets/icon/icon_1024x1024.png:
#   assets/icon/icon_512x512.png        Linux AppImage and the Windows installer / exe (pyside6-deploy turns the PNG into a .ico)
#   assets/icon/jv-studio-macos.icns    macOS app, with all ten sizes (16, 32, 128, 256 and 512 points, each at 1x and 2x)
#
# The master is exactly 1024x1024 and already in macOS icon form (rounded square about 824px wide, centred, soft shadow, transparent corners), as exported by
# IconKitchen or a design tool. Every size is scaled DOWN from it, never up, which is why it has to be the 1024px one.
# assets/icon/icon_source.png is the plain full-bleed square the master was made from; it is not used by the build.
# Needs macOS (sips and iconutil ship with it). Run it again whenever the master changes.
#
#   scripts/make_icons.sh

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ICON_DIR="$ROOT_DIR/assets/icon"
MASTER="$ICON_DIR/icon_1024x1024.png"

[ -f "$MASTER" ] || { echo "Missing $MASTER - export a 1024x1024 macOS-style icon (rounded square, transparent corners) and save it there."; exit 1; }
WIDTH=$(sips -g pixelWidth "$MASTER" | awk '/pixelWidth/ {print $2}')
HEIGHT=$(sips -g pixelHeight "$MASTER" | awk '/pixelHeight/ {print $2}')
if [ "$WIDTH" != "1024" ] || [ "$HEIGHT" != "1024" ]; then
    echo "icon_1024x1024.png must be exactly 1024x1024 (it is ${WIDTH}x${HEIGHT})"
    exit 1
fi

sips -z 512 512 "$MASTER" --out "$ICON_DIR/icon_512x512.png" >/dev/null

WORK="$(mktemp -d)"
ICONSET="$WORK/AppIcon.iconset"
mkdir -p "$ICONSET"
for POINTS in 16 32 128 256 512; do
    sips -z $POINTS $POINTS "$MASTER" --out "$ICONSET/icon_${POINTS}x${POINTS}.png" >/dev/null
    DOUBLE=$((POINTS * 2))
    if [ "$DOUBLE" = "1024" ]; then
        cp "$MASTER" "$ICONSET/icon_${POINTS}x${POINTS}@2x.png"
    else
        sips -z $DOUBLE $DOUBLE "$MASTER" --out "$ICONSET/icon_${POINTS}x${POINTS}@2x.png" >/dev/null
    fi
done
iconutil -c icns "$ICONSET" -o "$ICON_DIR/jv-studio-macos.icns"
rm -rf "$WORK"

echo "Wrote:"
ls -l "$ICON_DIR"
