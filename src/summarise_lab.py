"""Summarise a laboratory batch and check it for method artefacts.

Replicates exist to measure the method, not only the water. This script
therefore reports the per-sample statistics *and* runs three checks that treat
the replicates as evidence about how the measurement behaved:

1. Replicate-order bias. If the first reading of a triplicate is systematically
   the highest, that is the instrument or the operator, not the sample.
2. Zero dispersion. Identical repeats look like precision and usually are not:
   they mean the readout is quantised, and say nothing about accuracy.
3. Method disagreement. Where one sample was measured twice by different
   methods, the gap between them bounds the bias of the routine method.

Comparison against drinking-water guideline values is printed last and is
explicitly not a safety assessment -- see the caveats it prints.

Usage:
    python src/summarise_lab.py data/field/lab_results_2026-10-25.csv
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

# Comparison values, for orientation only.
# WHO Guidelines for Drinking-water Quality, 4th edition.
GUIDELINES = {
    "nitrite": (3.0, "mg/L", "WHO provisional guideline, NO2- confirmed by the lab"),
    "chlorine": (5.0, "mg/L", "WHO guideline value for free chlorine"),
    "iron": (0.3, "mg/L", "WHO: no health-based guideline; taste/staining threshold"),
    "sulfate": (250.0, "mg/L", "WHO: no health-based guideline; taste threshold"),
    "copper": (2.0, "mg/L", "WHO health-based guideline value"),
    "turbidity": (5.0, "NTU", "WHO aesthetic; <1 NTU preferred for disinfection"),
}
PH_OPERATIONAL = (6.5, 8.5)


def load(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def binomial_tail(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p). Exact, standard library only."""
    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


# Measurements made by a second method on a single sample are held out of the
# per-sample statistics: one reading from a different method is not a replicate
# and would distort both the mean and the spread. Check 3 compares them
# separately, which is the only place the comparison is meaningful.
SECONDARY_METHODS = {"hach_cuvette_test_barcoded"}


def grouped(rows: list[dict], exclude: set[str] = SECONDARY_METHODS) -> dict:
    out: dict[tuple[str, str], list[tuple[int, float]]] = defaultdict(list)
    for row in rows:
        if row.get("method") in exclude:
            continue
        try:
            value = float(row["value"])
        except (KeyError, ValueError):
            continue
        rep = int(row["replicate"]) if row.get("replicate") else 1
        out[(row["analyte"], row["spring_id"])].append((rep, value))
    for key in out:
        out[key].sort()
    return out


def report_table(groups: dict) -> None:
    analytes = sorted({a for a, _ in groups})
    for analyte in analytes:
        unit_rows = [k for k in groups if k[0] == analyte]
        print(f"\n{analyte}")
        print(f"  {'spring':10} {'n':>2} {'mean':>8} {'sd':>7} {'min':>7} {'max':>7}")
        for key in sorted(unit_rows, key=lambda k: k[1]):
            values = [v for _, v in groups[key]]
            sd = statistics.stdev(values) if len(values) > 1 else float("nan")
            sd_text = "   n/a" if len(values) < 2 else f"{sd:7.3f}"
            print(
                f"  {key[1]:10} {len(values):>2} {statistics.mean(values):8.3f} "
                f"{sd_text} {min(values):7.3f} {max(values):7.3f}"
            )


