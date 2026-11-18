---
name: agent-roles
description: Use at the start of every circuit, block, part, analysis or schematic task, including discussion-only turns, to decide which agent does what, who verifies, and how to brief subagents.
---

# Agent roles (always on)

Applies to every phase: spec discussion, research, option studies, analysis, Zener code, schematics, reviews. Priority: **accuracy, then low token use, then speed.** Engineering rules: `ee-design`. Schematic rules: `schematic-style`; the schematic workflow brief: `docs/briefs/schematic-capture.md`. Library-part roles: the library's `docs/briefs/`.

## Schematic first
Work is schematic phase until the designer says layout has started. Do no PCB placement, routing, `pcb layout`, `.kicad_pcb`, copper or stackup work. The only footprint work allowed is a library part's `.kicad_mod`. Record physical needs found by analysis (copper area for a thermal resistance, current-path width) as layout requirements or open items in the spec; never act on them. Every brief states "schematic phase: no layout work".

## Who does what
| Job | Who |
|---|---|
| Decisions with the designer, engineering judgment (which rows are bounds, trade-offs), briefs, final numbers check, skill and memory updates | main session |
| Read library entries or datasheets and return the rows, equations and cites a question needs (a compact table, not the files) | Haiku |
| First draft of a scratch option-study script from an exact brief | Haiku |
| Spec text from a decisions brief, Zener modules and benches, `analysis.py`, params, notes, file moves, toolchain probes | Haiku |
| Verification of any deliverable (numbers trace to library or analysis, ports, gates rerun) | fresh read-only Haiku, never the author |
| Schematic pre-flight and placement generator; deep adversarial review (re-derive equations, hunt unit, sign and typ-as-bound errors) | Sonnet |

- Haiku is the default. Sonnet only for spatial work or deep adversarial review; at most two Sonnet agents at once.
- The adversarial reviewer is Sonnet everywhere.
- The main session does not bulk-read datasheets, component TOMLs or long sources, and writes no analysis code longer than a few lines. It reads summaries, runs the result, and spot-checks the top contributors and every number it presents.

## Accuracy
- Every number an agent returns carries its library key or datasheet cite. Re-run any script whose numbers you present; numbers come from runs, never from agent prose or arithmetic.
- Every deliverable that leaves the session (spec, code, analysis, sheet) gets a fresh verifier first. Verifiers report defects only: `severity | file:line | problem | evidence | fix`.
- An agent that meets a judgment call reports it with options instead of deciding.
- Before reporting a limitation, state what was tried and the evidence; verify any "can't" with a second, differently designed test. Otherwise say "not confirmed".

## Tokens
- **The best step is no step.** Skip optional extras, re-checks that add nothing, and unrequested polish; say so in every brief.
- Spawn only when it saves tokens or adds independence; a one-or-two-command lookup is cheaper inline. Batch related questions; parallelize only independent work.
- Brief once, completely: absolute paths, the brief or skill paths to read, writable files (one writer per file), gates that define done, scratch directory, return format.
- Agents return a summary plus paths, never full files, logs or renders.
- Resume a stopped agent by message; do not spawn a replacement that redoes the work.
- Reuse committed tools (`tools/`, library `lib/`) instead of rebuilding helpers.
