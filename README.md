# Almaty Springs: A Geospatial and Hydrochemical Study of Natural Springs in the Almaty Region

A data study of natural springs (*rodniki*) on the northern slope of the Ile-Alatau
range and within the Almaty urban area. The project combines open geospatial data,
field measurements, and statistical analysis to describe where springs occur, how
their discharge and water quality vary through the year, and how accessible they
are to residents.

This repository is a research project in progress. Its structure, data contracts,
and methodology are defined first; results are added as data is collected.

---

## 1. Project Overview

Almaty sits on an alluvial fan fed by meltwater from the Ile-Alatau (Zailiysky
Alatau) mountains. Groundwater discharges at the break in slope and along gorge
walls, producing a large number of springs that residents use as drinking-water
sources — often without any knowledge of water quality or seasonal reliability.

Despite heavy informal use, there is no single open dataset describing these
springs. Locations are scattered across OpenStreetMap, municipal registries,
hiking resources, and local knowledge. Quality data is largely absent from the
public domain.

This project aims to build that dataset and analyze it.

### Objectives

1. Assemble a reproducible, openly licensed inventory of springs in the Almaty
   region, with coordinates, elevation, and access attributes.
2. Collect repeatable field measurements of discharge, temperature, and basic
   water chemistry at a subset of accessible springs.
3. Describe the spatial structure of spring occurrence in relation to elevation,
   geology, and the mountain-front break in slope.
4. Quantify seasonal variation in discharge and temperature where repeat visits
   allow it.
5. Produce an accessibility analysis: how many residents live within walking
   distance of a spring, and which districts are underserved.

---

## 2. Research Questions

**RQ1 — Spatial structure.**
Does spring occurrence cluster at a characteristic elevation band or distance from
the mountain front, as the alluvial-fan discharge model predicts?

**RQ2 — Thermal signature.**
Do spring water temperatures separate into distinct groups, and does that
separation correspond to shallow versus deep circulation? Spring temperature
approximating mean annual air temperature suggests shallow flow; a warmer or more
stable temperature suggests a deeper source.

**RQ3 — Seasonality.**
How does discharge respond to the snowmelt cycle, and what is the lag between
melt onset and peak spring flow?

**RQ4 — Water quality and land use.**
Is measured mineralization or nitrate concentration associated with upstream land
use (residential density, agriculture, roads)?

**RQ5 — Accessibility.**
What share of the Almaty population lives within a 15-minute walk of a documented
spring, and how is that share distributed across districts?

---

## 3. Data Sources

| Source | Type | Access | Use in project |
|---|---|---|---|
| OpenStreetMap (Overpass API) | Point/polygon features tagged `natural=spring`, `drinking_water` | Open, ODbL | Primary location seed |
| Copernicus DEM / SRTM | Raster elevation | Open | Elevation, slope, distance to mountain front |
| Field measurements | Discharge, temperature, pH, TDS, nitrate | Collected for this project | Hydrochemistry, seasonality |
| Kazhydromet | Meteorological observations (Almaty stations) | Public reports | Melt-season context, air temperature baseline |
| Bureau of National Statistics RK | Population by district | Open | Accessibility analysis |
| 2GIS, local hiking resources | Informal spring locations | Reference only | Cross-check and candidate discovery |

Attribution and licence terms for every source are recorded in
[`docs/sources.md`](docs/sources.md). No source is redistributed in this
repository in violation of its licence; derived datasets are published under the
terms noted there.

**Raw data is not committed to this repository.** Collection scripts in `src/`
reproduce the raw layer from scratch. See [`data/README.md`](data/README.md).

---

## 4. Data Schema

The canonical spring record is defined in [`data/README.md`](data/README.md) and
templated in [`data/springs_template.csv`](data/springs_template.csv). Core
fields:

| Field | Type | Description |
|---|---|---|
| `spring_id` | string | Stable project identifier, `ALA-####` |
| `name_local` | string | Name as used locally (Russian or Kazakh) |
| `lat`, `lon` | float | WGS84 coordinates, 5 decimal places |
| `elevation_m` | int | Elevation from DEM, metres (500-4500) |
| `source_type` | enum | `spring`, `captured_spring`, `well`, `unknown` |
| `access` | enum | `public`, `restricted`, `unknown` |
| `discharge_l_min` | float | Measured discharge, litres per minute |
| `water_temp_c` | float | Water temperature at outlet, degrees Celsius |
| `ph` | float | Field pH |
| `tds_ppm` | int | Total dissolved solids, ppm |
| `measured_at` | datetime | ISO 8601, local time |
| `data_source` | string | Provenance of this record |
| `confidence` | enum | `verified`, `reported`, `candidate` |

Every location carries a `confidence` value. A spring is only `verified` after a
site visit with recorded coordinates. Locations taken from secondary sources stay
`reported` or `candidate` until visited. This distinction is enforced in the
analysis: unverified points are excluded from hydrochemical results and included
in spatial results only with the exclusion stated.

---

## 5. Project Structure

