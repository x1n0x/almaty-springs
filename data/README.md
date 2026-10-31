# Data

This directory holds the project's data layers. **Raw and processed data are not
committed to version control.** Everything in `raw/` is reproducible from the
scripts in `src/`, and everything in `processed/` is reproducible from `raw/`.
Only the schema template and this documentation are tracked.

```
raw/        Unmodified source extracts. Never edited by hand.
interim/    Cleaned single-source tables, not yet joined.
processed/  Analysis-ready tables consumed by notebooks.
```

---

## 1. Canonical schema: the spring record

One row describes one observation at one spring. A spring visited three times
produces three rows sharing a `spring_id`. Static attributes (coordinates,
elevation) repeat; measured attributes differ.

`springs_template.csv` is this schema as an empty CSV. Copy it to start a new
collection file.

| Field | Type | Unit | Required | Allowed values / range | Notes |
|---|---|---|---|---|---|
| `spring_id` | string | — | yes | `ALA-####` | Project identifier, assigned once, never reused |
| `name_local` | string | — | no | free text | Name as locally used, Russian or Kazakh; empty if unnamed |
| `name_translit` | string | — | no | free text | Latin transliteration for search |
| `lat` | float | deg | yes | 42.8 to 43.6 | WGS84, 5 decimals (~1 m) |
| `lon` | float | deg | yes | 76.3 to 77.5 | WGS84, 5 decimals |
| `elevation_m` | int | m | no | 500 to 4500 | From DEM, not from a phone barometer |
| `source_type` | enum | — | yes | `spring`, `captured_spring`, `well`, `unknown` | `captured_spring` = built outlet, pipe or basin |
| `access` | enum | — | yes | `public`, `restricted`, `unknown` | `restricted` = private land or fenced |
| `discharge_l_min` | float | L/min | no | 0 to 2000 | Volumetric measurement, see field protocol |
| `discharge_method` | enum | — | no | `bucket`, `weir`, `estimate` | `estimate` rows excluded from quantitative discharge results |
| `water_temp_c` | float | degrees C | no | -1 to 30 | At the outlet, not downstream |
| `air_temp_c` | float | degrees C | no | -40 to 45 | Needed to interpret water temperature |
| `ph` | float | — | no | 4.0 to 10.0 | Field meter, calibrated same day |
| `tds_ppm` | int | ppm | no | 0 to 3000 | Total dissolved solids |
| `ec_us_cm` | int | microS/cm | no | 0 to 5000 | Electrical conductivity, if meter reports it |
| `nitrate_mg_l` | float | mg/L | no | 0 to 200 | Test-strip or colorimetric; indicative only |
| `turbidity_note` | string | — | no | free text | Visual description; no instrument |
| `flow_state` | enum | — | no | `flowing`, `trickle`, `dry`, `unknown` | Recorded even when discharge is not measured |
| `measured_at` | datetime | — | yes | ISO 8601 with offset | e.g. `2026-04-12T09:30:00+06:00` |
| `observer` | string | — | no | free text | Who took the measurement |
| `data_source` | string | — | yes | see below | Provenance of this row |
| `confidence` | enum | — | yes | `verified`, `reported`, `candidate` | See section 2 |
| `osm_id` | string | — | no | e.g. `node/123456789` | Link back to OSM when applicable |
| `notes` | string | — | no | free text | Anything the fields above cannot hold |

### `data_source` vocabulary

| Value | Meaning |
|---|---|
| `osm` | Extracted from OpenStreetMap via Overpass |
| `field` | Measured on site for this project |
| `kazhydromet` | From a Kazhydromet publication |
| `2gis` | Cross-referenced from 2GIS |
| `local_report` | Reported by a resident, not yet visited |
| `literature` | From a published paper or report, cited in `notes` |

---

## 2. The `confidence` field

This is the most important column in the dataset, and the one most likely to be
misused.

| Value | Criteria |
|---|---|
| `verified` | Visited in person. Coordinates recorded on site with GPS. Outlet observed flowing or dry, and that state recorded. |
| `reported` | Named in a source judged reliable (OSM with a recent survey date, a published report), but not visited by the project. |
| `candidate` | Mentioned somewhere, location approximate or unconfirmed. May not exist. |

Rules enforced in analysis code:

- Hydrochemical results use `verified` rows only.
- Spatial results may use `verified` and `reported`; any figure doing so states
  the mix in its caption.
- `candidate` rows are a work queue, not data. They never enter a result.

A `candidate` that turns out not to exist is not deleted. Its `flow_state` is set
to `dry` or its `notes` record the negative finding, because absence is
information and silently dropping it biases coverage estimates.

---

## 3. Provenance and licences

`raw/osm_springs.csv` is derived from OpenStreetMap and is therefore subject to
the Open Database Licence. Any published derivative must carry the ODbL
attribution — see `docs/sources.md`.

Field measurements are original to this project and are released under CC BY 4.0.

Where a processed table joins OSM-derived and field-collected columns, the ODbL
share-alike obligation applies to the result. `docs/sources.md` records which
tables are affected.

---

## 4. Reproducing the data layer

```bash
python src/fetch_osm_springs.py --out data/raw/osm_springs.csv
python src/validate.py data/raw/osm_springs.csv
```

`fetch_osm_springs.py` queries a live API, so the output changes as OSM changes.
Each run writes a sidecar `.meta.json` recording the query, the bounding box, the
timestamp, and the row count, so any figure can be traced to the extract it came
from.
