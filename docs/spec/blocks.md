# Using this library from a blocks repo

A blocks repo is any repository of circuit blocks that imports parts from this library. AgentEDA-Blocks is one;
anyone can keep their own. This library needs no PDFs and no manufacturer export to be used: those are for the
maintainers who verify numbers. A user needs a clone of this repo and Python 3.11+ with matplotlib (no pip package).

## What a block does
1. Loads a part with `lib.load("<Mfr>/<Value>")` and reads numbers only through `part.param(key)` or
   `part.inputs(fn)` (`docs/spec/lib-api.md`). Never retypes a datasheet number.
2. Before relying on a part, asks whether it is safe to use: `python3 tools/status.py <Value> [--json]`. Exit 0:
   released (every row that matters checked by a person). Exit 1: not released; the output lists the rows that need a
   check and the values used but not covered. Exit 2: unknown part. `lib.unverified_inputs()` and the analysis verdict
   (`PASS (UNVERIFIED INPUTS)`) say the same for the rows an analysis really read.
3. After an analysis, writes the rows it read to `benches/<Block>/docs/design-analysis/library-inputs.json`.

## library-inputs.json (the one file this library reads from a blocks repo)
A JSON list, one object per row read (from `lib.used_inputs()`):

| Field | Meaning |
|---|---|
| `input` | `<Value>:<key>`, or `<Value>[<catalog value>]:<key>` for a selected capacitor, or `<Variant>:<key>` for a variant |
| `value` | the Value (directory name) |
| `key` | the row key |
| `dir` | the part directory relative to this repo's root, e.g. `components/Murata/GCM188` (used when it holds a `component.toml`; else the label is looked up by name) |

`python3 tools/review.py --block <Block> --blocks-repo <path>` (or `CIRCUIT_BLOCKS=<path>`) narrows the review page to
those rows. There is no default path. The file is written by the blocks repo, never by this one.
