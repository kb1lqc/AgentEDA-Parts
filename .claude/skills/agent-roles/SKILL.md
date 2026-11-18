---
name: agent-roles
description: Mandatory agent ideology for all electronics design work in this designer's repos (spec development, part research and library data, option studies, worst-case analysis, Zener blocks and benches, schematics, reviews) - the main session orchestrates and owns every decision and verification, cheap (Haiku) subagents do the well-specified work, a fresh read-only agent verifies, Sonnet only for spatial work or deep adversarial review. Accuracy first, then lowest token use. Use at the start of every circuit, block, board, library-part or analysis task, including discussion-only spec turns, before reading datasheets or library files yourself.
---

# Agent roles (always on)

Applies to every phase: spec discussion, library and datasheet research, option studies, analysis, Zener code,
schematics, reviews. Priority order: **accuracy, then low token use, then speed.** Engineering rules are `ee-design`;
schematic-specific jobs (placement, pre-flight) are in `schematic-capture`; library-part roles are in the library's
CLAUDE.md. This skill is the default they all share.

## Schematic first (default for every agent)
Work is schematic-phase unless the designer says layout has started: no PCB placement, routing, `pcb layout`,
`.kicad_pcb` files, copper or stackup work, and no agent brief may ask for it. The only footprint work allowed is
in the component library (a part's `.kicad_mod`). Physical needs found by analysis (copper area for a thermal
resistance, current-path width) are recorded as layout requirements or open items in the spec, never acted on.
Every brief states "schematic phase: no layout work".

## Who does what
| Job | Who | Why |
|---|---|---|
| Decisions with the designer, engineering judgment (which rows are bounds, what limits what, trade-offs), briefs, final numbers check, skill/memory updates | main session | owns context and judgment; the designer talks only to it |
| Reading library entries / datasheets and returning the rows, equations and cites a question needs | Haiku | mechanical extraction; returns a compact table, not the files |
| First draft of a scratch option-study script from an exact brief (inputs by library key, model, outputs) | Haiku | checkable by running it |
| Spec text from a decisions brief, Zener modules and benches, `analysis.py`, params, notes, file moves, toolchain probes | Haiku | well specified, checked by build, tests and gates |
| Independent verification of any deliverable (numbers trace to library/analysis, ports, gates rerun) | a fresh read-only Haiku, never the author | independence beats size |
| Schematic pre-flight and placement generator; deep adversarial review (re-derive equations, hunt unit/sign/typ-as-bound errors) | Sonnet (at most two at once) | spatial or deep reasoning where Haiku proved weak |

The main session does NOT bulk-read datasheets, component TOMLs or long source files itself, and does not hand-write
analysis code longer than a few lines. It reads agent summaries, runs the result, and spot-checks the top
contributors and every number it will present.

## Accuracy rules
- Every number an agent returns comes with its library key or DS cite; the main session re-runs any script whose
  numbers it presents (numbers come from runs, never from an agent's prose or arithmetic).
- Every deliverable that leaves the session (spec, code, analysis, sheet) gets a fresh verifier before it is shown.
  Verifiers report defects only: `severity | file:line | problem | evidence | fix`.
- Engineering judgment calls stay in the main session: an agent that meets one reports it with options instead of
  deciding.

## Token rules
- **The best step is no step.** Do only the work a good design and its analysis need; skip optional extras,
  re-checks that add nothing, polish and refactors nobody asked for. This applies to the main session and every agent
  brief (say it in the brief).
- Spawn only when it saves tokens or adds independence: a lookup of one or two short commands is cheaper inline.
  Batch related questions into one agent; parallelize only independent work.
- Brief once, completely: absolute paths, the skills to read (by path, `~/.claude/skills/<name>/SKILL.md`), files it
  may write (one writer per file), the gates that define done, the scratch directory, and the exact return format.
- Agents return a summary plus paths, never full files, logs or renders; the main session opens only what it must
  check.
- Resume an agent that stopped (send it a message) instead of spawning a replacement that redoes the work.
- Reuse committed tools (`tools/`, library `lib/`) instead of letting each agent rebuild helpers.

## Standard flow for a new block (example)
1. Main: decisions with the designer; Haiku: library/DS extraction for the candidate parts.
2. Haiku: option-study script from the main session's brief; main: runs it, judges, presents, records decisions.
3. Haiku: spec draft from the decisions brief; fresh Haiku verifier; main: final read; designer approves.
4. Parallel Haiku: Zener module + bench (until `pcb build -Dwarnings` passes) and `analysis.py` + params (until the
   datasheet generates). Fresh verifier on both; main reruns the gates.
5. Schematic per `schematic-capture` (Sonnet placement, fresh adversarial review).
