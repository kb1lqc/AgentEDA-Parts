"""Capacitor series: the catalog file, printed-value parsing and part selection (docs/SPEC.md, "Capacitor series").

A capacitor series directory holds one `catalog.csv` row per orderable value. This module reads it, turns the
printed capacitance / tolerance / rated voltage into SI numbers and picks one part by (capacitance, rated voltage,
dielectric, optional tolerance). The Zener generator and the lookup key it builds live in lib/zen.py; the key
arithmetic is shared here so Python and Zener agree.
"""

import csv
import hashlib
import math
import re
import tomllib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .param import Param

CATALOG_COLUMNS = ["value", "dielectric", "capacitance", "tolerance", "rated_voltage", "thickness", "source"]
# Keys the part selection adds to the loaded Part (rows of component.toml may not use them).
SELECTION_KEYS = ("capacitance", "tolerance", "rated_v", "tc")

_FARAD = {"pF": Decimal("1e-12"), "nF": Decimal("1e-9"), "uF": Decimal("1e-6"), "μF": Decimal("1e-6"),
          "µF": Decimal("1e-6")}  # Greek mu and micro sign: both occur in the wild
# Digits with well-formed thousands separators ("6,800", "1,000,000") or plain digits; "1,2,3" is rejected.
_NUMBER = r"([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)"


def _decimal(text, what):
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        raise ValueError(f"{what} '{text}' is not a number") from None


def parse_capacitance(text):
    """Capacitance in F from a printed value: '100pF', '0.1μF' (or uF), '6,800pF', '1nF'."""
    m = re.fullmatch(_NUMBER + r"\s*(pF|nF|uF|μF|µF)", str(text).strip())
    if not m:
        raise ValueError(f"capacitance '{text}' is not <number>pF|nF|uF")
    return float(_decimal(m.group(1), "capacitance") * _FARAD[m.group(2)])


def parse_voltage(text):
    """Rated DC voltage in V from a printed value: '50Vdc', '1,000Vdc', '6.3Vdc', '50V'."""
    m = re.fullmatch(_NUMBER + r"\s*V(?:dc|DC)?", str(text).strip())
    if not m:
        raise ValueError(f"rated voltage '{text}' is not <number>V or <number>Vdc")
    return float(_decimal(m.group(1), "rated voltage"))


def parse_tolerance(text):
    """('rel', fraction) for '+/-10%' / '±10%', or ('abs', farad) for '+/-0.25pF'. Symmetric tolerances only."""
    m = re.fullmatch(r"(?:±|\+/-)\s*([0-9][0-9.]*)\s*(%|pF)", str(text).strip())
    if not m:
        raise ValueError(f"tolerance '{text}' is not +/-<number>% or +/-<number>pF")
    number = _decimal(m.group(1), "tolerance")
    if m.group(2) == "%":
        return "rel", float(number / 100)
    return "abs", float(number * _FARAD["pF"])


def tol_key(text):
    """Tolerance text for matching: '±0.25pF' and '+/- 0.25 pF' both give '+/-0.25pf'."""
    return str(text).replace("±", "+/-").replace(" ", "").lower()


def ascii_text(text):
    """Printed text as ASCII: the plus-minus sign becomes '+/-', Greek mu or micro sign 'u' (for the Zener wrapper)."""
    return str(text).replace("±", "+/-").replace("μ", "u").replace("µ", "u")


def zen_key(c_farad, v_volt):
    """(integer femtofarad, integer millivolt): the dict key Python and the Zener wrapper both compute the same way."""
    return int(c_farad * 1e15 + 0.5), int(v_volt * 1e3 + 0.5)


@dataclass
class CatalogRow:
    """One catalog.csv row: printed text plus the parsed numbers (SI)."""

    value: str  # MPN without the package letter
    dielectric: str
    capacitance: str  # as printed
    tolerance: str  # as printed
    rated_voltage: str  # as printed
    thickness: str  # as printed
    source: str  # cite of the row
    c: float  # F
    v: float  # V
    tol_kind: str  # "rel" (tol is a fraction) or "abs" (tol is farad)
    tol: float

    def tolerance_fraction(self):
        """Tolerance as a fraction of the capacitance (an absolute pF tolerance is divided by C)."""
        return self.tol if self.tol_kind == "rel" else self.tol / self.c

    def label(self):
        return f"{self.value} ({self.capacitance}, {self.rated_voltage}, {self.tolerance}, {self.dielectric})"


def read_catalog(path):
    """List of CatalogRow from a catalog.csv. ValueError listing every problem (columns, parse errors, duplicates)."""
    path = Path(path)
    if not path.exists():
        raise ValueError(f"catalog not found: {path}")
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != CATALOG_COLUMNS:
            raise ValueError(f"{path.name}: columns must be exactly {CATALOG_COLUMNS}, found {reader.fieldnames}")
        raw = list(reader)
    rows, problems, seen = [], [], set()
    for n, r in enumerate(raw, start=2):  # line 1 is the header
        where = f"{path.name} line {n} ({r.get('value')})"
        empty = [c for c in CATALOG_COLUMNS if not (r.get(c) or "").strip()]
        if empty:
            problems.append(f"{where}: empty {', '.join(empty)}")
            continue
        try:
            kind, tol = parse_tolerance(r["tolerance"])
            row = CatalogRow(**r, c=parse_capacitance(r["capacitance"]), v=parse_voltage(r["rated_voltage"]),
                             tol_kind=kind, tol=tol)
        except ValueError as e:
            problems.append(f"{where}: {e}")
            continue
        if row.value in seen:
            problems.append(f"{where}: value appears more than once")
        seen.add(row.value)
        rows.append(row)
    if problems:
        raise ValueError("\n".join(problems))
    return rows


