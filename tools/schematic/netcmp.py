"""Compare two KiCad netlists net by net (net names and node sets).

Usage: python3 tools/schematic/netcmp.py <baseline.net> <new.net>
Export a netlist with: kicad-cli sch export netlist --output <file>.net <root>.kicad_sch
Exit 0 when identical, 1 otherwise. Use after every `pcb apply` (see the schematic-style skill): apply can report
success while a hand-placed label was dropped.
"""

import re
import sys


def nets(path):
    text = open(path).read()
    out = {}
    for block in re.split(r"\n\s*\(net\n", text)[1:]:
        name = re.search(r'\(name "([^"]*)"\)', block).group(1)
        out[name] = sorted(re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', block))
    return out


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    a, b = nets(argv[0]), nets(argv[1])
    print(f"{len(a)} nets baseline; {len(b)} new")
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            print("DIFF", k, a.get(k), b.get(k))
    same = a == b
    print("IDENTICAL" if same else "MISMATCH")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
