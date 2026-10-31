# Methodology

This document fixes the analysis plan before the data exists. Each research
question gets a stated method, a stated success criterion, and a stated failure
mode. If the data turns out not to support a question, the answer recorded here
is "not answerable with this data" — not a weaker method chosen after the fact.

---

## 1. Inventory construction

**Step 1 — Extract.** `src/fetch_osm_springs.py` queries the Overpass API for
features tagged `natural=spring`, `man_made=water_tap`, or
`amenity=drinking_water` within the project bounding box. Output is raw and
unmodified.

**Step 2 — Deduplicate.** OSM contains duplicate nodes for the same physical
outlet, often added by different mappers years apart. Two features are treated as
the same spring when they are within 25 m of each other and neither carries a
name that contradicts the other. 25 m is chosen because it exceeds consumer GPS
error (typically 5-10 m) without merging genuinely adjacent outlets, which in
observed gorge settings are usually separated by more than that. Every merge is
logged with both source IDs; no merge happens silently.

**Step 3 — Assign identifiers.** Each surviving outlet receives an `ALA-####`
identifier. Identifiers are assigned once and never reused, so that a
field notebook reference stays valid after a re-extraction.

**Step 4 — Enrich.** Elevation is sampled from the DEM at each coordinate.
Distance to the mountain front is computed as the shortest planar distance to a
manually digitised front line, in a projected CRS (EPSG:32643, UTM zone 43N) so
that distances are in metres rather than degrees.

---

## 2. RQ1 — Spatial structure

**Claim to test.** Spring occurrence is not uniform with elevation; it
concentrates in a band associated with the break in slope at the mountain front.

**Method.**

1. Describe the elevation distribution of documented springs: kernel density
   estimate plus empirical quantiles.
2. Compare against a null model. The null is *not* a uniform distribution over
   the elevation range — that would be trivially rejected because the land area
   itself is not uniform with elevation. The null is the elevation distribution
   of the land area within the bounding box, sampled from the DEM. The test is
   whether springs are distributed differently from land.
3. Two-sample Kolmogorov-Smirnov test between the spring elevation sample and
   the area-weighted elevation sample. Report the statistic, the p-value, and
   the effect size, in that order of importance.
4. Spatial clustering: Ripley's K with a Monte Carlo envelope under complete
   spatial randomness restricted to the land mask.

**Confound that must be addressed.** Mapping effort is not uniform in space.
Springs near trails are mapped more often. Elevation correlates with trail
density. A clustering result could therefore reflect where mappers walk rather
than where water emerges. Mitigation: repeat the analysis with distance-to-trail
as a covariate, using OSM `highway=path|footway` as the trail layer, and report
whether the elevation effect survives. If it does not survive, the finding is
reported as confounded, not suppressed.

**Success criterion.** A stated effect size with a stated confound assessment.
Not a p-value alone.

---

## 3. RQ2 — Thermal signature

**Claim to test.** Water temperatures separate into groups consistent with
different circulation depths.

**Method.**

1. Require at least 30 `verified` temperature measurements before running this
   analysis. Below that, report descriptive statistics only.
2. Temperature must be interpreted against air temperature and season. The
   comparison quantity is the deviation of water temperature from the local mean
   annual air temperature, not raw water temperature, because a shallow spring
   measured in July and the same spring measured in January differ for reasons
   that have nothing to do with its source.
3. Cluster the deviation values. With a one-dimensional variable, a Gaussian
   mixture with model selection by BIC over k = 1 to 4 is appropriate; k-means
   is not, because it cannot express "one group" as an outcome and will always
   return the k it is given.
4. If BIC selects k = 1, the answer to RQ2 is that no separation is detectable.
   That is a result.

**Failure mode to avoid.** Finding two clusters in any continuous variable is
easy and usually meaningless. The analysis is only informative if the selected
k > 1 *and* the groups differ in a second, independent variable — elevation,
TDS, or discharge stability. A temperature-only split is not evidence of
distinct aquifers.

---

## 4. RQ3 — Seasonality

**Requirement.** At least 8 repeat visits per spring, distributed across the melt
cycle, at a minimum of 5 springs. Until that exists, this section produces
nothing.

**Method.** Per-spring discharge time series. Melt onset is taken from
Kazhydromet air-temperature records as the first date of a 5-day running mean
above 0 degrees C at the nearest station. Lag between melt onset and discharge
peak is estimated by cross-correlation per spring, then summarised across
springs with a median and an interquartile range rather than a mean, given the
small sample.

**Known limitation.** With 8 observations per series, a lag estimate has wide
uncertainty. The deliverable is an interval, not a point estimate, and the
interval will probably be wide enough to be uninformative in the first season.
This is accepted; the alternative is waiting a year to publish anything.

---

## 5. RQ4 — Water quality and land use

**Method.** Upstream land use is summarised in a circular buffer around each
spring. Buffer radius is a free parameter with no obvious correct value, so the
analysis is run at 250 m, 500 m, and 1000 m and the sensitivity to that choice is
reported. Reporting only the radius that produced the strongest association
would be a specification search; all three are reported regardless of outcome.

Association between nitrate and residential or agricultural fraction is estimated
with a rank correlation, given small samples and non-normal concentrations.

**Hard limitation, stated up front.** Nitrate from field test strips has
resolution on the order of 10 mg/L. Detecting a land-use gradient at that
resolution requires either a large sample or a large effect. This analysis is
exploratory and will be labelled as such.

---

## 6. RQ5 — Accessibility

**Method.** Walking-distance isochrones from each `verified` or `reported`
spring, computed on the OSM pedestrian network rather than as straight-line
buffers, because the gorges and the canal network make Euclidean distance a poor
proxy for walking time. 15 minutes at 4.5 km/h on flat ground, with a slope
penalty applied using Tobler's hiking function.

Population within isochrones is estimated from gridded population data
intersected with the isochrone polygons, then aggregated to district level.

**Interpretation limit.** Coverage computed from a biased inventory understates
nothing and overstates nothing in a predictable direction — missing springs mean
true coverage is higher than measured, but missing springs are concentrated in
remote areas with little population, so the effect on a population-weighted
figure is small. This argument is stated rather than assumed, and the sensitivity
is tested by recomputing coverage with `candidate` points included as an upper
bound.

---

## 7. Validation

- Every script that writes a table runs `src/validate.py` on its output.
- Range checks come from the allowed-values column of the data dictionary, so
  the dictionary is the single source of truth rather than a comment that drifts.
- Coordinate checks reject any point outside the project bounding box, which
  catches transposed lat/lon — the single most common error in this kind of
  dataset.
- Notebooks read from `data/processed/` and never mutate it.

---

## 8. What would make this project wrong

Recorded here so that it can be checked later rather than rationalised:

1. If the OSM seed layer turns out to contain mostly `man_made` taps on the
   municipal supply rather than natural springs, the inventory measures
   something different from what the title claims. Mitigation: `source_type`
   is verified on site, and the share of misclassified features is reported.
2. If field visits concentrate in one gorge because it is the easiest to reach,
   the hydrochemical sample is a study of that gorge, not of the region. Visit
   locations will be reported as a map, so the reader can see the sampling
   footprint rather than take a regional claim on trust.
3. If seasonal data collection stops after one spring, RQ3 is unanswered and
   will be marked so in the README status table rather than quietly dropped.
