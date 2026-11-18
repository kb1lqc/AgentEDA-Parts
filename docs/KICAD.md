# KiCad files: how they are made and checked

Never hand-draw a symbol or footprint. Start from the vendor download (Ultra Librarian, SnapEDA, manufacturer) in
`docs/vendor/<Value>/`, then fix it up. Vendor files ship L/N/M
densities: use N. Check every vendor download is for this datasheet's part and package. An MPN match does not prove the vendor footprint is right; if it is wrong, replace it from the
datasheet land pattern.

Vendor files only in Altium format (`.SchLib`, `.PcbLib`): convert them with the KiCad command line, keep the
originals next to the result, and record the conversion in `docs/vendor/<Value>/KiCad_from_Altium/CONVERTED.txt`:
```sh
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli   # macOS install; `kicad-cli` on PATH elsewhere
$K fp upgrade --force -o <out>.pretty <file>.PcbLib
$K sym upgrade --force -o <out>.kicad_sym <file>.SchLib
```
Then fix up the converted files like any other vendor file. Check custom drain/exposed pads (converted pads are
custom shapes) and remove converter leftovers. An exposed pad drawn as plain copper (`fp_poly` on F.Cu) must get a
real pad numbered as the pin it belongs to, or the copper has no net.

## Symbol (`<Value>.kicad_sym`)
- Format: KiCad 10, `(version 20251024)` or newer (`pcb apply` rejects older). Upgrade BEFORE the fix-ups with
  `$K sym upgrade --force <Value>.kicad_sym`, then check pins and properties are unchanged and restore the curated
  Description (the upgrade can overwrite it from ki_description).
- Properties: `Value` = Value, `Manufacturer_Part_Number` = MPN, `Manufacturer_Name` = manufacturer with spaces,
  `Datasheet` = manufacturer URL, `Description` filled, `Footprint` = `<Value>`.
- Pin names verbatim from the datasheet (`+IN`, `-VS`). Rename only same-name pins that are separate nodes
  (two `RG` pins -> `RG1`, `RG2`).
- Pin electrical types from the datasheet function text, not the vendor. Supplies `power_in`, external-component
  pins `passive`.
- Body roughly centred on the origin.

## Footprint (`<Value>.kicad_mod`)
- Pads equal the datasheet's recommended land pattern (size, position, corner radius). If the datasheet has no land
  pattern, say so in the component's notes and keep the vendor's nominal-density pattern.
- For an accepted footprint, set `Datasheet` to the geometry source and `Description` to the package and evidence basis.
- Courtyard on F.CrtYd (`lib.check` enforces the 0.25 mm margin beyond pads and F.Fab body).
- Pin-1 marker visible outside the body on silkscreen.
- STEP model: keep an existing embedded model (`kicad-embed://<Value>.step`), or copy the vendor STEP as
  `<Value>.step` next to the footprint and reference it (`step = "<Value>.step"` in component.toml). No vendor model:
  `step = "none"`. Never substitute another part's model. `pcb embed-step` rewrites every model reference: settle
  one model transform first.
- Stop and ask if the vendor footprint is mirrored or rotated, or pad count, pitch or pin-1 corner disagrees with the datasheet.

## What still needs a human with KiCad open
- Pin 1 orientation of the 3D model in the 3D viewer.
- Silkscreen/fab legibility.
