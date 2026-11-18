# Schematic tools

Helpers for the `schematic-capture` and `schematic-style` skills. They need KiCad 10's `kicad-cli` (set
`KICAD_CLI` if it is not at the macOS default) and `pdftoppm` (poppler).

| Tool | Use |
|---|---|
| `render.sh <root.kicad_sch> <out_dir> [dpi]` | Export all sheets to PDF and one PNG per sheet |
| `erc.sh <root.kicad_sch> [report]` | Run ERC and count violations by category |
| `netcmp.py <baseline.net> <new.net>` | Net-by-net netlist diff; run after every `pcb apply` |
| `kicad_sexpr.py` | Lossless `.kicad_sch` reader/writer (`load`, `dumps`, `save`); round trip is byte-exact |
| `place.py` | Library for placement scripts: pin endpoints (rotate then mirror), grid snap, wire/junction/no-connect/label/hierarchical/global label emitters (text direction aware), text, titled group box, move/rotate/mirror by reference with readable fields, power symbols to hierarchical labels, paper (`PAPER_TABLOID = "USLedger"`), title block, deterministic UUIDs. See the module docstring |
| `overlap.py [--overlap] [--dangling] <sheet.kicad_sch> ...` | Text boxes vs wires, pins, symbol bodies and other text; unconnected wire ends, pins, labels, sheet pins. Exit 1 on findings |

Python tools are stdlib only; tests are `tests/test_schematic_tools.py`. Text sizes in `overlap.py` are estimates
calibrated on KiCad 10 renders (pin number/name text and group-box edges are not checked).

Run them on a copy of the project folder: `kicad-cli` can leave stale `.lck` files next to the schematic.
