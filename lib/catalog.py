"""Write a capacitor series catalog.csv from a manufacturer product-list export.

    python3 -m lib.catalog murata-gcm <vendor csv> <component dir> [--dielectrics X7R,C0G]

The component directory name gives the size and thickness code (GCM155: size 15, thickness 5; GCM21A: size 21,
thickness A). The allowed dielectrics default to the keys of `[part] tc_param` in the directory's component.toml, so a
dielectric without a temperature-characteristic row is never written. Every kept export row is decoded from its part
number and compared with the export's own columns; any mismatch is an error and that row is not written.

The decode tables below are a CROSS-CHECK ONLY, "Not a DS rule": the Murata reference sheets decode just their own
example part number (DS p.2). Where each code comes from is stated at its table. A row that passes proves only that the
export is consistent with itself and with these tables; it does not prove the tables are Murata's rules.
"""

import csv
import re
import sys
import tomllib
from decimal import Decimal
from pathlib import Path

from .capacitor import CATALOG_COLUMNS, parse_capacitance, parse_tolerance, parse_voltage, tol_key

# Part number: GCM <size 2> <thickness 1> <dielectric 2> <voltage 2> <capacitance 3> <tolerance 1> <individual 3> <#>
# "#" is the placeholder for the package letter (the export lists the part without it).
CAP_CODE_RE = re.compile(r"[0-9]{3}|[0-9]R[0-9]|R[0-9]{2}")
PART_RE = re.compile(r"GCM([0-9]{2})([0-9A-Z])([0-9A-Z]{2})([0-9A-Z]{2})([0-9RA-Z]{3})([A-Z])([0-9A-Z]{3})#")

# Size code -> (length mm, width mm) nominal. Printed in the reference sheets: 15 = 1.0 x 0.5 (GCM155), 18 = 1.6 x 0.8
# (GCM188) (DS p.2, Type & Dimension). The others are the standard EIA chip sizes as published by Murata; each agrees
# with the nominal Length and Width columns of every export row (checked on every row).
SIZE = {"15": ("1", "0.5"), "18": ("1.6", "0.8"), "21": ("2", "1.25"), "31": ("3.2", "1.6"), "32": ("3.2", "2.5")}
# Thickness code -> nominal thickness mm. DS p.2: 5 = 0.5 mm (GCM155), 8 = 0.8 mm (GCM188). Others: Murata's published
# thickness codes, checked against the nominal Thickness column of every export row.
THICKNESS = {"5": "0.5", "6": "0.6", "8": "0.8", "9": "0.85", "A": "1", "B": "1.25", "C": "1.6", "D": "2", "E": "2.5",
             "M": "1.15", "Q": "1.5"}
# Dielectric code -> catalog dielectric name. DS p.2: R7 = X7R. 5C = C0G is Murata's published code; the export's
# "Temperature characteristics" column agrees on every row.
DIELECTRIC = {"5C": "C0G", "R7": "X7R"}
# Rated-voltage code -> volts. DS p.2: 1H = DC 50 V. The others are Murata's published codes; the export's
# "Rated Voltage DC" column agrees on every row (one voltage per code).
VOLTAGE = {"0E": "2.5", "0G": "4", "0J": "6.3", "1A": "10", "1C": "16", "1E": "25", "1H": "50", "1J": "63", "1K": "80",
           "2A": "100", "2E": "250", "2J": "630", "3A": "1000", "3B": "1250", "YA": "35"}
# Tolerance letter -> printed tolerance. DS p.2: K = +/-10 %. The others are Murata's published letters; the export's
# "Tolerance of capacitance" column agrees on every row (one tolerance per letter).
TOLERANCE = {"W": "+/-0.05pF", "B": "+/-0.1pF", "C": "+/-0.25pF", "D": "+/-0.5pF", "F": "+/-1%", "G": "+/-2%",
             "J": "+/-5%", "K": "+/-10%", "M": "+/-20%", "R": "+/-2.5%"}

# Operating temperature the export must print. The shared op_temp_<dielectric> rows of the GCM155/GCM188 directories
# (DS p.2, Operating Temp. Range) are -55 to 125 degC and the Zener ambient check uses them for every catalog row, so a
# row printing another range (the export also lists -55 to 150 degC parts) is an error until it has its own row.
OPERATING_TEMPERATURE = "-55\uff5e125\u2103"

