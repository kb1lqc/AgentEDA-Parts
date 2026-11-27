# Brief: adversarial reviewer (Sonnet, electrical + software)

READ-ONLY. You receive: this brief's path, the datasheet PDF path, the component directory (or the lib diff), and a
scratch dir (your only writable place).

Load exactly these files:
- `docs/spec/extract.md`, plus `docs/spec/wrapper.md` for the Zener check review
- the component's `component.toml`, `calc.py`, generated `<Value>.zen` and `tests/test_zen.py` CASES for it
- one more only if the part is a family, resistor series or capacitor series (`family.md`, `series.md`,
  `capacitor.md`)

Hunt, with evidence from the page images (`pdftoppm -r 150 -png -f N -l N <pdf> <scratch>/p`, then Read the PNG):
1. Re-derive every `calc.py` equation from the datasheet; run the functions and the `EXAMPLES`.
2. Conventions that mislead worst-case analysis: one-sided ± values, sign errors, % / ppm units, typ used as a
   bound, curve values as bounds, wrong scope.
3. Zener check selection: a pin the circuit sets but left unchecked, a part-driven pin checked, a wrong reference
   pin, a derate applied on the wrong side.
4. Spot-check 10 or more high-impact numbers (supply limits, input ranges, thermal, accuracy rows) against the images.
5. Run `python3 -m lib.check` and `python3 -m unittest discover -s tests` and report failures.
6. Final step: report findings to the orchestrator as `severity | file:line | problem | evidence | fix`; the orchestrator applies those that cite the DS or spec and lists the rest in the PR description as open items; nothing is committed. Item 1 covers every calc.py function.

Report, one finding per line, sorted by severity:
`severity | file:line | problem | evidence | exact fix`. A finding without page or code evidence is not a finding.
End with the list of numbers you spot-checked and the pages you rendered.

Stop and return: datasheet missing or unreadable; two sources contradict and you cannot tell which governs.
