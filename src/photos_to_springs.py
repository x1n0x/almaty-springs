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

PHOTO_SUFFIXES = {
    ".jpg", ".jpeg", ".jpe", ".tif", ".tiff",
    ".heic", ".heif", ".avif",  # iPhone default format
    ".png",                     # screenshots: usually a timestamp, no GPS
}
# Raw formats wrap TIFF in vendor containers; not worth supporting while every
# camera that produces them also writes a JPEG or HEIC alongside.
UNSUPPORTED_SUFFIXES = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".webp"}


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


def scan(
    folder: Path,
) -> tuple[list[PhotoLocation], list[PhotoLocation], list[tuple[Path, str]]]:
    """Return (photos with GPS, photos without GPS, unreadable files)."""
    located: list[PhotoLocation] = []
    no_gps: list[PhotoLocation] = []
    problems: list[tuple[Path, str]] = []

    files = sorted(p for p in folder.rglob("*") if p.is_file())
    for path in files:
        suffix = path.suffix.lower()
        if suffix in UNSUPPORTED_SUFFIXES:
            problems.append((path, f"{suffix} is not readable by this script"))
            continue
        if suffix not in PHOTO_SUFFIXES:
            continue
        try:
            photo = read_location(path)
        except ExifError as exc:
            problems.append((path, str(exc)))
            continue
        except OSError as exc:
            problems.append((path, f"could not read file: {exc}"))
            continue

        (located if photo.has_position else no_gps).append(photo)

    return located, no_gps, problems


def group_by_folder(
    photos: list[PhotoLocation], root: Path
) -> list[tuple[str, list[PhotoLocation]]]:
    """Group photos by the subfolder they sit in.

    When someone has already sorted their photographs into a folder per site,
    that grouping is better evidence than anything inferred from distance: it
    records what the photographer meant, and it keeps a shot taken on the
    approach in the right site instead of spawning a spurious one.
    """
    groups: dict[str, list[PhotoLocation]] = {}
    for photo in photos:
        try:
            relative = photo.path.relative_to(root)
        except ValueError:
            relative = photo.path
        label = relative.parts[0] if len(relative.parts) > 1 else root.name
        groups.setdefault(label, []).append(photo)
    return sorted(groups.items())


def build_rows(
    groups: list[tuple[str, list[PhotoLocation]]],
    start_id: int,
    extras: dict[str, list[PhotoLocation]] | None = None,
) -> list[dict]:
    extras = extras or {}
    rows: list[dict] = []
    for index, (label, group) in enumerate(groups):
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

        notes = [f"folder={label}", f"photos={len(group)}"]
        notes.append("files=" + "|".join(sorted(p.path.name for p in group)))
        companions = extras.get(label, [])
        if companions:
            notes.append(
                "no_gps=" + "|".join(sorted(p.path.name for p in companions))
            )
        if spread:
            notes.append(f"photo_spread_m={spread:.0f}")
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
                "name_local": label,
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
        "--group-by",
        choices=("folder", "distance"),
        default="folder",
        help="how to decide which photos belong to one spring (default: folder)",
    )
    parser.add_argument(
        "--group-radius",
        type=float,
        default=50.0,
        help="for --group-by distance: photos within this many metres are one spring",
    )
    parser.add_argument(
        "--start-id", type=int, default=1, help="first ALA-#### number to assign"
    )
    args = parser.parse_args()

    if not args.folder.is_dir():
        print(f"Not a folder: {args.folder}", file=sys.stderr)
        return 1

    print(f"Scanning {args.folder}")
    located, no_gps, problems = scan(args.folder)
    print(
        f"  {len(located)} photo(s) with GPS, "
        f"{len(no_gps)} without, {len(problems)} unreadable"
    )

    if not located:
        print("\nNo geotagged photographs found.", file=sys.stderr)
        for path, why in problems[:20]:
            print(f"  {path.name}: {why}", file=sys.stderr)
        return 1

    if args.group_by == "folder":
        groups = group_by_folder(located, args.folder)
        extras = {
            label: photos
            for label, photos in group_by_folder(no_gps, args.folder)
        }
        print(f"  grouped by folder: {len(groups)} site(s)")
    else:
        groups = [
            (f"group-{i + 1}", g)
            for i, g in enumerate(group_photos(located, args.group_radius))
        ]
        extras = {}
        print(f"  grouped within {args.group_radius:.0f} m: {len(groups)} site(s)")

    rows = build_rows(groups, args.start_id, extras)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{len(groups)} spring(s) from {len(located)} photo(s):")
    for row in rows:
        fields = dict(
            part.split("=", 1) for part in row["notes"].split("; ") if "=" in part
        )
        spread = fields.get("photo_spread_m")
        detail = f"{fields.get('photos', '?')} photos"
        if spread:
            detail += f", spread {spread} m"
        print(
            f"  {row['spring_id']}  {row['name_local']:12}  "
            f"{row['lat']}, {row['lon']}  {detail}  {row['measured_at'][:16]}"
        )

    if no_gps:
        print(f"\n{len(no_gps)} photo(s) without GPS, recorded per site in notes:")
        for photo in no_gps[:10]:
            stamp = photo.taken_at.isoformat()[:16] if photo.taken_at else "no time"
            print(f"  {photo.path.name}  {stamp}")

    if problems:
        print(f"\n{len(problems)} unreadable file(s):")
        for path, why in problems[:15]:
            print(f"  {path.name}: {why}")
        if len(problems) > 15:
            print(f"  ... and {len(problems) - 15} more")

    print(f"\nWrote {args.out}")
    print("\nNext:")
    print(f"  python src/enrich_elevation.py {args.out} --backend api")
    print(f"  python src/validate.py {args.out}")
    print("\nEvery row is `candidate`. Review the photographs, set source_type")
    print("and access, then promote the real springs to `verified` by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