PRINTED_FIELDS = ("Operating Temperature", "Part Number", "Product Status", "Length", "Width", "Thickness", "Temperature characteristics",
                  "Capacitance", "Tolerance of capacitance", "Rated Voltage DC")


def nominal_mm(text):
    """Nominal Decimal from '0.5mm +/-0.05mm' or '1mm +0mm/-0.3mm' (the number before the first 'mm')."""
    m = re.match(r"\s*([0-9.]+)\s*mm", text)
    if not m:
        raise ValueError(f"'{text}' is not a '<number>mm ...' dimension")
    return Decimal(m.group(1))


def capacitance_code(code):
    """Capacitance in pF (Decimal) from a 3-character code: two digits and a power of ten ('104' = 10 x 10^4 pF), or
    with R as the decimal point ('1R5' = 1.5 pF, 'R50' = 0.5 pF)."""
    if "R" in code:
        return Decimal(code.replace("R", ".", 1))
    return Decimal(code[:2]) * Decimal(10) ** int(code[2])


def decode(row, offline=False):
    """Mismatch texts for one export row (empty list = the part number agrees with every column it encodes).

    offline=True is the half that needs only catalog.csv columns (dielectric, voltage, capacitance, tolerance,
    thickness): the export-only length, width and operating temperature are skipped. row then uses the export's column
    names ("Temperature characteristics", "Rated Voltage DC", "Capacitance", "Tolerance of capacitance", "Thickness");
    see catalog_row_problems.
    """
    number = row["Part Number"]
    m = PART_RE.fullmatch(number)
    if not m:
        return [f"part number '{number}' does not have the form GCM<size><T><dielectric><voltage><C><tol><spec>#"]
    size, thick, diel, volt, cap, tol, _spec = m.groups()
    problems = []

    def need(ok, text):
        if not ok:
            problems.append(text)

    try:
        if size not in SIZE:
            problems.append(f"size code {size} is not in the decode table")
        elif not offline:
            length, width = SIZE[size]
            need(nominal_mm(row["Length"]) == Decimal(length), f"size {size} gives length {length} mm, export says '{row['Length']}'")
            need(nominal_mm(row["Width"]) == Decimal(width), f"size {size} gives width {width} mm, export says '{row['Width']}'")
        if thick not in THICKNESS:
            problems.append(f"thickness code {thick} is not in the decode table")
        else:
            need(nominal_mm(row["Thickness"]) == Decimal(THICKNESS[thick]),
                 f"thickness code {thick} gives {THICKNESS[thick]} mm, export says '{row['Thickness']}'")
    except ValueError as e:
        problems.append(str(e))
    need(DIELECTRIC.get(diel) is not None, f"dielectric code {diel} is not in the decode table")
    need(DIELECTRIC.get(diel) == row["Temperature characteristics"],
         f"dielectric code {diel} gives {DIELECTRIC.get(diel)}, export says '{row['Temperature characteristics']}'")
    try:
        need(volt in VOLTAGE, f"rated-voltage code {volt} is not in the decode table")
        need(volt in VOLTAGE and Decimal(VOLTAGE[volt]) == Decimal(str(parse_voltage(row["Rated Voltage DC"]))),
             f"rated-voltage code {volt} gives {VOLTAGE.get(volt)} V, export says '{row['Rated Voltage DC']}'")
        if not CAP_CODE_RE.fullmatch(cap):
            problems.append(f"capacitance code '{cap}' is not 3 digits or R-decimal")
        else:
            printed = Decimal(str(parse_capacitance(row["Capacitance"]))) / Decimal("1e-12")
            need(capacitance_code(cap) == printed, f"capacitance code {cap} gives {capacitance_code(cap)} pF, "
                                                   f"export says '{row['Capacitance']}'")
    except ValueError as e:
        problems.append(str(e))
    if not offline:
        need(row["Operating Temperature"] == OPERATING_TEMPERATURE,
             f"operating temperature '{row['Operating Temperature']}' is not the -55 to 125 degC of the shared rows")
    need(tol in TOLERANCE, f"tolerance letter {tol} is not in the decode table")
    try:
        need(tol in TOLERANCE and tol_key(TOLERANCE[tol]) == tol_key(row["Tolerance of capacitance"]),
             f"tolerance letter {tol} gives {TOLERANCE.get(tol)}, export says '{row['Tolerance of capacitance']}'")
        parse_tolerance(row["Tolerance of capacitance"])
    except ValueError as e:
        problems.append(str(e))
    return problems


