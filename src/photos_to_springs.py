"""Turn a folder of geotagged field photographs into a spring table.

Photographs taken at one outlet cluster within a few metres of each other, so
nearby photos are grouped into a single spring and the group's median position
is used. The median rather than the mean: one photo taken from the car park
should not drag the outlet's coordinates halfway there.

Rows come out as `confidence=candidate` by design. A photograph proves someone
stood somewhere, not that the thing photographed is a spring, and promoting a
row to `verified` is a decision a person makes while looking at the picture --
see data/README.md section 2.

Usage:
    python src/photos_to_springs.py "D:/springs photos" --out data/raw/from_photos.csv
    python src/photos_to_springs.py ./photos --out out.csv --group-radius 80
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from exif_gps import ExifError, PhotoLocation, read_location  # noqa: E402

FIELDNAMES = [
    "spring_id", "name_local", "name_translit", "lat", "lon", "elevation_m",
    "source_type", "access", "discharge_l_min", "discharge_method",
    "water_temp_c", "air_temp_c", "ph", "tds_ppm", "ec_us_cm", "nitrate_mg_l",
    "turbidity_note", "flow_state", "measured_at", "observer", "data_source",
    "confidence", "osm_id", "notes",
]

# .heic / .heif hold EXIF in an ISO-BMFF container, not a JPEG APP1 segment.
# They are listed so the report can tell the user to export them as JPEG
# rather than silently ignoring half their photographs.
JPEG_SUFFIXES = {".jpg", ".jpeg", ".jpe", ".tif", ".tiff"}
UNSUPPORTED_SUFFIXES = {".heic", ".heif", ".dng", ".cr2", ".nef", ".arw", ".png", ".webp"}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    r = 6371008.8  # mean Earth radius, metres
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return 2 * r * asin(sqrt(a))


def group_photos(
    photos: list[PhotoLocation], radius_m: float
) -> list[list[PhotoLocation]]:
    """Single-link clustering: a photo joins a group it comes within radius of.

    Single-link is right here because photographs of one outlet form a chain of
    close points, and the alternative -- a fixed grid -- would split a spring
    whose photos straddle a cell boundary.
    """
    groups: list[list[PhotoLocation]] = []
    for photo in sorted(photos, key=lambda p: (p.lat, p.lon)):
        for group in groups:
            if any(
                haversine_m(photo.lat, photo.lon, other.lat, other.lon) <= radius_m
                for other in group
            ):
                group.append(photo)
                break
        else:
            groups.append([photo])
    return groups


def scan(folder: Path) -> tuple[list[PhotoLocation], list[tuple[Path, str]]]:
    located: list[PhotoLocation] = []
    problems: list[tuple[Path, str]] = []

    files = sorted(p for p in folder.rglob("*") if p.is_file())
    for path in files:
        suffix = path.suffix.lower()
        if suffix in UNSUPPORTED_SUFFIXES:
            problems.append((path, f"{suffix} is not readable by this script"))
            continue
        if suffix not in JPEG_SUFFIXES:
            continue
        try:
            photo = read_location(path)
        except ExifError as exc:
            problems.append((path, str(exc)))
            continue
        except OSError as exc:
            problems.append((path, f"could not read file: {exc}"))
            continue

        if photo.has_position:
            located.append(photo)
        else:
            problems.append((path, "EXIF present but no GPS position"))

    return located, problems


def build_rows(groups: list[list[PhotoLocation]], start_id: int) -> list[dict]:
    rows: list[dict] = []
    for index, group in enumerate(groups):
        lat = statistics.median(p.lat for p in group)
        lon = statistics.median(p.lon for p in group)

        times = sorted(p.taken_at for p in group if p.taken_at)
        altitudes = [p.altitude_m for p in group if p.altitude_m is not None]
        cameras = sorted({p.camera for p in group if p.camera})
        dops = [p.gps_dop for p in group if p.gps_dop is not None]

        spread = 0.0
        if len(group) > 1:
            spread = max(
                haversine_m(lat, lon, p.lat, p.lon) for p in group
            )

        notes = [f"photos={len(group)}"]
        notes.append("files=" + "|".join(sorted(p.path.name for p in group)))
        if spread:
            notes.append(f"photo_spread_m={spread:.1f}")
        if altitudes:
            notes.append(f"gps_alt_m={statistics.median(altitudes):.0f}")
        if dops:
            notes.append(f"gps_dop={min(dops)}")
        if cameras:
            notes.append("camera=" + "/".join(cameras))

        row = dict.fromkeys(FIELDNAMES, "")
        row.update(
            {
                "spring_id": f"ALA-{start_id + index:04d}",
                "lat": f"{lat:.5f}",
                "lon": f"{lon:.5f}",
                # GPS altitude from a phone is barometric or satellite-derived
                # and routinely off by tens of metres, so it goes in notes and
                # elevation_m is left for enrich_elevation.py to fill from the DEM.
                "source_type": "unknown",
                "access": "unknown",
                "measured_at": times[0].isoformat() if times else "",
                "data_source": "field",
                "confidence": "candidate",
                "notes": "; ".join(notes),
            }
        )
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="folder of photographs (searched recursively)")
    parser.add_argument(
        "--out", type=Path, default=Path("data/raw/from_photos.csv"), help="output CSV"
    )
    parser.add_argument(
        "--group-radius",
        type=float,
        default=50.0,
        help="photos within this many metres are treated as one spring (default: 50)",
    )
    parser.add_argument(
        "--start-id", type=int, default=1, help="first ALA-#### number to assign"
    )
    args = parser.parse_args()

    if not args.folder.is_dir():
        print(f"Not a folder: {args.folder}", file=sys.stderr)
        return 1

    print(f"Scanning {args.folder}")
    located, problems = scan(args.folder)
    print(f"  {len(located)} photo(s) with GPS, {len(problems)} skipped")

    if not located:
        print("\nNo geotagged photographs found.", file=sys.stderr)
        if problems:
            print("Skipped files:", file=sys.stderr)
            for path, why in problems[:20]:
                print(f"  {path.name}: {why}", file=sys.stderr)
        return 1

    groups = group_photos(located, args.group_radius)
    rows = build_rows(groups, args.start_id)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{len(groups)} spring(s) from {len(located)} photo(s):")
    for row in rows:
        detail = row["notes"].split("; ")[0]
        stamp = row["measured_at"][:16] or "no timestamp"
        print(f"  {row['spring_id']}  {row['lat']}, {row['lon']}  {detail}  {stamp}")

    if problems:
        print(f"\nSkipped {len(problems)} file(s):")
        shown = problems[:15]
        for path, why in shown:
            print(f"  {path.name}: {why}")
        if len(problems) > len(shown):
            print(f"  ... and {len(problems) - len(shown)} more")
        if any(p.suffix.lower() in (".heic", ".heif") for p, _ in problems):
            print("\n  HEIC/HEIF photos need exporting as JPEG first.")
            print("  On iPhone: Settings > Camera > Formats > Most Compatible,")
            print("  or export copies as JPEG when downloading from the cloud.")

    print(f"\nWrote {args.out}")
    print("\nNext:")
    print(f"  python src/enrich_elevation.py {args.out} --backend api")
    print(f"  python src/validate.py {args.out}")
    print("\nEvery row is `candidate`. Review the photographs, set source_type")
    print("and access, then promote the real springs to `verified` by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
