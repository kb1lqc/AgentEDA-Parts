#!/bin/zsh
# Render every sheet of a schematic to PNG (one file per sheet: <prefix>-1.png, <prefix>-2.png, ...).
# Usage: tools/schematic/render.sh <root.kicad_sch> <out_dir> [dpi]
# Zoom into an area afterwards with: pdftoppm -r 300 -x X -y Y -W W -H H -png <out_dir>/sch.pdf <out_dir>/zoom
K=${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}
mkdir -p $2
$K sch export pdf --output $2/sch.pdf $1 2>&1 | grep -vi fontconfig
pdftoppm -r ${3:-150} -png $2/sch.pdf $2/sheet
ls $2/sheet-*.png