```
data/
  raw/                  Unmodified source extracts (gitignored)
  interim/              Cleaned, not yet joined
  processed/            Analysis-ready tables (gitignored)
  springs_template.csv  Empty template defining the canonical schema
  README.md             Data dictionary and collection protocol

src/
  fetch_osm_springs.py  Pull spring features from the Overpass API
  enrich_elevation.py   Attach DEM elevation to spring coordinates
  validate.py           Schema and range checks on the spring table

notebooks/
  01_osm_inventory.ipynb        Extract, deduplicate, map the OSM seed layer
  02_spatial_structure.ipynb    RQ1 - elevation and distance-to-front analysis
  03_field_measurements.ipynb   RQ2, RQ3 - temperature and discharge
  04_accessibility.ipynb        RQ5 - walking-distance coverage

docs/
  methodology.md        Analysis plan and statistical approach
  field_protocol.md     How measurements are taken, instrument by instrument
  sources.md            Every data source, its licence, and attribution

reports/
  figures/              Generated figures
```

---

## 6. Methodology

The analysis plan, including the statistical approach for each research question
and the validation strategy, is written out in
[`docs/methodology.md`](docs/methodology.md) before results are produced. Writing
the plan first is deliberate: it keeps the project from retrofitting a method to
whatever the data happens to show.

Field measurement procedure — instruments, calibration, repeat-visit scheduling,
and the handling of measurement error — is documented in
[`docs/field_protocol.md`](docs/field_protocol.md).

---

## 7. Setup

```bash
git clone https://github.com/x1n0x/almaty-springs.git
cd almaty-springs
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, activate with `.venv\Scripts\activate` instead.

Build the raw OpenStreetMap layer:

```bash
python src/fetch_osm_springs.py --out data/raw/osm_springs.csv
```

Validate a spring table against the schema:

```bash
python src/validate.py data/raw/osm_springs.csv
```

---

## 8. Current Status

| Component | Status |
|---|---|
| Repository structure and data contract | Defined |
| OSM extraction pipeline | Implemented |
| DEM enrichment | Implemented |
| Schema validator | Implemented |
| Deduplication and identifier assignment | Not started |
| Field measurement campaign | 6 springs sampled |
| Laboratory analysis | Samples submitted, results pending |
| RQ1 spatial analysis | Not started |
| RQ2-RQ4 hydrochemistry | Awaiting laboratory results |
| RQ5 accessibility | Not started |

### First extract

A run of the extraction pipeline over the default bounding box returned **262
candidate water features**:

| `source_type` | Count |
|---|---:|
| `spring` | 140 |
| `unknown` (tagged `amenity=drinking_water`) | 115 |
| `captured_spring` | 5 |
| `well` | 2 |

Only 8 of the 262 carry a name, so 254 entered the table as `candidate` rather
than `reported`. DEM elevations span 569 m to 4177 m with a median of 1612 m,
which immediately widened the schema's expected elevation range: the initial
3500 m ceiling rejected twelve genuine high-altitude glacial-meltwater springs
on the Ile-Alatau ridge.

The 115 `amenity=drinking_water` features are the main open question in the
inventory. Some are genuine captured springs; others are taps on the municipal
supply, which are not springs at all. Separating them requires site visits, and
the share that turns out to be misclassified will be reported — it is the first
limitation listed in `docs/methodology.md` section 8.

---

## 9. Limitations

**Coverage is biased toward accessibility.** Springs near trails and roads are
over-represented in every available source. Remote springs are systematically
missing, and no amount of cleaning fixes that. Spatial results are therefore
statements about *documented* springs, not about all springs.

**Sample size.** Six springs have been sampled so far. That is enough for a
careful description of each one and for comparison against drinking-water
norms, and it is not enough for the clustering and distribution tests described
in `docs/methodology.md`. Those sections are written for a larger inventory and
stay unanswered until it exists; nothing in this repository will report a
statistical result computed on six points.

**Two tiers of measurement.** Where samples go to a laboratory, results are
laboratory-grade and are labelled with the facility and method. Where only
portable pH, TDS and nitrate instruments were used, readings are indicative and
labelled as such. The two are never pooled into one column, because an
indicative strip reading and a certified assay are not the same measurement.

**Seasonality requires time.** RQ3 needs at least one full melt cycle of repeat
visits. Until then, no seasonal claim will be made.

**This project does not certify water as safe to drink.** Measurements published
here describe what was observed at one outlet at one moment. They are not a
substitute for laboratory testing by a certified facility, and must not be read
as a recommendation to drink from any spring.

---

## 10. Technologies

- Python 3.11
- pandas, numpy — tabular processing
- geopandas, shapely, pyproj — geospatial operations
- rasterio — DEM sampling
- requests — Overpass API access
- scikit-learn, scipy, statsmodels — clustering and hypothesis testing
- matplotlib, folium — static and interactive mapping

---

## 11. Contributing

Spring locations, corrections, and measurements are welcome. Open an issue with
coordinates and, if possible, a photograph of the outlet. Please do not submit
locations on private land without the owner's permission.

---

## 12. Licence

Code is released under the MIT Licence — see [`LICENSE`](LICENSE).

Data derived from OpenStreetMap remains subject to the Open Database Licence
(ODbL). Original field measurements collected for this project are released under
CC BY 4.0. Details in [`docs/sources.md`](docs/sources.md).
