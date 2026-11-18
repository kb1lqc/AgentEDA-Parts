# Families and variants

Orderables that share one package (same symbol, footprint, STEP) and differ only in grade or option are one family
directory named for the package (`LTC4364MS`) with `variants.toml`. Another package is another directory and needs its
own KiCad files. Functional silicon variants need distinct symbols; ordering-only variants (tape/reel, temperature
grade, RoHS suffix) do not.

One directory holds several orderable Values that share a datasheet (LTC4364HMS-1, LTC4364IMS-1). The family
directory is an ordinary component directory (`component.toml`, `calc.py`, KiCad files) plus `variants.toml`; each
variant lists only what differs.

```toml
# components/AnalogDevices/LTC4364MS/variants.toml
[variant."LTC4364HMS-1"]
mpn        = "LTC4364HMS-1#TRPBF"        # any [part] key may be overridden here
alternates = ["LTC4364HMS-1#PBF"]
temp_grade = "-40 to 125 degC"

[variant."LTC4364HMS-1".param.ta_grade]  # replaces the shared row of that key, or adds a row (same schema)
name = "..."                              # ... every field of a normal row
```
- Every variant sets its own `mpn`, `alternates` (may be `[]`) and `temp_grade` (lib.check errors otherwise); the shared
  `[part]` should not carry them.
- In the family `component.toml`, `[part] value` is the family name (= directory name, `LTC4364MS`); each variant's
  Value is its table key in `variants.toml`.
- A shared row may carry `variants = ["LTC4364HMS-1", "LTC4364IMS-1"]`: it applies only to those variants.
- Merged data for a variant: shared `[part]` overridden by the variant's keys (value = the variant); shared rows that
  apply to it, in file order; then each `[variant.X.param.key]` replaces the shared row in place or is appended.
- `load("AnalogDevices/LTC4364MS", variant="LTC4364HMS-1")` returns a normal `Part` for that variant (same calc
  module). `load("AnalogDevices/LTC4364HMS-1")`, a variant Value that is not a directory, scans
  `components/<Mfr>/*/variants.toml` for it. `load()` of a family without `variant=` raises an error listing the
  variants. `Part.variant` is the variant Value (None for a plain part); `Part.family_path` the family directory.
- `lib.readme` writes one README per family: a Variants table (Value, mpn, alternates, temp_grade, and any other
  `[part]` key some variant overrides), the shared tables (restricted rows show "Variants: X, Y" in Conditions), and a
  "Variant-specific parameters" section per variant with overrides.
- `lib.zen` writes one wrapper per variant, `<Variant>.zen`, in the family directory with one `pcb.toml`;
  `pcb build <dir>` builds every entrypoint. The wrapper uses the variant's merged `[part]` and params.
- A series component cannot be a family. A shared row restricted with `variants = [...]` or overridden per variant keeps its cite.
