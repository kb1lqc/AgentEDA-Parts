# pcb / KiCad toolchain facts for schematic work

Verified on Zener / pcb 0.4.102 with KiCad 10. Re-verify with a throwaway build before relying on one for a newer version. Style rules are in the `schematic-style` skill; the workflow is `docs/briefs/schematic-capture.md`.

## Generation
- **Sub-sheets.** A module becomes its own sub-sheet when it declares `Project(name="<Module>", path="<anything>", layout=False)` (stdlib `properties.zen`). `path` is required; without it the module is flattened. The parent gets a sheet symbol named after the instance with one sheet pin per port; the child is `<instance>.kicad_sch` next to the root. A second `Project()` at the root writes a full copy of the design.
- **Net types decide the drawing.** `Power` and `Ground` nets become power symbols; plain `Net`s become labels, and a plain-`Net` port of a sub-sheet becomes a hierarchical label. A `Power` net passed into a sub-sheet appears inside as a global power symbol and ERC reports its sheet pin unmatched: declare power paths into reusable sheets as `Net(voltage=...)`; voltage checks still run.
- **Internal net names** are always `<instance>.<net>`, even for an explicit `Net()`. Write `X = Net(...)`, not `X = Net("X")` (`style.redundant_name` advice).
- **Interfaces** (`Spi`, `I2c`) become one hierarchical label and sheet pin per member (`SPI.CS`). A hand-drawn bus group does not persist; `pcb apply` rewrites it into separate pins and leaves breakouts dangling (ERC errors that `pcb build` misses). Keep members as separate pins.
- **Child sheets are per instance and per board.** Each instance becomes `<instance>.kicad_sch` in the board's `eda/`, generated fresh; `Project(path=)` is not a template. A copied arranged sheet keeps its placement but the root's rail sheet pins need the transplant below, and a second copy for another instance fails (duplicate net symbol UUID) and carries the first instance's prefix. Stamping handles this (`reusable-blocks`, circuit-blocks `stamp_block.py`).

## Local rails in a sub-sheet
Library wrappers type supply pins as `Power` and ground pins as `Ground`, so inside a block they draw as global power symbols. To make them local:
1. Declare module ports as plain nets (`V3V3 = io(Net)`, `GND = io(Net)`, then `_GND = Ground(GND)` and connect library ground pins to `_GND`); the board keeps `V3V3 = Power(..., voltage=...)`.
2. The root gets V3V3/GND sheet pins.
3. Replace each V3V3/GND power symbol in the child with a `hierarchical_label` of the same name at the symbol's pin point (angle 90 rail, 270 ground; ground label pointing down uses `justify right`). Use `place.py power_to_hlabels` (rails text up, ground down).
4. A fresh regeneration restores the power symbols: re-run the swap after any regeneration.
5. On an already-arranged sheet an incremental `pcb apply` does not add the new sheet pins or root power symbols after a port-type change, yet reports success with rails split into `/INA/V3V3` and `/INA/GND` (only the netlist diff shows it). Generate a throwaway fresh copy, transplant the root's new sheet pins, power symbols and their `lib_symbols` entries by script, then place them.

## Applying
- `pcb apply` is incremental: it keeps hand-moved symbols, wires, labels, text, graphics, title block and paper size, and refuses an edit that changes connectivity ("not netlist-equivalent", including shorts and splits). Net-name, net-type and new-sheet changes often appear only on a fresh generation (delete the `.kicad_sch` files, apply again), which loses placement. Finish the Zener code first, regenerate once, then arrange. A freshly generated sheet has default positions, power symbols and no wiring: re-run the generator after every fresh generation.
- A silent label drop can show exit 0 and "updated": diff `kicad-cli sch export netlist` before and after.
- A top-level `(text`, `(text_box` or `(rectangle` inserted inside a `lib_symbols` entry is dropped silently; insert before the file's final `)`. Count them after every apply.
- **Port limit:** `pcb apply` deletes local or global labels carrying a port net's name and re-adds a hierarchical label on every separate wire group of that net. Achieve "each port once" by wiring every use into one wire group.
- `--no-open` and no stale `*.lck` are enforced by circuit-blocks `tools/check_env.py`. Run `kicad-cli` on copies of the project folder. On macOS `kicad-cli` is `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`.
- Render: `kicad-cli sch export pdf --output <scratch>/s.pdf <root>.kicad_sch && pdftoppm -r 110 -png <scratch>/s.pdf <scratch>/s`.
- KiCad 10 symbols (format 20251024+) are required by `pcb apply`.

## ERC
- Run ERC on the root sheet; a child alone reports every hierarchical label as `pin_not_connected`.
- Zero tolerance: dangling wires, unconnected endpoints, hierarchical mismatches.
- `label_dangling` on a local label of a sheet with no component pin, net with more than one pin in a sub-sheet, is not a wiring fault (KiCad `ercCheckLabels`); a global label clears it but changes the net name. House convention: local labels for board-level nets, accept these until connectors or host exist. Also `label_dangling` on a root label whose net has only a sheet pin, and `isolated_pin_label`, are net-level.
- Expected while the board is incomplete, re-check later: `isolated_pin_label`, `pin_not_driven`, `power_pin_not_driven`. `lib_symbol_issues` is a project-configuration notice.

## Hand-editing S-expressions and placement geometry
- Sheet Y grows downward. Pin positions in `lib_symbols` are relative to the symbol origin; transform: flip y to screen, rotate CCW, then mirror (`mirror x` flips screen y, `mirror y` flips screen x); rot 0: sheet = (at.x + x, at.y - y). Read each symbol's real pin geometry; never assume symmetry. Move Reference and Value with the symbol.
- KiCad 10 writes `(sheet` then a newline: search `\(sheet($|\s)`.
- Rotate 180 swaps left/right and up/down of the pin groups and reverses pin order top to bottom; mirror flips one axis.
- A field's stored angle is relative to the symbol rotation (behaviour differed between passes): place with `set_field` (visual angle, sets `do_not_autoplace`) and confirm in a render.
- Labels: a local label anchors at the wire end with text running along the wire (angle toward the pin, justify left/right + bottom), and the wire must be longer than the text. Hierarchical and global labels anchor at the wire end with text running away from the wire; the flag goes at the wire's far end. KiCad never draws text upside down: 0 and 90 use `left`, 180 and 270 use `right`.
- Local-label text sits 0.3-0.5 mm above its wire; at 2.54 mm pitch neighbours touch. Fan stacked label wires out to 5.08 mm pitch with nested jogs. Plan room for a pull-up's vertical drop before routing a stacked pin group.
- Wires on 1.27 mm, pin rows on 2.54 mm; dog-leg inside a 2.54 mm pitch.
- Paper: Tabloid is `USLedger`; `pcb apply` preserves it.

## Tools
Generic helpers live in `tools/schematic/` (README there): `render.sh`, `netcmp.py`, `erc.sh`, `kicad_sexpr.py`, `place.py`, `overlap.py`. Run them on copies. `overlap.py` skips pin number/name text and group-box edges; review those in the render.
