"""Validate a spring table against the project schema.

The rules here mirror data/README.md. When the data dictionary changes, this
file changes with it -- the two are meant to be read side by side.

Exit code 0 when the file is clean, 1 when any error is found. Warnings do not
fail the run, because a missing optional measurement is normal, not broken.

Usage:
    python src/validate.py data/raw/osm_springs.csv
    python src/validate.py data/raw/field_2026_04.csv --strict
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# Project bounding box. A point outside this is almost always transposed
# lat/lon, which is the single most common error in a hand-entered
# geospatial table.
LAT_RANGE = (42.80, 43.60)
LON_RANGE = (76.30, 77.50)

REQUIRED = ("lat", "lon", "source_type", "access", "measured_at", "data_source", "confidence")

ENUMS = {
    "source_type": {"spring", "captured_spring", "well", "unknown"},
    "access": {"public", "restricted", "unknown"},
    "discharge_method": {"bucket", "weir", "estimate"},
    "flow_state": {"flowing", "trickle", "dry", "unknown"},
    "confidence": {"verified", "reported", "candidate"},
    "data_source": {"osm", "field", "kazhydromet", "2gis", "local_report", "literature"},
}

NUMERIC_RANGES = {
    "lat": LAT_RANGE,
    "lon": LON_RANGE,
    "elevation_m": (500, 4500),
    "discharge_l_min": (0, 2000),
    "water_temp_c": (-1, 30),
    "air_temp_c": (-40, 45),
    "ph": (4.0, 10.0),
    "tds_ppm": (0, 3000),
    "ec_us_cm": (0, 5000),
    "nitrate_mg_l": (0, 200),
}

SPRING_ID_RE = re.compile(r"^ALA-\d{4}$")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, row: int, message: str) -> None:
        self.errors.append(f"row {row}: {message}")

    def warn(self, row: int, message: str) -> None:
        self.warnings.append(f"row {row}: {message}")


def check_numeric(report: Report, line: int, field: str, raw: str) -> float | None:
    try:
        value = float(raw)
    except ValueError:
        report.error(line, f"{field}: {raw!r} is not a number")
        return None
    low, high = NUMERIC_RANGES[field]
    if not low <= value <= high:
        report.error(line, f"{field}: {value} outside expected range [{low}, {high}]")
    return value


def check_row(report: Report, line: int, row: dict, strict: bool) -> None:
    for field in REQUIRED:
        # measured_at is only required once a measurement exists; an OSM extract
        # legitimately has none.
        if field == "measured_at" and row.get("data_source") == "osm":
            continue
        if not (row.get(field) or "").strip():
            report.error(line, f"{field} is required and empty")

    spring_id = (row.get("spring_id") or "").strip()
    if spring_id and not SPRING_ID_RE.match(spring_id):
        report.error(line, f"spring_id: {spring_id!r} does not match ALA-####")
    if not spring_id and strict:
        report.error(line, "spring_id is empty (required under --strict)")

    for field, allowed in ENUMS.items():
        value = (row.get(field) or "").strip()
        if value and value not in allowed:
            report.error(line, f"{field}: {value!r} not in {sorted(allowed)}")

    for field in NUMERIC_RANGES:
        value = (row.get(field) or "").strip()
        if value:
            check_numeric(report, line, field, value)

    measured_at = (row.get("measured_at") or "").strip()
    if measured_at:
        try:
            parsed = datetime.fromisoformat(measured_at)
        except ValueError:
            report.error(line, f"measured_at: {measured_at!r} is not ISO 8601")
        else:
            if parsed.tzinfo is None:
                report.warn(line, "measured_at has no UTC offset; assume +05:00?")

    confidence = (row.get("confidence") or "").strip()
    has_chemistry = any(
        (row.get(f) or "").strip() for f in ("ph", "tds_ppm", "nitrate_mg_l", "water_temp_c")
    )
    if has_chemistry and confidence != "verified":
        report.error(
            line,
            f"chemistry present but confidence={confidence!r}; "
            "measurements imply a site visit",
        )

    if (row.get("water_temp_c") or "").strip() and not (row.get("air_temp_c") or "").strip():
        report.warn(line, "water_temp_c without air_temp_c cannot be interpreted")

    if (row.get("discharge_l_min") or "").strip() and not (
        row.get("discharge_method") or ""
    ).strip():
        report.error(line, "discharge_l_min present without discharge_method")


def check_duplicates(report: Report, rows: list[dict]) -> None:
    """Flag coordinates repeated to 5 decimals with no shared spring_id.

    Two visits to one spring share a spring_id and are expected. The same point
    under two different ids means the deduplication step was missed.
    """
    seen: dict[tuple[str, str], tuple[int, str]] = {}
    for line, row in enumerate(rows, start=2):
        key = ((row.get("lat") or "").strip(), (row.get("lon") or "").strip())
        if not all(key):
            continue
        spring_id = (row.get("spring_id") or "").strip()
        if key in seen:
            first_line, first_id = seen[key]
            if spring_id != first_id:
                report.warn(
                    line,
                    f"coordinates duplicate row {first_line} "
                    f"(ids {first_id or 'empty'!r} vs {spring_id or 'empty'!r})",
                )
        else:
            seen[key] = (line, spring_id)


def summarise(rows: list[dict]) -> None:
    print(f"  rows: {len(rows)}")
    for field in ("confidence", "source_type", "data_source", "flow_state"):
        counts = Counter((r.get(field) or "empty").strip() or "empty" for r in rows)
        rendered = ", ".join(f"{k}={v}" for k, v in counts.most_common())
        print(f"  {field}: {rendered}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="CSV file to validate")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also require spring_id on every row (use after identifiers are assigned)",
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(f"No such file: {args.path}", file=sys.stderr)
        return 1

    with args.path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        header = reader.fieldnames or []

    print(f"Validating {args.path}")

    unknown = [c for c in header if c not in _schema_columns()]
    if unknown:
        print(f"  note: columns not in the schema: {unknown}")

    report = Report()
    for line, row in enumerate(rows, start=2):  # line 1 is the header
        check_row(report, line, row, args.strict)
    check_duplicates(report, rows)

    summarise(rows)

    if report.warnings:
        print(f"\n{len(report.warnings)} warning(s):")
        for message in report.warnings[:40]:
            print(f"  ! {message}")
        if len(report.warnings) > 40:
            print(f"  ... and {len(report.warnings) - 40} more")

    if report.errors:
        print(f"\n{len(report.errors)} error(s):")
        for message in report.errors[:40]:
            print(f"  x {message}")
        if len(report.errors) > 40:
            print(f"  ... and {len(report.errors) - 40} more")
        return 1

    print("\nOK")
    return 0


def _schema_columns() -> set[str]:
    return {
        "spring_id",
        "name_local",
        "name_translit",
        "lat",
        "lon",
        "elevation_m",
        "source_type",
        "access",
        "discharge_l_min",
        "discharge_method",
        "water_temp_c",
        "air_temp_c",
        "ph",
        "tds_ppm",
        "ec_us_cm",
        "nitrate_mg_l",
        "turbidity_note",
        "flow_state",
        "measured_at",
        "observer",
        "data_source",
        "confidence",
        "osm_id",
        "notes",
    }


if __name__ == "__main__":
    sys.exit(main())
