# KiCad files: how they are made and checked

Never hand-draw a symbol or footprint. Start from the vendor download (Ultra Librarian, SnapEDA, manufacturer) in
`docs/vendor/<Value>/`, then fix it up. Each fix-up is checkable against the datasheet.

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