def choose(rows, capacitance, rated_voltage, dielectric, tolerance=None):
    """The one CatalogRow matching the request. ValueError for no match or an ambiguous match (the text says why).

    capacitance (F) and rated_voltage (V) are numbers or printed text ('0.1uF', '50Vdc'); numbers match to 1e-9
    relative. tolerance is printed text ('+/-10%') or None (any).
    """
    c = capacitance if isinstance(capacitance, (int, float)) else parse_capacitance(capacitance)
    v = rated_voltage if isinstance(rated_voltage, (int, float)) else parse_voltage(rated_voltage)
    request = f"{c:g} F, {v:g} V, {dielectric}" + (f", tolerance {tolerance}" if tolerance else "")
    same_dielectric = [r for r in rows if r.dielectric == dielectric]
    if not same_dielectric:
        raise ValueError(f"no catalog part for {request}: dielectric '{dielectric}' is not in the catalog "
                         f"({', '.join(sorted({r.dielectric for r in rows}))})")
    same_c = [r for r in same_dielectric if math.isclose(r.c, c, rel_tol=1e-9)]
    same_cv = [r for r in same_c if math.isclose(r.v, v, rel_tol=1e-9)]
    found = [r for r in same_cv if tolerance is None or tol_key(r.tolerance) == tol_key(tolerance)]
    if not found:
        if not same_c:
            hint = f"the catalog has no {dielectric} part with that capacitance"
        elif not same_cv:
            hint = "rated voltages for that capacitance: " + ", ".join(sorted({r.rated_voltage for r in same_c}))
        else:
            hint = "tolerances for that capacitance and voltage: " + ", ".join(sorted({r.tolerance for r in same_cv}))
        raise ValueError(f"no catalog part for {request}; {hint}")
    if len(found) > 1:
        tols = sorted({r.tolerance for r in found})
        advice = f"pass tolerance= one of {', '.join(tols)}" if tolerance is None and len(tols) > 1 \
            else "the catalog lists several values for it"
        raise ValueError(f"ambiguous: {len(found)} catalog parts match {request}: "
                         f"{', '.join(r.value for r in found)}; {advice}")
    return found[0]


def export_stamp_date(folder, catalog_path, dielectric):
    """Date of the human export-check stamp of one dielectric group (review/export_check.toml, docs/spec/capacitor.md
    "Export check"), or None: no record, no stamp for the group, or a record made from another catalog.csv (stale)."""
    try:
        with open(Path(folder) / "review" / "export_check.toml", "rb") as fh:
            record = tomllib.load(fh)
        catalog_sha = hashlib.sha256(Path(catalog_path).read_bytes()).hexdigest()
    except (OSError, tomllib.TOMLDecodeError):
        return None
    if record.get("catalog", {}).get("sha256") != catalog_sha:
        return None
    verified = record.get("group", {}).get(dielectric, {}).get("verified") or ""
    m = re.fullmatch(r"human:\S+ (\d{4}-\d{2}-\d{2}) export-check group \S+", verified)
    return m[1] if m else None


def selection_params(row, stamp_date=None):
    """(capacitance, tolerance, rated_v) Params for one catalog row, SI. The row's `source` is their cite. stamp_date: the
    date of the group's human export-check stamp (export_stamp_date); None means the values are unverified."""
    delta = row.c * row.tolerance_fraction()
    # Machine-readable manufacturer export, parsed by tested code: no person or model transcribed these numbers. The
    # `verified` stamp says so (method) and is dated by the human stamp of the group; no stamp -> unverified (fail safe).
    verified = (f"manufacturer-export {stamp_date} machine-readable product list parsed by lib.catalog, no transcription"
                if stamp_date else None)
    note = "From the manufacturer catalog (catalog.csv), not a datasheet table. " \
           "Excludes DC-bias, aging and temperature effects: see calc.capacitance_worst_pct / _ppm."
    capacitance = Param(min=row.c - delta, typ=row.c, max=row.c + delta, unit="F", name="Capacitance", symbol="C",
                        kind="electrical", scope="25C", conditions=f"Printed {row.capacitance}, {row.tolerance}",
                        cite=row.source, note=note, verified=verified)
    frac = row.tolerance_fraction()
    tolerance = Param(min=-frac, max=frac, unit="1", name="Capacitance tolerance", kind="electrical", scope="25C",
                      conditions=f"Printed {row.tolerance}" + (" (absolute, divided by C)" if row.tol_kind == "abs" else ""),
                      cite=row.source, note=note, verified=verified)
    rated = Param(min=-row.v, max=row.v, unit="V", name="Rated voltage (DC)", kind="rec_op", scope="na",
                  conditions="Voltage between the two terminals (non-polarized; either polarity)", cite=row.source,
                  note=f"Printed {row.rated_voltage} with no MIN/MAX label; stored symmetric because the part is "
                       "non-polarized.", verified=verified)
    return capacitance, tolerance, rated