def catalog_row_problems(row, folder_name):
    """Mismatch texts for one committed catalog row (lib.capacitor.CatalogRow) of directory `folder_name` (GCM155):
    the offline decode of its value, plus the size+thickness code against the directory name. lib.check runs this on
    every row of a catalog whose [part] says catalog_decoder = "murata-gcm"."""
    fields = {"Part Number": row.value + "#", "Temperature characteristics": row.dielectric,
              "Capacitance": row.capacitance, "Tolerance of capacitance": row.tolerance,
              "Rated Voltage DC": row.rated_voltage, "Thickness": row.thickness}
    problems = decode(fields, offline=True)
    if row.value[3:6] != folder_name[3:]:
        problems.append(f"size+thickness code {row.value[3:6]} differs from the directory '{folder_name}'")
    return problems


def build_rows(export_rows, code, dielectrics, export_name):
    """(catalog rows, error texts, skip counts) for the export rows of one size+thickness code ('155') and dielectrics.

    Rows of other size/thickness codes or other dielectrics (by the export's own column) are skipped and counted; a
    kept row that fails decode() or repeats a part number is an error and is not written.
    """
    rows, errors, seen = [], [], set()
    skipped = {"other size/thickness": 0, "other dielectric": 0, "not In Production": 0}
    for r in export_rows:
        number = r.get("Part Number", "")
        if number[3:6] != code:
            skipped["other size/thickness"] += 1
        elif r.get("Temperature characteristics") not in dielectrics:
            skipped["other dielectric"] += 1
        elif r.get("Product Status") != "In Production":
            skipped["not In Production"] += 1
        else:
            problems = decode(r)
            if number in seen:
                problems.append("part number appears more than once in the export")
            seen.add(number)
            if problems:
                errors += [f"{number}: {p}" for p in problems]
                continue
            rows.append({"value": number[:-1], "dielectric": r["Temperature characteristics"],
                         "capacitance": r["Capacitance"], "tolerance": r["Tolerance of capacitance"],
                         "rated_voltage": r["Rated Voltage DC"], "thickness": r["Thickness"],
                         "source": f"Murata product list export {export_name}, row {number}"})
    rows.sort(key=lambda x: x["value"])
    return rows, errors, skipped


def write_catalog(path, rows):
    """catalog.csv: UTF-8, LF line ends, the columns of lib.capacitor.CATALOG_COLUMNS."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CATALOG_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv):
    if len(argv) < 3 or argv[0] != "murata-gcm":
        print(__doc__)
        return 2
    export, folder, extra = Path(argv[1]), Path(argv[2]), argv[3:]
    code = folder.name[3:]
    if not re.fullmatch(r"GCM[0-9]{2}[0-9A-Z]", folder.name):
        print(f"ERROR: directory '{folder.name}' is not GCM<size 2 digits><thickness code>")
        return 1
    toml = tomllib.loads((folder / "component.toml").read_text(encoding="utf-8"))
    if extra[:1] == ["--dielectrics"] and len(extra) == 2:
        dielectrics = extra[1].split(",")
    else:
        dielectrics = list(toml.get("part", {}).get("tc_param", {}))
    if not dielectrics:
        print("ERROR: no dielectrics: give --dielectrics or a [part] tc_param table in component.toml")
        return 1
    with open(export, newline="", encoding="utf-8-sig") as f:  # the export starts with a byte order mark
        reader = csv.DictReader(f)
        missing = [c for c in PRINTED_FIELDS if c not in (reader.fieldnames or [])]
        if missing:
            print(f"ERROR: export lacks columns {missing}")
            return 1
        export_rows = list(reader)
    rows, errors, skipped = build_rows(export_rows, code, set(dielectrics), export.name)
    for e in errors:
        print(f"ERROR: {e}")
    if errors:  # never overwrite a good catalog with a partial one
        print(f"{len(errors)} errors: catalog not written", file=sys.stderr)
        return 1
    write_catalog(folder / toml["part"].get("catalog", "catalog.csv"), rows)
    by = {d: sum(r["dielectric"] == d for r in rows) for d in dielectrics}
    print(f"{folder.name}: wrote {len(rows)} rows ({', '.join(f'{d} {n}' for d, n in by.items())}); "
          f"skipped {', '.join(f'{n} {k}' for k, n in skipped.items())}; {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