def check_replicate_order(groups: dict) -> None:
    print("\n" + "=" * 72)
    print("CHECK 1  Replicate-order bias")
    print("=" * 72)
    print("If readings within a triplicate were exchangeable, the first one")
    print("would be the strict maximum about a third of the time.")
    print()
    print("Triplicates whose three readings are identical are excluded: a")
    print("readout that cannot vary carries no information about ordering, and")
    print("counting it as a failure would hide a real effect behind the")
    print("quantised analytes. The exclusion rule is fixed in advance and")
    print("applies to every analyte, so it is not a choice made after seeing")
    print("which ones looked interesting.\n")

    total_first = total_sets = total_dropped = 0
    for analyte in sorted({a for a, _ in groups}):
        first_max = sets = dropped = 0
        for key in [k for k in groups if k[0] == analyte]:
            values = [v for _, v in groups[key]]
            if len(values) < 3:
                continue
            if len(set(values)) == 1:
                dropped += 1
                continue
            sets += 1
            if values[0] > max(values[1:]):
                first_max += 1
        total_dropped += dropped
        if not sets:
            print(f"  {analyte:16} no informative triplicates ({dropped} identical)")
            continue
        total_first += first_max
        total_sets += sets
        suffix = f"   ({dropped} identical, excluded)" if dropped else ""
        print(f"  {analyte:16} first reading highest in {first_max}/{sets}{suffix}")

    if total_sets:
        p = binomial_tail(total_first, total_sets, 1 / 3)
        print(f"\n  overall: {total_first}/{total_sets} triplicates")
        print(f"  P(this many or more by chance) = {p:.4f}")
        if p < 0.05:
            print("\n  -> Not chance. Something makes the first reading read high:")
            print("     insufficient stabilisation, carry-over between readings, or")
            print("     a rinse step missing between repeats. Until it is traced,")
            print("     the mean of a triplicate is biased upward, and the first")
            print("     reading should not be averaged in without justification.")
        else:
            print("\n  -> Consistent with chance at this sample size.")


def check_zero_dispersion(groups: dict) -> None:
    print("\n" + "=" * 72)
    print("CHECK 2  Zero dispersion")
    print("=" * 72)
    for analyte in sorted({a for a, _ in groups}):
        keys = [k for k in groups if k[0] == analyte]
        triplicates = [k for k in keys if len(groups[k]) >= 2]
        identical = [k for k in triplicates if len(set(v for _, v in groups[k])) == 1]
        if triplicates and len(identical) == len(triplicates):
            print(f"  {analyte}: every replicate set is identical "
                  f"({len(identical)}/{len(triplicates)})")
            print("     Repeatability without accuracy. A readout that always")
            print("     returns the same number is quantised, not precise; its")
            print("     standard deviation of zero must not be reported as")
            print("     measurement uncertainty.")


def check_method_disagreement(rows: list[dict]) -> None:
    print("\n" + "=" * 72)
    print("CHECK 3  Method disagreement")
    print("=" * 72)
    by_key: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        try:
            by_key[(row["analyte"], row["spring_id"])][row["method"]].append(
                float(row["value"])
            )
        except (KeyError, ValueError):
            continue

    found = False
    for (analyte, spring), methods in sorted(by_key.items()):
        if len(methods) < 2:
            continue
        found = True
        print(f"  {analyte} at {spring}:")
        means = {}
        for method, values in sorted(methods.items()):
            means[method] = statistics.mean(values)
            print(f"     {method:16} {means[method]:.2f}  (n={len(values)})")
        routine = means.get("hach_dr3900_prog680_SulfaVer4")
        reference = means.get("hach_cuvette_test_barcoded")
        if routine and reference:
            diff = reference - routine
            print(f"     difference: {diff:+.2f} ({diff / reference * 100:+.1f}% "
                  "of the cuvette value)")
            print("\n     The powder method reads low here. The two share their")
            print("     chemistry -- barium chloride, turbidity -- and differ in")
            print("     reagent delivery and calibration range.")
            print()
            print("     The gap cannot be carried across to the other samples.")
            print("     The cuvette test works from about 40 mg/L upward, and the")
            print("     other five sit at 2-9 mg/L, below its range: they could")
            print("     not have been measured by it, which is why only this one")
            print("     was re-run. Correcting them by -17.8% would be applying a")
            print("     bias measured at the top of the powder method's range to")
            print("     readings near its bottom. Checking them needs a different")
            print("     reference method, not this one.")
    if not found:
        print("  No analyte was measured by more than one method.")


