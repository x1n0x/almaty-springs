"""Fetch spring features in the Almaty region from the Overpass API.

Writes a CSV conforming to the project schema (see data/README.md) plus a
sidecar .meta.json recording the query, bounding box, endpoint and timestamp,
so that any downstream figure can be traced to the extract it came from.

Usage:
    python src/fetch_osm_springs.py --out data/raw/osm_springs.csv
    python src/fetch_osm_springs.py --out data/raw/wide.csv --bbox 42.8 76.3 43.6 77.5
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# Northern slope of the Ile-Alatau plus the Almaty urban area.
# (south, west, north, east) in WGS84 degrees.
DEFAULT_BBOX = (42.80, 76.30, 43.60, 77.50)

ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

# Columns from the canonical schema that this source can populate.
# Everything else is written empty and filled by field work.
FIELDNAMES = [
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
]

QUERY_TEMPLATE = """
[out:json][timeout:{timeout}];
(
  node["natural"="spring"]({bbox});
  way["natural"="spring"]({bbox});
  node["amenity"="drinking_water"]({bbox});
  node["man_made"="water_tap"]({bbox});
  node["man_made"="water_well"]({bbox});
);
out center tags;
"""

# OSM tags -> schema source_type. Order matters: first match wins.
SOURCE_TYPE_RULES = (
    ("natural", "spring", "spring"),
    ("man_made", "water_well", "well"),
    ("man_made", "water_tap", "captured_spring"),
    ("amenity", "drinking_water", "unknown"),
)


def build_query(bbox: tuple[float, float, float, float], timeout: int) -> str:
    return QUERY_TEMPLATE.format(bbox=",".join(str(v) for v in bbox), timeout=timeout)


def fetch(query: str, timeout: int, retries: int = 3) -> dict:
    """POST the query, trying each endpoint with exponential backoff.

    The public Overpass endpoints are shared and rate-limited; a 429 or 504 is
    routine rather than exceptional, so it is retried rather than raised.
    """
    last_error: Exception | None = None
    for endpoint in ENDPOINTS:
        for attempt in range(retries):
            try:
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    timeout=timeout + 30,
                    headers={"User-Agent": "almaty-springs/0.1 (research project)"},
                )
                if response.status_code in (429, 504):
                    wait = 5 * (2**attempt)
                    print(
                        f"  {endpoint} returned {response.status_code}, "
                        f"retrying in {wait}s",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:  # noqa: PERF203
                last_error = exc
                print(f"  {endpoint}: {exc}", file=sys.stderr)
                time.sleep(2 * (attempt + 1))
        print(f"  giving up on {endpoint}", file=sys.stderr)
    raise RuntimeError(f"all Overpass endpoints failed; last error: {last_error}")


def classify(tags: dict) -> str:
    for key, value, source_type in SOURCE_TYPE_RULES:
        if tags.get(key) == value:
            return source_type
    return "unknown"


def access_of(tags: dict) -> str:
    value = tags.get("access")
    if value in ("yes", "public", "permissive"):
        return "public"
    if value in ("private", "no", "customers"):
        return "restricted"
    return "unknown"


def flow_state_of(tags: dict) -> str:
    """OSM has no discharge field, but `intermittent=yes` is a real signal."""
    if tags.get("intermittent") == "yes":
        return "unknown"
    return ""


def notes_of(tags: dict) -> str:
    """Carry across tags that matter but have no schema column of their own."""
    interesting = ("drinking_water", "intermittent", "description", "note", "operator")
    parts = [f"{k}={tags[k]}" for k in interesting if tags.get(k)]
    return "; ".join(parts)


def to_rows(payload: dict) -> list[dict]:
    rows: list[dict] = []
    for element in payload.get("elements", []):
        # Nodes carry lat/lon directly; ways queried with `out center` carry it
        # under `center`.
        if "lat" in element and "lon" in element:
            lat, lon = element["lat"], element["lon"]
        elif "center" in element:
            lat, lon = element["center"]["lat"], element["center"]["lon"]
        else:
            continue

        tags = element.get("tags", {})
        osm_id = f"{element['type']}/{element['id']}"

        row = dict.fromkeys(FIELDNAMES, "")
        row.update(
            {
                # spring_id is deliberately left empty. Identifiers are assigned
                # once, after deduplication, by the inventory notebook -- not here,
                # where a re-run would renumber everything and invalidate every
                # field notebook reference.
                "name_local": tags.get("name", ""),
                "name_translit": tags.get("name:en", ""),
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "source_type": classify(tags),
                "access": access_of(tags),
                "flow_state": flow_state_of(tags),
                "data_source": "osm",
                "confidence": "reported" if tags.get("name") else "candidate",
                "osm_id": osm_id,
                "notes": notes_of(tags),
            }
        )
        rows.append(row)
    return rows


def write_csv(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_meta(out: Path, query: str, bbox, endpoint_list, row_count: int) -> None:
    meta = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "bbox_south_west_north_east": list(bbox),
        "endpoints_tried": list(endpoint_list),
        "query": query.strip(),
        "row_count": row_count,
        "schema": "data/README.md",
        "licence": "Derived from OpenStreetMap, (c) OpenStreetMap contributors, ODbL 1.0",
    }
    out.with_suffix(".meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/raw/osm_springs.csv"),
        help="output CSV path (default: data/raw/osm_springs.csv)",
    )
    parser.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("SOUTH", "WEST", "NORTH", "EAST"),
        default=DEFAULT_BBOX,
        help="bounding box in WGS84 degrees",
    )
    parser.add_argument("--timeout", type=int, default=180, help="Overpass timeout, s")
    args = parser.parse_args()

    bbox = tuple(args.bbox)
    query = build_query(bbox, args.timeout)

    print(f"Querying Overpass for springs in bbox {bbox}")
    payload = fetch(query, args.timeout)

    rows = to_rows(payload)
    if not rows:
        print("No features returned. Check the bounding box.", file=sys.stderr)
        return 1

    write_csv(rows, args.out)
    write_meta(args.out, query, bbox, ENDPOINTS, len(rows))

    by_type: dict[str, int] = {}
    for row in rows:
        by_type[row["source_type"]] = by_type.get(row["source_type"], 0) + 1

    print(f"Wrote {len(rows)} rows to {args.out}")
    for source_type, count in sorted(by_type.items(), key=lambda kv: -kv[1]):
        print(f"  {source_type:18} {count}")
    print(f"Provenance: {args.out.with_suffix('.meta.json')}")
    print()
    print("Note: these are unverified locations. Nothing here is `verified`")
    print("until a site visit confirms it -- see data/README.md section 2.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
