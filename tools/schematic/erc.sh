#!/bin/zsh
# Run KiCad ERC on a root schematic and print violation counts by category.
# Usage: tools/schematic/erc.sh <root.kicad_sch> [report.rpt]
# Run it on a COPY of the project folder: kicad-cli can leave stale .lck files next to the schematic.
# Classify the categories with the schematic-style skill before acting on them.
K=${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}
rpt=${2:-${1:r}.rpt}
$K sch erc -o $rpt $1 2>&1 | grep -vi fontconfig
grep "^\[" $rpt | sed 's/^\[\(.*\)\]:.*/\1/' | sort | uniq -c
