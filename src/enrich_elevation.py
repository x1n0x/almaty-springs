"""Attach DEM elevation to spring coordinates.

Two backends:

  --backend api   Query the public OpenTopoData service. No download, no setup,
                  rate-limited to 1 call/second and 100 points per call. Good
                  for a few hundred points.

  --backend local Sample a local GeoTIFF with rasterio. Required for the
                  area-weighted elevation null model in RQ1, which samples the
                  whole bounding box and is far too large for an API.

Both write the `elevation_m` column in place, rounded to the metre. A DEM at
30 m resolution does not support sub-metre precision, and writing decimals
would imply accuracy the source does not have.

Usage:
    python src/enrich_elevation.py data/raw/osm_springs.csv --backend api
    python src/enrich_elevation.py data/raw/osm_springs.csv \
        --backend local --dem data/raw/copernicus_glo30_almaty.tif
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import requests

OPENTOPODATA_URL = "https://api.opentopodata.org/v1/{dataset}"
DEFAULT_DATASET = "srtm30m"
BATCH_SIZE = 100
RATE_LIMIT_SECONDS = 1.1  # the public endpoint allows 1 call/second


def read_rows(path: Path) -> tuple[list[dict], list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    if "elevation_m" not in fieldnames:
        raise SystemExit("input has no elevation_m column; is this a spring table?")
    return rows, fieldnames


def write_rows(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def coordinates_of(rows: list[dict]) -> list[tuple[int, float, float]]:
    """Return (index, lat, lon) for rows that need an elevation."""
    pending: list[tuple[int, float, float]] = []
    for index, row in enumerate(rows):
        if (row.get("elevation_m") or "").strip():
            continue  # already enriched; do not re-query
        try:
            lat = float(row["lat"])
            lon = float(row["lon"])
        except (KeyError, ValueError):
            print(f"  row {index + 2}: unusable coordinates, skipped", file=sys.stderr)
            continue
        pending.append((index, lat, lon))
    return pending


def fetch_api(
    pending: list[tuple[int, float, float]], dataset: str
) -> dict[int, float | None]:
    results: dict[int, float | None] = {}
    batches = [pending[i : i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]

    for number, batch in enumerate(batches, start=1):
        locations = "|".join(f"{lat},{lon}" for _, lat, lon in batch)
        print(f"  batch {number}/{len(batches)} ({len(batch)} points)")

        response = requests.post(
            OPENTOPODATA_URL.format(dataset=dataset),
            data={"locations": locations},
            timeout=60,
            headers={"User-Agent": "almaty-springs/0.1 (research project)"},
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("status") != "OK":
            raise SystemExit(f"OpenTopoData returned: {payload.get('error', payload)}")

        for (index, _, _), result in zip(batch, payload["results"], strict=True):
            results[index] = result.get("elevation")

        if number < len(batches):
            time.sleep(RATE_LIMIT_SECONDS)

    return results


def fetch_local(
    pending: list[tuple[int, float, float]], dem_path: Path
) -> dict[int, float | None]:
    try:
        import rasterio
    except ImportError:
        raise SystemExit(
            "the local backend needs rasterio: pip install -r requirements.txt"
        ) from None

    results: dict[int, float | None] = {}
    with rasterio.open(dem_path) as dem:
        if dem.crs is None:
            raise SystemExit(f"{dem_path} has no CRS; cannot sample it safely")
        if dem.crs.to_epsg() != 4326:
            raise SystemExit(
                f"{dem_path} is in EPSG:{dem.crs.to_epsg()}; reproject to EPSG:4326 "
                "first, or the lat/lon sampling below is meaningless"
            )
        nodata = dem.nodata
        # rasterio.sample takes (x, y) == (lon, lat), not (lat, lon). Getting
        # this backwards returns plausible numbers from the wrong place.
        points = [(lon, lat) for _, lat, lon in pending]
        for (index, _, _), sampled in zip(pending, dem.sample(points), strict=True):
            value = float(sampled[0])
            results[index] = None if nodata is not None and value == nodata else value
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="spring CSV to enrich in place")
    parser.add_argument(
        "--backend", choices=("api", "local"), default="api", help="elevation source"
    )
    parser.add_argument("--dem", type=Path, help="GeoTIFF path, required for --backend local")
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help=f"OpenTopoData dataset for --backend api (default: {DEFAULT_DATASET})",
    )
    args = parser.parse_args()

    if args.backend == "local" and not args.dem:
        parser.error("--backend local requires --dem")
    if not args.path.exists():
        parser.error(f"no such file: {args.path}")

    rows, fieldnames = read_rows(args.path)
    pending = coordinates_of(rows)

    if not pending:
        print("Every row already has an elevation. Nothing to do.")
        return 0

    print(f"Enriching {len(pending)} of {len(rows)} rows via {args.backend}")
    if args.backend == "api":
        elevations = fetch_api(pending, args.dataset)
        provenance = f"opentopodata:{args.dataset}"
    else:
        elevations = fetch_local(pending, args.dem)
        provenance = f"dem:{args.dem.name}"

    filled = 0
    missing = 0
    for index, elevation in elevations.items():
        if elevation is None:
            missing += 1
            continue
        rows[index]["elevation_m"] = str(round(elevation))
        note = (rows[index].get("notes") or "").strip()
        rows[index]["notes"] = f"{note}; elev_src={provenance}" if note else f"elev_src={provenance}"
        filled += 1

    write_rows(args.path, rows, fieldnames)

    print(f"Wrote {filled} elevations to {args.path}")
    if missing:
        print(f"{missing} point(s) returned no data (outside DEM coverage or nodata)")
    print(f"Provenance recorded in notes as elev_src={provenance}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
