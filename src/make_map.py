"""Render the spring inventory as a standalone HTML map.

Produces one self-contained file that opens in any browser with no server and
no Python environment. Written with the standard library only, for the same
reason as exif_gps.py: a collaborator should be able to look at the data
without first installing a geospatial stack.

Field sites are drawn as numbered markers; the OpenStreetMap layer is drawn
beneath them as small circles so the visited sites can be read against the
regional background rather than in isolation.

Usage:
    python src/make_map.py --out reports/map.html
    python src/make_map.py --field data/field/springs_2026-10-25.csv --no-osm
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import statistics
import sys
from pathlib import Path

LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"
LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"

# Analytes shown in a site's popup, in order, with the unit to print.
CHEMISTRY = [
    ("ph", "pH", ""),
    ("hardness", "Hardness", " mg/L CaCO3"),
    ("sulfate", "Sulfate", " mg/L"),
    ("copper", "Copper", " mg/L"),
    ("turbidity", "Turbidity", " NTU"),
    ("chlorine", "Chlorine", " mg/L"),
]

# Analytes deliberately not shown as values. Each was produced by a method
# that cannot support one -- see the laboratory sections of the README. The
# map says so rather than omitting them, because a reader who knows nitrite
# was measured should be told why no number appears.
UNUSABLE = {
    "nitrite": "measured on a high-range method",
    "ammonium": "measured on a 2-47 mg/L test",
    "iron": "no method recorded",
}

# Readings from a second method on a single sample are not replicates.
SECONDARY_METHODS = {"hach_cuvette_test_barcoded"}

SOURCE_COLOURS = {
    "spring": "#2a7fb8",
    "captured_spring": "#4aa3c7",
    "well": "#8a6fb0",
    "unknown": "#9aa3ab",
}


def load(path: Path) -> list[dict]:
    """Rows that carry a position. For tables that do not, use read_rows."""
    return [r for r in read_rows(path) if r.get("lat") and r.get("lon")]


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_chemistry(paths: list[Path]) -> dict[str, dict[str, object]]:
    """Mean of the replicates per spring and analyte, plus the unusable flags."""
    gathered: dict[str, dict[str, list[float]]] = {}
    censored: set[tuple[str, str]] = set()
    nondetect: dict[tuple[str, str], int] = {}
    counts: dict[tuple[str, str], int] = {}

    for path in paths:
        for row in read_rows(path):
            if row.get("method") in SECONDARY_METHODS:
                continue
            spring, analyte = row.get("spring_id", ""), row.get("analyte", "")
            try:
                value = float(row["value"])
            except (KeyError, ValueError):
                continue
            gathered.setdefault(spring, {}).setdefault(analyte, []).append(value)
            key = (spring, analyte)
            counts[key] = counts.get(key, 0) + 1
            if row.get("below_lod") == "true":
                nondetect[key] = nondetect.get(key, 0) + 1
            if "TOP OF SCALE" in (row.get("notes") or ""):
                censored.add(key)

    out: dict[str, dict[str, object]] = {}
    for spring, analytes in gathered.items():
        entry: dict[str, object] = {}
        for analyte, values in analytes.items():
            if analyte in UNUSABLE:
                entry[analyte] = {"unusable": UNUSABLE[analyte]}
                continue
            key = (spring, analyte)
            mean = sum(values) / len(values)
            entry[analyte] = {
                "mean": round(mean, 3),
                "censored": key in censored,
                # Every reading below the limit means the analyte was simply
                # not detected, which is a result and is shown as such.
                "nondetect": nondetect.get(key, 0) == counts.get(key, 0),
            }
        out[spring] = entry
    return out


def notes_dict(row: dict) -> dict[str, str]:
    return dict(
        part.split("=", 1)
        for part in (row.get("notes") or "").split("; ")
        if "=" in part
    )


def to_feature(row: dict, kind: str, chemistry: dict | None = None) -> dict:
    notes = notes_dict(row)
    return {
        "chem": (chemistry or {}).get(row.get("spring_id", ""), {}),
        "water_temp": row.get("water_temp_c") or "",
        "air_temp": row.get("air_temp_c") or "",
        "id": row.get("spring_id") or "",
        "name": row.get("name_local") or "",
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
        "elev": row.get("elevation_m") or "",
        "type": row.get("source_type") or "unknown",
        "confidence": row.get("confidence") or "",
        "osm": row.get("osm_id") or "",
        "photos": notes.get("photos", ""),
        "folder": notes.get("folder", ""),
        "measured": (row.get("measured_at") or "")[:16].replace("T", " "),
        "kind": kind,
    }


def elevation_summary(field: list[dict], osm: list[dict]) -> str:
    def values(rows: list[dict]) -> list[int]:
        out = []
        for r in rows:
            try:
                out.append(int(float(r["elevation_m"])))
            except (KeyError, ValueError, TypeError):
                continue
        return out

    f = values(field)
    o = values(osm)
    if not f:
        return ""

    parts = [
        f"Visited sites span {min(f)}&ndash;{max(f)} m "
        f"(median {int(statistics.median(f))} m)."
    ]
    if o:
        parts.append(
            f" The {len(o)} mapped features span {min(o)}&ndash;{max(o)} m "
            f"(median {int(statistics.median(o))} m)."
        )
        below = sum(1 for v in o if v < min(f))
        above = sum(1 for v in o if v > max(f))
        parts.append(
            f" {below} sit below that band and {above} above it, so the visited"
            " sites are not a cross-section of the region&rsquo;s springs"
            " &mdash; they are a sample from its middle elevations."
        )
    return "".join(parts)


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Almaty Springs</title>
<link rel="stylesheet" href="{css}">
<style>
  :root {{
    --bg: #ffffff; --fg: #1b1f23; --muted: #5b646d;
    --panel: #ffffffee; --border: #d8dee4; --accent: #c2410c;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #0f1216; --fg: #e6eaef; --muted: #9aa3ab;
      --panel: #161b22ee; --border: #30363d; --accent: #fb923c;
    }}
  }}
  :root[data-theme="dark"] {{
    --bg: #0f1216; --fg: #e6eaef; --muted: #9aa3ab;
    --panel: #161b22ee; --border: #30363d; --accent: #fb923c;
  }}
  html, body {{ margin: 0; height: 100%; background: var(--bg); color: var(--fg);
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  #map {{ position: absolute; inset: 0; }}
  .panel {{
    position: absolute; z-index: 1000; top: 12px; left: 12px; max-width: 330px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px 14px; backdrop-filter: blur(6px);
  }}
  .panel h1 {{ font-size: 15px; margin: 0 0 6px; }}
  .panel p {{ margin: 6px 0 0; color: var(--muted); font-size: 12.5px; }}
  .legend {{ margin-top: 10px; display: grid; gap: 4px; }}
  .legend div {{ display: flex; align-items: center; gap: 7px; font-size: 12.5px; }}
  .dot {{ width: 11px; height: 11px; border-radius: 50%; flex: none; }}
  .pin {{ width: 15px; height: 15px; border-radius: 50%; flex: none;
    background: var(--accent); border: 2px solid #fff; box-shadow: 0 0 0 1px #0004; }}
  .marker-label {{
    background: var(--accent); color: #fff; border: 2px solid #fff;
    border-radius: 50%; width: 24px; height: 24px; line-height: 20px;
    text-align: center; font-size: 11px; font-weight: 700;
    box-shadow: 0 1px 4px #0006;
  }}
  .leaflet-popup-content {{ font-size: 13px; }}
  .leaflet-popup-content b {{ font-size: 13.5px; }}
  .leaflet-popup-content code {{ font-size: 12px; }}
  .leaflet-popup-content table.chem {{
    margin: 7px 0 2px; border-collapse: collapse; font-size: 12.5px;
  }}
  .chem td {{ padding: 1px 0; }}
  .chem td:first-child {{ padding-right: 12px; color: var(--muted); }}
  .chem .muted {{ color: var(--muted); font-style: italic; }}
  @media (max-width: 600px) {{ .panel {{ max-width: calc(100% - 40px); }} }}
</style>
</head>
<body>
<div id="map"></div>
<div class="panel">
  <h1>Almaty Springs</h1>
  <p>{visited} visited site{plural} (numbered) against {mapped} features from
     OpenStreetMap.</p>
  <p>{summary}</p>
  <div class="legend">
    <div><span class="pin"></span> Visited and sampled</div>
    {legend}
  </div>
</div>
<script src="{js}"></script>
<script>
const FIELD = {field_json};
const OSM = {osm_json};
const COLOURS = {colours_json};
const CHEMISTRY = {chemistry_json};

const map = L.map('map', {{ scrollWheelZoom: true }});
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 18,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}}).addTo(map);

const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g,
  c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]);

const osmLayer = L.layerGroup();
for (const f of OSM) {{
  L.circleMarker([f.lat, f.lon], {{
    radius: 4, weight: 1, color: '#fff', opacity: 0.7,
    fillColor: COLOURS[f.type] || COLOURS.unknown, fillOpacity: 0.85
  }}).bindPopup(
      '<b>' + esc(f.name || 'Unnamed') + '</b><br>' + esc(f.type) +
      (f.elev ? '<br>' + esc(f.elev) + ' m' : '') +
      (f.osm ? '<br><a target="_blank" rel="noopener" href="https://www.openstreetmap.org/' +
        esc(f.osm) + '">' + esc(f.osm) + '</a>' : '')
    ).addTo(osmLayer);
}}
osmLayer.addTo(map);

const fieldLayer = L.layerGroup();
FIELD.forEach((f, i) => {{
  const rows = [];
  if (f.name) rows.push('<i>' + esc(f.name) + '</i>');
  rows.push(esc(f.lat.toFixed(5)) + ', ' + esc(f.lon.toFixed(5)));
  if (f.elev) rows.push('Elevation ' + esc(f.elev) + ' m (DEM)');
  if (f.water_temp) rows.push('Water ' + esc(f.water_temp) + ' &deg;C, air '
    + esc(f.air_temp) + ' &deg;C');
  if (f.photos) rows.push(esc(f.photos) + ' photographs');
  if (f.measured) rows.push('Visited ' + esc(f.measured));
  if (f.folder) rows.push('Folder <code>' + esc(f.folder) + '</code>');
  rows.push(f.osm
    ? 'In OSM: <a target="_blank" rel="noopener" href="https://www.openstreetmap.org/' +
      esc(f.osm) + '">' + esc(f.osm) + '</a>'
    : '<b>Not mapped in OSM</b>');

  const chem = [];
  for (const [key, label, unit] of CHEMISTRY) {{
    const c = f.chem[key];
    if (!c) continue;
    let text;
    if (c.nondetect) text = 'not detected';
    else text = (c.censored ? '&ge;' : '') + c.mean + unit;
    chem.push('<tr><td>' + esc(label) + '</td><td><b>' + text + '</b></td></tr>');
  }}
  for (const key of Object.keys(f.chem)) {{
    const c = f.chem[key];
    if (!c || !c.unusable) continue;
    chem.push('<tr><td>' + esc(key) + '</td><td class="muted">no result &mdash; '
      + esc(c.unusable) + '</td></tr>');
  }}
  if (chem.length) {{
    rows.push('<table class="chem">' + chem.join('') + '</table>');
  }}

  L.marker([f.lat, f.lon], {{
    icon: L.divIcon({{ className: '', iconSize: [24, 24], iconAnchor: [12, 12],
      html: '<div class="marker-label">' + (i + 1) + '</div>' }}),
    zIndexOffset: 1000
  }}).bindPopup('<b>' + esc(f.id) + '</b><br>' + rows.join('<br>')).addTo(fieldLayer);
}});
fieldLayer.addTo(map);

L.control.layers(null, {{
  'Visited sites': fieldLayer,
  'OpenStreetMap features': osmLayer
}}, {{ collapsed: false, position: 'topright' }}).addTo(map);

const all = FIELD.concat(OSM).map(f => [f.lat, f.lon]);
const bounds = FIELD.length ? FIELD.map(f => [f.lat, f.lon]) : all;

// Fitting bounds against a container that has not been laid out yet leaves
// the map centred on nothing: Leaflet measures zero and zooms accordingly.
// That happens whenever the page starts hidden -- in a tab opened in the
// background, in an iframe, in a pane that is sized after load. Re-measure
// once the window has settled, and again whenever it changes size.
function fitToSites() {{
  map.invalidateSize();
  map.fitBounds(bounds, {{ padding: [60, 60] }});
}}
fitToSites();
window.addEventListener('load', fitToSites);
// On resize only re-measure: refitting would undo the reader's own panning.
window.addEventListener('resize', () => map.invalidateSize());
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--field",
        type=Path,
        nargs="*",
        help="field CSV(s); default: every CSV in data/field/",
    )
    parser.add_argument(
        "--osm", type=Path, default=Path("data/raw/osm_springs.csv"), help="OSM extract"
    )
    parser.add_argument("--no-osm", action="store_true", help="omit the OSM layer")
    parser.add_argument("--out", type=Path, default=Path("reports/map.html"))
    args = parser.parse_args()

    field_paths = args.field or sorted(Path("data/field").glob("springs_*.csv"))
    if not field_paths:
        print("No field CSV found in data/field/.", file=sys.stderr)
        return 1

    field_rows: list[dict] = []
    for path in field_paths:
        if not path.exists():
            print(f"Missing: {path}", file=sys.stderr)
            return 1
        field_rows.extend(load(path))

    osm_rows: list[dict] = []
    if not args.no_osm:
        if args.osm.exists():
            osm_rows = load(args.osm)
        else:
            print(f"No OSM extract at {args.osm} -- drawing field sites only.")
            print("Build it with: python src/fetch_osm_springs.py")

    lab_paths = sorted(Path("data/field").glob("lab_results_*.csv"))
    chemistry = load_chemistry(lab_paths) if lab_paths else {}

    field = [to_feature(r, "field", chemistry) for r in field_rows]
    osm = [to_feature(r, "osm") for r in osm_rows]
    field.sort(key=lambda f: f["id"])

    present = sorted({f["type"] for f in osm})
    legend = "\n    ".join(
        f'<div><span class="dot" style="background:{SOURCE_COLOURS.get(t, "#9aa3ab")}">'
        f"</span> {html.escape(t.replace('_', ' '))} (OSM)</div>"
        for t in present
    )

    page = TEMPLATE.format(
        css=LEAFLET_CSS,
        js=LEAFLET_JS,
        visited=len(field),
        plural="" if len(field) == 1 else "s",
        mapped=len(osm),
        summary=elevation_summary(field_rows, osm_rows),
        legend=legend,
        field_json=json.dumps(field, ensure_ascii=False),
        osm_json=json.dumps(osm, ensure_ascii=False),
        colours_json=json.dumps(SOURCE_COLOURS),
        chemistry_json=json.dumps(CHEMISTRY, ensure_ascii=False),
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page, encoding="utf-8")

    print(f"Wrote {args.out}  ({len(page) / 1024:.0f} KB)")
    print(f"  {len(field)} visited site(s), {len(osm)} OSM feature(s)")
    unmapped = [f["id"] for f in field if not f["osm"]]
    if unmapped:
        print(f"  not in OSM: {', '.join(unmapped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