# Working range and smallest resolvable step for each method, from the
# manufacturer's published procedure. `step` is the concentration change
# corresponding to 0.010 absorbance where Hach states one; None where it is
# not published or does not apply.
METHOD_SPECS = {
    "hach_dr3900_prog373_NitriVer2_HR": (0, 250, 1.4, "nitrite HIGH range, NitriVer 2"),
    "hach_dr3900_prog680_SulfaVer4": (2, 70, None, "sulfate, SulfaVer 4"),
    "hach_cuvette_test_barcoded": (40, 150, None, "sulfate, barcoded cuvette test"),
    "hach_dr3900_prog88_DPD_530nm": (0, 10, None, "chlorine free+total, DPD"),
    "hach_lck303_cuvette": (2, 47, None, "ammonium, LCK 303 cuvette test"),
    "hach_dr3900_CuVer1_bicinchoninate": (0.04, 5.0, None, "copper, CuVer 1"),
}


def check_method_fit(rows: list[dict]) -> set[str]:
    """Were the samples inside the part of the range the method can resolve?

    A method is not simply right or wrong for a sample; it has a span, and
    readings crowded against the bottom of that span are noise wearing the
    costume of data. This check exists because the first batch contained
    exactly that, and nothing else in the pipeline would have caught it.
    """
    print(chr(10) + "=" * 72)
    print("CHECK 5  Method range against what was measured")
    print("=" * 72)

    by_method: dict[str, list[float]] = defaultdict(list)
    analyte_of: dict[str, str] = {}
    for row in rows:
        try:
            by_method[row["method"]].append(float(row["value"]))
            analyte_of[row["method"]] = row["analyte"]
        except (KeyError, ValueError):
            continue
    unusable: set[str] = set()

    unknown = [m for m in by_method if m == "UNKNOWN"]
    for method in sorted(by_method):
        values = by_method[method]
        if method == "UNKNOWN":
            print(f"  UNKNOWN method: {len(values)} readings")
            print("     No instrument or procedure recorded. The readings cannot")
            print("     be assessed at all, and must not be used until the")
            print("     laboratory says how they were produced.")
            unusable.add(analyte_of[method])
            continue
        if method not in METHOD_SPECS:
            continue
        low, high, step, label = METHOD_SPECS[method]
        lo, hi = min(values), max(values)
        position = hi / high * 100
        under = [v for v in values if v < low]
        negative = [v for v in values if v < 0]
        print(f"  {label}")
        print(f"     method range {low}-{high}; samples {lo:g}-{hi:g} "
              f"(top sample at {position:.0f}% of range)")
        if under:
            print(f"     {len(under)} of {len(values)} readings are BELOW the "
                  f"method's floor of {low:g}")
            if negative:
                print(f"     {len(negative)} of them are negative, which is not "
                      "a concentration at all:")
                print("     the instrument extrapolated off the bottom of its")
                print("     calibration and said so on screen.")
            if len(under) > len(values) / 2:
                unusable.add(analyte_of[method])
                print()
                print("     -> WRONG TEST. Most readings fall outside the range")
                print("        this method is calibrated for, so most of this")
                print("        column is not a measurement. A test covering the")
                print("        concentrations actually present is needed.")
        if step:
            worst = step / lo * 100 if lo else float("inf")
            best = step / hi * 100 if hi else float("inf")
            print(f"     smallest resolvable step {step}: "
                  f"{best:.0f}-{worst:.0f}% of the readings themselves")
            if best > 10:
                unusable.add(analyte_of[method])
                print()
                print("     -> WRONG RANGE. One step of this method is a large")
                print("        fraction of every value it returned here. These")
                print("        numbers do not distinguish the samples from each")
                print("        other or from zero, and no threshold comparison")
                print("        based on them can stand. A low-range method is")
                print("        required and the measurement must be repeated.")
        elif position < 10 and not under:
            print("     -> Readings sit in the bottom tenth of the range;")
            print("        treat small differences between them with care.")
        print()
    return unusable


