# KiCad files: how they are made and checked

Never hand-draw a symbol or footprint. Start from the vendor download (Ultra Librarian, SnapEDA, manufacturer) in
`docs/vendor/<Value>/`, then fix it up. Each fix-up is checkable against the datasheet.

Vendor files only in Altium format (`.SchLib`, `.PcbLib`): convert them with the KiCad command line, keep the
originals next to the result, and record the conversion in `docs/vendor/<Value>/KiCad_from_Altium/CONVERTED.txt`:
```sh
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli   # macOS install; `kicad-cli` on PATH elsewhere
$K fp upgrade --force -o <out>.pretty <file>.PcbLib
$K sym upgrade --force -o <out>.kicad_sym <file>.SchLib
```
Then fix up the converted files like any other vendor file. Check custom drain/exposed pads (converted pads are
custom shapes, sometimes with tiny anchor pads) and remove converter leftovers. Vendor footprints that draw an
exposed pad as plain copper (`fp_poly` on F.Cu) instead of a pad must get a real pad numbered as the pin it
belongs to, or the copper has no net.

## Symbol (`<Value>.kicad_sym`)
- Properties: `Value` = Value, `Manufacturer_Part_Number` = MPN, `Manufacturer_Name` = manufacturer with spaces,
  `Datasheet` = manufacturer URL, `Description` filled, `Footprint` = `<Value>` (the footprint name; the symbol and footprint sit in the same package directory).
- Pin names verbatim from the datasheet (`+IN`, `-VS`). Rename only same-name pins that are separate nodes
  (two `RG` pins -> `RG1`, `RG2`).
- Pin electrical types from the datasheet function text, not the vendor. Supplies `power_in`, external-component
  pins `passive`.
- Every pin on the 2.54 mm grid; body roughly centred on the origin.
- `[[pin]]` in `component.toml` must match the symbol exactly; `python3 -m lib.check` enforces it.

## Footprint (`<Value>.kicad_mod`)
- Pads equal the datasheet's recommended land pattern (size, position, corner radius). If the datasheet has no land
  pattern, say so in the component's notes and keep the vendor's nominal-density pattern.
- Vendor ships L/N/M densities: use N (nominal).
- Courtyard 0.25 mm beyond the larger of the pads and the body/lead extent, on F.CrtYd.
- Pin-1 marker visible outside the body on silkscreen.
- STEP model: keep an existing embedded model (`kicad-embed://<Value>.step`), or copy the vendor STEP as
  `<Value>.step` next to the footprint and reference it (`step = "<Value>.step"` in component.toml). No vendor model:
  `step = "none"`. Never substitute another part's model.
- Footprint pads must cover every `[[pin]]` number; `python3 -m lib.check` enforces it.

## What still needs a human with KiCad open
- Pin 1 orientation of the 3D model in the 3D viewer.
- Silkscreen/fab legibility.
