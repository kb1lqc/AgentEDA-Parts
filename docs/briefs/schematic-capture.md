# Brief: schematic capture

Role: capture a schematic from Zener into arranged KiCad sheets in one pass, no layout. You receive this path, the bench path, a scratch dir, writable files.

Load only (from circuit-blocks, `.claude/skills/...` and `docs/...` are under `../zener-library/`; `tools/schematic/README.md` is its own):
- `.claude/skills/schematic-style/SKILL.md`
- `docs/spec/pcb-toolchain.md`
- `tools/schematic/README.md`
- the block's `spec.md` and its `values.json`

Models: pre-flight, generator Sonnet; code, notes, analysis changes Haiku; reviewer fresh Sonnet, not the drafter.

Phases:
1. Decisions (ask once): names, ports, rails, port net types, hierarchy, label convention, ERC exceptions, title fields, notes and boxes per sheet; the spec must hold every note number.
2. Freeze code: `pcb build -Dwarnings` exit 0; delete `.kicad_sch` files, apply twice (second unchanged). No placement before this. Check support-part returns against the datasheet figure image.
3. Pre-flight (text only): pin-group sides, rail vs ground pins, forced crossings, label pitch, support parts; resolve conflicts by schematic-style rule or ask; output a placement table.
4. Generator: one parametric re-runnable script computes every coordinate from `pin_point`; no hand nudging; never hard-code the instance prefix (stamping rewrites it). Output byte-identical on rerun; prove changes on copies.
5. Annotate per the schematic-style checklist; numbers only from spec or report.

Gates before review: `python3 tools/verify.py --schematic <bench>` (apply twice, netlist diff, classified ERC, overlap; temp copies) and `python3 tools/verify.py` (build, `check_sync.sh` IN SYNC); hand-added items survive apply.

Reviewer: checks renders (sheet, zoomed crops) against checklist and decisions, and note numbers against the spec; returns `sheet | location | rule | evidence | fix`. Results: renders, gates, ERC exceptions, open items.

If committed files are damaged, stop and report; never run `git checkout`, `restore`, `stash` or `reset`. State what was tried before claiming a tool limit, else "not confirmed".

Re-check tool-limit claims; re-review changes only. Return summary and artifact paths, never logs.