def check_guidelines(groups: dict, unusable: set[str]) -> None:
    print("\n" + "=" * 72)
    print("CHECK 4  Comparison with drinking-water guideline values")
    print("=" * 72)
    print("ORIENTATION ONLY. This is not a safety assessment. No microbiological")
    print("testing was performed, and contamination that makes spring water")
    print("dangerous is usually microbiological. See README section 9.\n")

    for analyte, (limit, unit, source) in GUIDELINES.items():
        keys = [k for k in groups if k[0] == analyte]
        if not keys:
            continue
        if analyte in unusable:
            print(f"  {analyte} -- COMPARISON WITHDRAWN")
            print("     Check 5 found the measurement cannot support a threshold")
            print("     comparison. Printing the numbers beside a guideline value")
            print("     would lend them an authority the method does not give")
            print("     them, so they are not printed here.")
            print()
            continue
        print(f"  {analyte} -- {limit} {unit} ({source})")
        for key in sorted(keys, key=lambda k: k[1]):
            values = [v for _, v in groups[key]]
            mean = statistics.mean(values)
            flag = "  <-- at or above" if mean >= limit else ""
            print(f"     {key[1]:10} {mean:7.3f}{flag}")
        print()

    hardness_keys = [k for k in groups if k[0] == "hardness"]
    if hardness_keys:
        # Conventional descriptive bands for total hardness as CaCO3. There is
        # no WHO health-based guideline for hardness.
        bands = [(60, "soft"), (120, "moderately hard"), (180, "hard")]
        print("  hardness -- mg/L CaCO3 (no health-based guideline)")
        censored = 0
        for key in sorted(hardness_keys, key=lambda k: k[1]):
            value = statistics.mean(v for _, v in groups[key])
            label = next((name for limit, name in bands if value < limit), "very hard")
            note = ""
            if value >= 425:
                censored += 1
                note = "   (top of strip scale: >= 425, right-censored)"
            print(f"     {key[1]:10} {value:7.0f}  {label}{note}")
        if censored:
            print(f"\n     {censored} of {len(hardness_keys)} readings sit at the top")
            print("     of the strip's range. Their true values are unknown above")
            print("     425 mg/L, so they cannot be compared with each other and")
            print("     any mean computed across them is a lower bound, not an")
            print("     estimate. A titration or a wider-range method is needed")
            print("     before hardness supports any quantitative statement.")
        print()

    ph_keys = [k for k in groups if k[0] == "ph"]
    if ph_keys:
        low, high = PH_OPERATIONAL
        print(f"  ph -- operational range {low}-{high}")
        for key in sorted(ph_keys, key=lambda k: k[1]):
            mean = statistics.mean(v for _, v in groups[key])
            flag = "  <-- outside" if not low <= mean <= high else ""
            print(f"     {key[1]:10} {mean:7.3f}{flag}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="lab results CSV")
    args = parser.parse_args()
    if not args.path.exists():
        print(f"No such file: {args.path}", file=sys.stderr)
        return 1

    rows = load(args.path)
    groups = grouped(rows)

    print(f"{args.path}: {len(rows)} rows, "
          f"{len({r['spring_id'] for r in rows})} springs, "
          f"{len({r['analyte'] for r in rows})} analytes")

    unknown_units = sorted(
        {r["analyte"] for r in rows if r.get("unit") == "unknown"}
    )
    if unknown_units:
        print(f"\nWARNING: unit not reported for: {', '.join(unknown_units)}")
        print("These are excluded from every comparison below. A value whose")
        print("unit is unknown cannot be interpreted, only stored.")

    report_table(groups)
    check_replicate_order(groups)
    check_zero_dispersion(groups)
    check_method_disagreement(rows)
    unusable = check_method_fit(rows)
    check_guidelines(groups, unusable)
    return 0


if __name__ == "__main__":
    sys.exit(main())
