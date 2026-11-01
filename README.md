# Almaty Springs: A Geospatial and Hydrochemical Study of Natural Springs in the Almaty Region

A data study of natural springs (*rodniki*) on the northern slope of the Ile-Alatau
range and within the Almaty urban area. The project combines open geospatial data,
field measurements, and statistical analysis to describe where springs occur, how
their discharge and water quality vary through the year, and how accessible they
are to residents.

**[Interactive map of the inventory](https://x1n0x.github.io/almaty-springs/reports/map.html)**
— six visited springs against 262 features from OpenStreetMap.

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
| Field measurements | Discharge, temperature, pH, TDS, nitrate | Collected for this project | Indicative on-site readings |
| Laboratory analysis (DKU) | Water chemistry of collected samples | Kazakh-German University, Almaty | Hydrochemical results |
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
  field/                Primary field records -- tracked, not reproducible
  interim/              Cleaned, not yet joined
  processed/            Analysis-ready tables (gitignored)
  springs_template.csv  Empty template defining the canonical schema
  README.md             Data dictionary and collection protocol

src/
  photos_to_springs.py  Turn geotagged field photos into spring records
  exif_gps.py           EXIF reader for JPEG/HEIC/PNG (standard library only)
  match_osm.py          Match visited springs against the OSM extract
  ingest_lab.py         Parse a laboratory report into the results table
  summarise_lab.py      Per-sample statistics and method-artefact checks
  make_map.py           Render the inventory as a standalone HTML map
  fetch_osm_springs.py  Pull spring features from the Overpass API
  enrich_elevation.py   Attach DEM elevation to spring coordinates
  validate.py           Schema and range checks on the spring table

tests/
  test_exif_gps.py      EXIF parsing, both byte orders, missing-GPS cases

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
  map.html              Interactive map of the inventory
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

Turn a folder of field photographs into spring records:

```bash
python src/photos_to_springs.py "path/to/photos" --out data/raw/from_photos.csv
python src/enrich_elevation.py data/raw/from_photos.csv --backend api
python src/validate.py data/raw/from_photos.csv
```

Photographs are grouped by the subfolder they sit in, because a photographer
who has already sorted their shots into a folder per site has recorded better
evidence than any distance rule can infer. `--group-by distance` falls back to
clustering within `--group-radius` metres. Either way the site's position is
the group's **median**, not its mean: on the first real run one site had a
photo taken 222 m away on the approach, and a mean would have dragged the
outlet's coordinates toward it. GPS altitude from a phone is kept only as a note: it
is routinely tens of metres out, so `elevation_m` is filled from the DEM
instead. Every row lands as `candidate` — a photograph proves someone stood
somewhere, not that what they photographed is a spring.

Run the tests:

```bash
python -m unittest discover -s tests -v
```

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
| Photo-to-record pipeline | Implemented, 15 tests passing |
| OSM cross-matching | Implemented |
| Interactive map | Implemented |
| Deduplication and identifier assignment | Not started |
| Field measurement campaign | 6 springs visited and sampled, 2026-10-25 |
| Laboratory analysis | First batch received 2026-11-01, six analytes |
| RQ1 spatial analysis | Not started |
| RQ2-RQ4 hydrochemistry | Blocked on unit clarifications, see below |
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


### First field campaign, 25 October 2026

Six springs on the northern slope of the Ile-Alatau were visited in one
afternoon and sampled for laboratory analysis. Positions come from 34
geotagged photographs, grouped by site and reduced to a median coordinate;
elevations are from the DEM.

| ID | Latitude | Longitude | Elevation | Photos | In OSM |
|---|---|---|---|---|---|
| ALA-0001 | 43.18696 | 77.00465 | 1237 m | 4 | not mapped |
| ALA-0002 | 43.16193 | 77.04089 | 1550 m | 6 | `node/12196396465`, 25 m |
| ALA-0003 | 43.15953 | 77.03564 | 1622 m | 7 | `node/9924581790`, 8 m |
| ALA-0004 | 43.12511 | 76.92535 | 1436 m | 5 | not mapped |
| ALA-0005 | 43.10185 | 76.94049 | 1632 m | 6 | `node/4822409372`, 31 m |
| ALA-0006 | 43.09582 | 76.95166 | 1731 m | 6 | `node/12802758118`, 20 m |

Data: [`data/field/springs_2026-10-25.csv`](data/field/springs_2026-10-25.csv).
Map: **[open the interactive map](https://x1n0x.github.io/almaty-springs/reports/map.html)**
(source: [`reports/map.html`](reports/map.html), rebuild with
`python src/make_map.py`).

**Four of the six are already in OpenStreetMap.** ALA-0003 matches a named node
(Күміс Тау) to within 8 m, which is an independent check on the photo-derived
coordinates: two unrelated methods agreeing to within GPS error.

**Two are absent from OSM** — the nearest mapped feature is 1.4 km and 2.9 km
away respectively. Both are candidates to contribute back once their outlets
have been confirmed on a second visit.

**Where the six sit in the region.** They span 1237-1731 m, with a median of
1586 m. The 262 mapped features span 569-4177 m with a median of 1612 m: 115
lie below the visited band and 128 above it. The medians nearly coincide, but
the visited range is narrow — this is a sample from the region's middle
elevations, not a cross-section of it. Any later comparison between these
springs and the regional picture has to carry that caveat.

Phone GPS altitude agreed with the DEM to within 2-13 m across all six sites.
That is better than typical for a handset, but `elevation_m` still comes from
the DEM: the agreement was measured here, not guaranteed elsewhere.

**Not yet recorded for these sites.** `flow_state` is empty: discharge was not
measured and the outlets' flow was not characterised at the time of sampling.
Five of the six have no local name. Both are gaps to close on the next visit,
not values to infer afterwards from memory.


### First laboratory batch, received 1 November 2026

Six samples, six analytes, most in triplicate: 97 measurements in
[`data/field/lab_results_2026-10-25.csv`](data/field/lab_results_2026-10-25.csv),
transcribed from the report preserved verbatim at
[`data/field/lab_raw_2026-10-25.txt`](data/field/lab_raw_2026-10-25.txt).
Reproduce and check with:

```bash
python src/ingest_lab.py data/field/lab_raw_2026-10-25.txt
python src/summarise_lab.py data/field/lab_results_2026-10-25.csv
```

Replicate means:

| Spring | pH | Nitrite mg/L | Sulfate mg/L | Iron mg/L | Chlorine mg/L | Water degC | Air degC |
|---|---:|---:|---:|---:|---:|---:|---:|
| ALA-0001 | 7.25 | 3.67 | 9 | 0.030 | 0.00 | 8.0 | 5 |
| ALA-0002 | 7.94 | 3.67 | 2 | 0.013 | 0.00 | 2.0 | 4 |
| ALA-0003 | 7.47 | 3.00 | 2 | 0.007 | 0.00 | 6.0 | 3 |
| ALA-0004 | 8.15 | 3.00 | 54 (65.7) | 0.103 | 0.00 | 12.5 | -1 |
| ALA-0005 | 7.85 | 4.33 | 4 | 0.007 | 0.00 | 1.5 | -3 |
| ALA-0006 | 7.64 | 6.33 | 9 | 0.010 | 0.03 | 5.0 | -3 |

Hardness was also reported — 25, 25, 25, 7, 15, 25 — **without units**, and is
therefore not in this table. 25 mg/L CaCO3 is very soft water and 25 °dH is
very hard water; the two readings differ by a factor of about 18, so the column
is stored with `unit=unknown` and excluded from every comparison until the
laboratory answers.

#### What the replicates show about the method

**The first reading of a triplicate is systematically the highest.** Across the
17 triplicates that could vary at all — sulfate and chlorine returned identical
repeats and carry no ordering information — the first reading was the strict
maximum in 13. Under exchangeable readings that happens with probability
0.0003. This is an instrument or procedure effect, not a property of the water:
insufficient stabilisation, carry-over between readings, or a missing rinse
step. Until it is traced, triplicate means are biased upward.

**Sulfate repeats are identical in all six samples, and that is not precision.**
A readout returning the same number three times is quantised. The one sample
measured twice proves the point: ALA-0004 gave 54 mg/L by the routine method
and 65.7 mg/L by the laboratory's reference method, a difference of 17.8%. A
standard deviation of zero alongside a 17.8% method bias is exactly the trap
that reporting replicate spread as uncertainty would set. The other five
sulfate figures were measured only by the routine method and inherit an
unquantified bias of unknown size.

#### ALA-0004 is different from the other five

It has the highest pH (8.15), the highest sulfate (54–65.7 against 2–9
elsewhere), the highest iron (0.103 against 0.007–0.030), the lowest hardness
(7 against 15–25 in whatever units), and the warmest water by a wide margin:
12.5 °C while the air was -1 °C.

The thermal part survives the obvious confound. Air temperature fell through
the afternoon, so a water-minus-air difference is not comparable between sites
visited hours apart. But ALA-0005 and ALA-0006 were sampled 22 and 32 minutes
after ALA-0004 under near-identical air temperature, and their water was 1.5 °C
and 5.0 °C. ALA-0004 is warm relative to its immediate neighbours in time, not
merely relative to a colder hour.

A warm, more mineralised outlet is what deeper circulation looks like. It is
also what a different aquifer, a leaking pipe, or a mislabelled sample looks
like. One sample cannot separate those, and **the lowest hardness coinciding
with the highest sulfate does not fit the simple deep-circulation story** — it
is the kind of internal tension that usually means a measurement needs
repeating, not a mechanism needs inventing. ALA-0004 is also one of the two
springs absent from OpenStreetMap.

#### Nitrite

Every sample sits at or above the WHO provisional guideline value for nitrite
of 3 mg/L, ranging from 3.0 to 6.3 mg/L.

This must not be read as a health finding yet, for a specific reason: the
report does not say whether the figures are nitrite ion (NO2-) or nitrite as
nitrogen (NO2-N). The two differ by a factor of 3.28, and the guideline is
stated for the ion. The question has been sent back to the laboratory and is
the single most consequential open item in this batch.

Three further cautions apply regardless of the answer. The first-reading bias
above inflates these means. Nitrite in groundwater is usually transient and
can indicate recent contamination rather than a stable condition, so a single
visit cannot establish a persistent level. And this project performs no
microbiological testing at all — the contamination that actually makes spring
water dangerous would not appear anywhere in this table.

#### Open questions with the laboratory

Listed in full at the end of
[`data/field/lab_raw_2026-10-25.txt`](data/field/lab_raw_2026-10-25.txt):
hardness units, nitrite species, chlorine units, methods and detection limits
for every analyte, which method produced each sulfate figure, and the analyst
and analysis date for the record. The many 0.00 results are almost certainly
non-detects rather than true zeros, and cannot be stored correctly until the
detection limits are known.

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

## 11. Credits

This project is the work of more than one person, and the laboratory half of it
does not appear in the commit history. It is recorded here instead.

**Vladislav Karelin** ([@x1n0x](https://github.com/x1n0x), [ORCID 0009-0003-2612-7843](https://orcid.org/0009-0003-2612-7843)) — project design, field
survey, data engineering, analysis, repository.

**Elizaveta Katkova** — Kazakh-German University (DKU), Almaty. Laboratory
analysis, sample preparation and handling, hydrochemical interpretation. Every
water-chemistry value published in this repository comes from this work.

Laboratory analysis is carried out at the Kazakh-German University (DKU) in
Almaty, which provides the facilities and instrumentation the project's
hydrochemistry depends on.

Machine-readable authorship is in [`CITATION.cff`](CITATION.cff); GitHub reads
it for the "Cite this repository" panel. Both authors are listed there, and the
citation metadata is the canonical record — not the commit log, which only
reflects who typed.

---

## 12. Contributing

Spring locations, corrections, and measurements are welcome. Open an issue with
coordinates and, if possible, a photograph of the outlet. Please do not submit
locations on private land without the owner's permission.

---

## 13. Licence

Code is released under the MIT Licence — see [`LICENSE`](LICENSE).

Data derived from OpenStreetMap remains subject to the Open Database Licence
(ODbL). Original field measurements collected for this project are released under
CC BY 4.0. Details in [`docs/sources.md`](docs/sources.md).
