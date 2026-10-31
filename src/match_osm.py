"""Match field-visited springs against the OpenStreetMap extract.

Answers two questions at once: which visited outlets are already mapped (so a
field record can carry its `osm_id`), and which are absent from OSM (so they
can be contributed back).

Matching is by distance alone. Names are not used: most OSM spring nodes here
are unnamed, and the few names that exist are inconsistently transliterated
between Kazakh and Russian, so a name comparison would reject true matches more
often than it would catch false ones.

Usage:
    python src/match_osm.py data/field/springs.csv --osm data/raw/osm_springs.csv
    python src/match_osm.py data/field/springs.csv --osm data/raw/osm_springs.csv --write
"""

from __future__ import annotations

import argparse
import csv
import sys
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

# Consumer GPS error is 5-10 m, and OSM nodes are often placed from imagery
# rather than survey. 60 m is wide enough to catch the same outlet recorded by
# two independent methods, narrow enough that two distinct outlets in one gorge
# are not merged. Matches are reported with their distance so the judgement
# stays visible rather than hidden behind the threshold.
DEFAULT_RADIUS_M = 60.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371008.8
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def load(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def nearest(row: dict, osm: list[dict]) -> tuple[float, dict] | None:
    try:
        lat, lon = float(row["lat"]), float(row["lon"])
    except (KeyError, ValueError):
        return None
    candidates = []
    for other in osm:
        try:
            candidates.append(
                (haversine_m(lat, lon, float(other["lat"]), float(other["lon"])), other)
            )
        except (KeyError, ValueError):
            continue
    return min(candidates, key=lambda t: t[0]) if candidates else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("field", type=Path, help="field spring CSV")
    parser.add_argument(
        "--osm", type=Path, default=Path("data/raw/osm_springs.csv"), help="OSM extract"
    )
    parser.add_argument(
        "--radius", type=float, default=DEFAULT_RADIUS_M, help="match radius, metres"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write matched osm_id back into the field CSV",
    )
    args = parser.parse_args()

    for path in (args.field, args.osm):
        if not path.exists():
            print(f"No such file: {path}", file=sys.stderr)
            return 1

    field = load(args.field)
    osm = load(args.osm)
    print(f"{len(field)} field site(s) against {len(osm)} OSM feature(s)\n")

    matched = 0
    unmatched: list[dict] = []

    for row in field:
        found = nearest(row, osm)
        label = f"{row.get('spring_id', '?')} {row.get('name_local', '')}".strip()
        if not found:
            print(f"{label}: no usable coordinates")
            continue
        distance, other = found
        if distance <= args.radius:
            matched += 1
            name = other.get("name_local") or "unnamed"
            print(f"{label}: {other['osm_id']} at {distance:.0f} m ({name})")
            if args.write:
                row["osm_id"] = other["osm_id"]
                note = (row.get("notes") or "").strip()
                addition = f"osm_match_m={distance:.0f}"
                row["notes"] = f"{note}; {addition}" if note else addition
        else:
            unmatched.append(row)
            print(f"{label}: not in OSM (nearest {distance:.0f} m)")

    print(f"\n{matched} matched, {len(unmatched)} not in OpenStreetMap")

    if unmatched:
        print("\nAbsent from OSM -- candidates to contribute back:")
        for row in unmatched:
            print(f"  {row['spring_id']}  {row['lat']}, {row['lon']}")
        print("\nOnly map outlets you have actually seen, and do not add any")
        print("that sit on private land. See docs/field_protocol.md section 10.")

    if args.write:
        with args.field.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(field[0].keys()))
            writer.writeheader()
            writer.writerows(field)
        print(f"\nUpdated {args.field}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
