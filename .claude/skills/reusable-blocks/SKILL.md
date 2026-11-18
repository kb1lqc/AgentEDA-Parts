---
name: reusable-blocks
description: Use when creating a circuit block, restructuring the blocks repository, or using blocks on a board: ports, versioning, per-instance analysis, sheet reuse.
---

# Reusable circuit blocks

A block is to a board what a library part is to a block: a versioned, analysed, reviewed unit pulled in by URL and pinned version, used unchanged. Engineering rules: `ee-design`. Drawing rules: `schematic-style`. Package layout, standard ports, versioning, per-instance analysis, stamping and the new-block checklist: `docs/spec/blocks.md` in the circuit-blocks repository. Mark any toolchain behaviour as "verify first" until a throwaway build confirms it for the current `pcb` version.

## Rules
- A block is a Zener module with role-named ports, all support parts inside (sense element, decoupling, terminations, DNP-selectable pull-ups), and design-intent configs (values, tolerances, DNP, `ambient`, `derate`).
- Topology is fixed: configs change values and DNP only. A different topology is a different block.
- Name the block after its limits (`INA229HighSideMonitor`, not `INA229Monitor`).
- Reuse the standard port names before inventing one; record each new standard name in `blocks.md`.
- Each block owns a worst-case analysis that any board runs with its own instance configs, and a reference schematic sheet arranged once, with notes true for every instance.
- Instance numbers go on the parent sheet (DESIGN VALUES box), never in the reference sheet.
- Never re-arrange a block's internals on a board. Fix the reference sheet in the blocks repository, release, re-stamp.
- Pin each block by tag; pin its analysis to the same tag and bump both together.
- Rename a repository named for one part before any board imports from it: the repository path is part of every import URL and tag.
- The board's top sheet is a block diagram; see `schematic-style`.
