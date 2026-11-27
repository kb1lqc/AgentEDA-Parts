#!/usr/bin/env python3
"""Record an agent review of a part (docs/spec/agent-review.md); logic in lib/agent_review.py.

Usage (repo root), run by the orchestrator after the reviewer returned its report, never by the reviewer:
  python3 tools/agent_review.py record <Value> --role verifier|adversarial --model <id> --findings N --applied N
      --logged N --report <report file> [--rows-checked N] [--clean] [--root R]
Writes review/agent_review.toml: hashes of the part's inputs, of the report and of the datasheet PDF, the rows that
matter, the scope offered to the reviewer. --rows-checked N is required for the verifier and forbidden for
the adversarial role: how many of the reference rows in scope it checked (the tool stores the total; N = total is full). Zero findings needs --clean. An accountability record, not proof.
Exit 0 = written, 1 = refused (nothing written).
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import agent_review  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tools/agent_review.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record", help="write one role's entry")
    r.add_argument("value", metavar="Value", help="component directory name (components/<Mfr>/<Value>/)")
    r.add_argument("--role", required=True, help="verifier or adversarial")
    r.add_argument("--model", required=True, help="model id of the reviewer")
    r.add_argument("--findings", type=int, required=True)
    r.add_argument("--applied", type=int, required=True)
    r.add_argument("--logged", type=int, required=True)
    r.add_argument("--report", required=True, metavar="PATH", help="the reviewer's returned findings file")
    r.add_argument("--rows-checked", type=int, default=None, help="verifier only: reference rows checked")
    r.add_argument("--clean", action="store_true", help="zero findings")
    r.add_argument("--root", default=Path(__file__).resolve().parent.parent)
    a = ap.parse_args(argv)
    try:
        f = agent_review.record(Path(a.root).resolve(), a.value, a.role, a.model, a.findings, a.applied, a.logged,
                                a.report, a.clean, rows_checked=a.rows_checked)
    except ValueError as e:
        print(f"refused: {e}")
        return 1
    print(f"wrote {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
