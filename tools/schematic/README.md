# Schematic tools

Helpers for the `schematic-capture` and `schematic-style` skills. They need KiCad 10's `kicad-cli` (set
`KICAD_CLI` if it is not at the macOS default) and `pdftoppm` (poppler).

| Tool | Use |
|---|---|
| `render.sh <root.kicad_sch> <out_dir> [dpi]` | Export all sheets to PDF and one PNG per sheet |
| `erc.sh <root.kicad_sch> [report]` | Run ERC and count violations by category |
| `netcmp.py <baseline.net> <new.net>` | Net-by-net netlist diff; run after every `pcb apply` |

Planned (see `schematic-capture`): a text-overlap checker (label, port, sheet-pin and field text vs wires) and
placement helpers (pin endpoint from a symbol's position, rotation and mirror; label emitters).

Run them on a copy of the project folder: `kicad-cli` can leave stale `.lck` files next to the schematic.
