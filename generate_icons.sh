#!/bin/bash

SOURCE_SVG="src/assets/icons/hicolor/scalable/apps/com.github.konverner.gnome-nano-image-edit.svg"
BASE_DIR="src/assets/icons/hicolor"
APP_ID="com.github.konverner.gnome-nano-image-edit"

CONVERTER=""

# Check for rsvg-convert or inkscape
if command -v rsvg-convert &> /dev/null; then
    CONVERTER="rsvg"
elif command -v inkscape &> /dev/null; then
    CONVERTER="inkscape"
elif python3 -m cairosvg --help &> /dev/null; then
    CONVERTER="cairosvg"
else
    echo "No suitable SVG converter found."
    echo "Please install one of the following:"
    echo "  1. System tools: sudo apt install librsvg2-bin (or inkscape)"
    echo "  2. Python tool:  pip install cairosvg"
    exit 1
fi

# Sizes to generate
SIZES=(48 128 256 512)

for size in "${SIZES[@]}"; do
    OUTPUT_DIR="$BASE_DIR/${size}x${size}/apps"
    OUTPUT_FILE="$OUTPUT_DIR/$APP_ID.png"
    
    echo "Generating ${size}x${size} icon..."
    mkdir -p "$OUTPUT_DIR"
    
    if [ "$CONVERTER" = "rsvg" ]; then
        rsvg-convert -w "$size" -h "$size" -f png -o "$OUTPUT_FILE" "$SOURCE_SVG"
    elif [ "$CONVERTER" = "inkscape" ]; then
        # Inkscape CLI syntax varies by version, this covers 1.0+
        inkscape -w "$size" -h "$size" -o "$OUTPUT_FILE" "$SOURCE_SVG"
    elif [ "$CONVERTER" = "cairosvg" ]; then
        python3 -m cairosvg "$SOURCE_SVG" -o "$OUTPUT_FILE" --output-width "$size" --output-height "$size"
    fi
done

echo "Done."
