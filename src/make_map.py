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

SOURCE_COLOURS = {
    "spring": "#2a7fb8",
    "captured_spring": "#4aa3c7",
    "well": "#8a6fb0",
    "unknown": "#9aa3ab",
}


def load(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [r for r in csv.DictReader(handle) if r.get("lat") and r.get("lon")]


def notes_dict(row: dict) -> dict[str, str]:
    return dict(
        part.split("=", 1)
        for part in (row.get("notes") or "").split("; ")
        if "=" in part
    )


def to_feature(row: dict, kind: str) -> dict:
    notes = notes_dict(row)
    return {
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
  if (f.photos) rows.push(esc(f.photos) + ' photographs');
  if (f.measured) rows.push('Visited ' + esc(f.measured));
  if (f.folder) rows.push('Folder <code>' + esc(f.folder) + '</code>');
  rows.push(f.osm
    ? 'In OSM: <a target="_blank" rel="noopener" href="https://www.openstreetmap.org/' +
      esc(f.osm) + '">' + esc(f.osm) + '</a>'
    : '<b>Not mapped in OSM</b>');

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
map.fitBounds(FIELD.length ? FIELD.map(f => [f.lat, f.lon]) : all, {{ padding: [60, 60] }});
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

    field_paths = args.field or sorted(Path("data/field").glob("*.csv"))
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

    field = [to_feature(r, "field") for r in field_rows]
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
