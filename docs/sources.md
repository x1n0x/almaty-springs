# Data Sources, Licences, and Attribution

Every source used by this project, what it provides, what its licence requires,
and what that means for anything published from it.

---

## 1. OpenStreetMap

**What it provides.** The seed layer of spring locations: features tagged
`natural=spring`, `amenity=drinking_water`, `man_made=water_tap`, together with
the pedestrian network used for the accessibility analysis.

**Access.** Overpass API, queried by `src/fetch_osm_springs.py`. Public endpoint,
no key required. The endpoint is rate-limited and shared; the script sends one
query per run and retries with backoff rather than hammering it.

**Licence.** Open Database Licence (ODbL) 1.0.

**What that requires.**

- Attribution: "© OpenStreetMap contributors".
- Share-alike: a derived database must be offered under ODbL. A map image or a
  statistical summary is a "produced work" and may be licensed freely, but the
  underlying table of locations is a derived database and stays ODbL.

**Practical consequence for this project.** The spring location table is ODbL,
because it derives from OSM. Field measurements are separable original data and
are CC BY 4.0 on their own. Any published table that joins the two inherits the
ODbL obligation, and the data release notes will say so explicitly rather than
leaving a reader to guess.

Tag documentation: https://wiki.openstreetmap.org/wiki/Tag:natural%3Dspring

---

## 2. Digital elevation model

**What it provides.** Elevation at each spring coordinate, slope, and the terrain
surface used to digitise the mountain front and to build the area-weighted
elevation null model for RQ1.

**Candidate datasets.**

| Dataset | Resolution | Licence |
|---|---|---|
| Copernicus DEM GLO-30 | 30 m | Free for any use with attribution to the European Space Agency |
| SRTM v3 | 30 m | Public domain (NASA/USGS) |
| ALOS World 3D-30m | 30 m | Free with attribution to JAXA, non-commercial terms on some tiers |

Copernicus GLO-30 is the default: it is more recent than SRTM and better in
mountainous terrain, which matters directly here.

**Attribution required.** "Produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014
and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the
European Union and ESA; all rights reserved." The exact wording is set by the
dataset terms and is reproduced verbatim in any publication.

**Accuracy note.** 30 m horizontal resolution with vertical error on the order of
several metres. Adequate for elevation-band analysis at the 100 m scale used in
RQ1. Not adequate for anything requiring metre-level elevation, and no such
analysis is planned.

---

## 3. Kazhydromet

**What it provides.** Air temperature and precipitation observations from Almaty
stations, used to define melt onset for RQ3 and the mean annual air temperature
baseline for RQ2.

**Access.** Published bulletins and reports from the national hydrometeorological
service. Not a machine-readable API; data is transcribed from publications, and
each transcribed series records the publication it came from.

**Licence.** Terms of reuse for official publications must be confirmed per
document before republication. Until confirmed, this project uses the data for
analysis and cites the source, rather than redistributing the series.

Site: https://www.kazhydromet.kz/

---

## 4. Population statistics

**What it provides.** District-level population for the accessibility analysis in
RQ5.

**Source.** Bureau of National Statistics of the Agency for Strategic Planning
and Reforms of the Republic of Kazakhstan.

**Licence.** Official statistics, publicly published. Cited, not redistributed.

**Gridded alternative.** Where district aggregates are too coarse, a gridded
population product is used instead:

| Dataset | Resolution | Licence |
|---|---|---|
| WorldPop | 100 m | CC BY 4.0 |
| GHS-POP (JRC) | 100 m | CC BY 4.0 |

Both require attribution and both are modelled products — they are estimates
disaggregated from census units, not observations. Coverage percentages computed
from them carry that modelling uncertainty, which is stated wherever such a
percentage appears.

---

## 5. 2GIS and local hiking resources

**What they provide.** Candidate spring locations not present in OSM, and local
names.

**Use.** Reference only, for generating a visit queue. Rows entered from these
sources carry `data_source=2gis` or `local_report` and `confidence=candidate`.

**Licence.** Proprietary. Content is **not** copied into this repository. What is
recorded is the fact that a spring may exist at approximately a given place —
and that fact is then confirmed independently by a site visit before it becomes
project data. No 2GIS content is redistributed.

---

## 6. Field measurements

**What they provide.** Discharge, temperature, pH, TDS, EC, nitrate.

**Collected by.** This project, following `docs/field_protocol.md`.

**Licence.** CC BY 4.0. Attribution: "Karelin, V., & Katkova, E. — Almaty Springs project
(github.com/x1n0x/almaty-springs)".

**Caveat published alongside.** Field-instrument readings, indicative accuracy,
no microbiological testing. Not a safety assessment. See the limitations section
of the README.

---

## 7. Laboratory analysis

**What it provides.** Water chemistry of samples collected in the field: the
measurements that field instruments cannot deliver, and the only ones with
analytical accuracy worth reporting.

**Where.** Kazakh-German University (DKU), Almaty.

**By whom.** Elizaveta Katkova, Energy and Environmental Engineering, DKU.

**Methods.** Sulfate: barium-chloride turbidimetry, delivered both as a powder
reagent in a square cuvette (working range about 2-70 mg/L) and as a barcoded
cuvette test (about 40-150 mg/L). The instrument has not been identified, so
the method designations recorded are provisional. Methods for the remaining
analytes have not been supplied and the `method` column is empty for them. See the credits section of the README; this is
authorship, not a data source being consumed, and it is recorded in
`CITATION.cff` alongside the repository's other author.

**How it is recorded.** Laboratory values are stored in their own columns,
never merged with the indicative field-instrument readings described in
section 6. Each laboratory result carries the facility and the method used, so
that a value can be traced to how it was produced. Where a parameter is
measured both on site and in the laboratory, both values are kept: the
difference between them is information about the field instrument, not noise
to be averaged away.

**Licence.** Original to this project, released under CC BY 4.0 with
attribution to both authors and to DKU as the analysing facility.

---

## 8. Attribution block for publications

Any figure, notebook, or report published from this project carries:

```
Spring locations © OpenStreetMap contributors, ODbL 1.0.
Laboratory analysis by Elizaveta Katkova, Kazakh-German University (DKU), Almaty.
Elevation from Copernicus DEM GLO-30, © DLR/Airbus, provided under COPERNICUS by
the European Union and ESA.
Population from WorldPop, CC BY 4.0.
Field and laboratory measurements: Karelin & Katkova, Almaty Springs
project, CC BY 4.0.
```

Sources not used in a given figure are omitted from its block.

---

## 9. Extract provenance

Every run of `fetch_osm_springs.py` writes a sidecar `.meta.json` next to its
output recording the Overpass query text, the bounding box, the endpoint, the UTC
timestamp, and the row count. OSM changes continuously, so a result is only
reproducible against the extract it was computed from. Keep the sidecar with any
figure derived from that extract.
