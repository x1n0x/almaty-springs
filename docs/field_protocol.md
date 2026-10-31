# Field Protocol

How a measurement is taken, so that two visits a year apart are comparable and so
that anyone reading a number knows what it means.

Safety and legality come before data. No measurement is worth a flooded gorge, an
unstable slope, or an argument with a landowner.

---

## 1. Before leaving

- Calibrate the pH meter the same day, with fresh buffer solutions (4.01 and
  7.00). Record the calibration time in the visit log. An uncalibrated pH reading
  is not recorded as data.
- Check the TDS/EC meter against a standard solution. Replace the battery if the
  reading drifts; a low battery produces plausible but wrong numbers, which is
  worse than no reading.
- Note the weather for the previous 72 hours. Rainfall changes discharge and
  turbidity, and a reading taken the morning after a storm is not comparable to a
  dry-weather reading. Record it rather than discarding the visit.

---

## 2. On arrival

Record in this order, before touching the water:

1. **Time** — ISO 8601 with the `+06:00` offset.
2. **GPS coordinates** — taken at the outlet, with the device given at least 60
   seconds to settle. Record the device's reported accuracy. If accuracy is worse
   than 15 m, note it; the point stays `reported`, not `verified`.
3. **Flow state** — `flowing`, `trickle`, or `dry`, by eye.
4. **Air temperature** — in shade, away from the body.
5. **Photograph** — the outlet, and a wider shot showing the setting. Photographs
   are the only record that lets a later visitor confirm they found the same
   outlet.

A dry spring is a complete, valid observation. Record it with `flow_state=dry`
and move on. Discarding dry visits turns the dataset into a record of springs
that happened to be flowing when someone looked, which makes any seasonality
result meaningless.

---

## 3. Discharge

Three methods, in descending order of preference.

**Bucket method** (preferred for outlets under ~100 L/min). Place a container of
known volume under the full flow. Time how long it takes to fill, with a
stopwatch, starting when the container is in position and stopping at the mark.
Repeat three times. Record the median, not the mean — a single mistimed fill
distorts a mean of three. Record `discharge_method=bucket`.

Requirements: the entire flow must enter the container. If water escapes around
the sides, the measurement is an underestimate and must be recorded as
`estimate`, not `bucket`.

**Weir or flume** (for larger flows). Only where a built structure exists.
Record the structure type and dimensions in `notes`.

**Visual estimate** (last resort). Recorded as `discharge_method=estimate` and
excluded from quantitative discharge analysis. Still useful for ranking and for
confirming the spring flows at all.

---

## 4. Temperature

Measure **at the outlet**, in the emerging water, not in a downstream pool. A
pool equilibrates with air temperature within metres and will read several
degrees off.

Submerge the probe, wait for the reading to stabilise — typically 30-60 seconds —
and record the stable value. Record air temperature at the same visit; water
temperature without air temperature cannot be interpreted.

---

## 5. pH, TDS, EC

Rinse the probe with distilled water, then with the spring water itself, before
reading. Residue from the previous site is a real source of error.

Take the reading in flowing water where possible. Wait for stabilisation. If the
reading will not stabilise within two minutes, record the range in `notes` and
flag the row.

Temperature compensation: most consumer meters compensate automatically, but
record water temperature alongside every EC reading regardless, since conductivity
is strongly temperature-dependent and a later reader may need to recompute.

---

## 6. Nitrate

Test strips or a colorimetric kit. Follow the kit's timing exactly; reading a
strip late is a systematic bias, not random noise.

Record the kit brand and lot in `notes` on the first use of each batch. Results
from different kits are not directly comparable, and without the brand recorded
there is no way to know a batch changed mid-campaign.

Treat every nitrate value as indicative. The resolution is coarse and the
analysis plan in `methodology.md` treats RQ4 as exploratory for this reason.

---

## 7. What is not measured

**Microbiological contamination.** Coliforms and E. coli are the contamination
that actually makes spring water dangerous, and they cannot be assessed with
field instruments or by eye. Clear, cold, pleasant-tasting water can be
contaminated. This project does not test for it and therefore cannot say any
spring is safe to drink.

**Heavy metals, hydrocarbons, pesticides.** Require laboratory analysis.

If a laboratory campaign becomes possible, samples must be collected in
lab-supplied containers, chilled, and delivered within the lab's stated holding
time. Samples collected into water bottles are not analysable and should not be
taken.

---

## 8. Repeat visits

Seasonality needs the same springs measured repeatedly, not more springs measured
once. For the subset selected for seasonal tracking:

- Monthly through the year, with additional visits during melt onset (typically
  March to May) when discharge changes fastest.
- Same time of day where practical, to remove diurnal variation as a confound.
- Same observer and same instruments where practical. When either changes, record
  it, so that a step change in the series can be attributed.

---

## 9. Data entry

Enter measurements the same day, from the field notebook into a copy of
`data/springs_template.csv`. Delay introduces transcription error and lost
context.

Run the validator before committing anything derived from the file:

```bash
python src/validate.py data/raw/field_2026_04.csv
```

Keep the paper notebook. It is the primary record, and it is the only thing that
survives a mistaken overwrite of the CSV.

---

## 10. Access and courtesy

Many outlets sit on or beside private land. Ask before entering. If asked to
leave, leave, and record the spring as `access=restricted` without coordinates
precise enough to direct others onto that land.

Do not publish precise coordinates for springs on private property. The
accessibility analysis uses them in aggregate; the published point layer excludes
them.
