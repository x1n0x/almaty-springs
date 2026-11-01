"""Turn the laboratory's reported batch into the long-format results table.

The raw report arrives as free text with Russian labels, replicates separated
by semicolons and a decimal separator that switches between "." and ","
mid-document. Parsing it in code rather than retyping it into a spreadsheet
keeps the transcription reviewable: the raw file stays in data/field/, the
mapping lives here, and a mistake in either is visible in a diff.

Usage:
    python src/ingest_lab.py data/field/lab_raw_2026-10-25.txt \
        --out data/field/lab_results_2026-10-25.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

FIELDNAMES = [
    "spring_id", "sample_id", "replicate", "analyte", "value", "unit",
    "below_lod", "lod", "method", "lab", "analyst", "sampled_at",
    "analysed_at", "notes",
]

# The laboratory numbers its samples 1-6 in the order the sites were visited,
# which is the order the field folders were numbered. Recorded explicitly
# because it is an assumption, not something the report states.
SAMPLE_TO_SPRING = {n: f"ALA-{n:04d}" for n in range(1, 7)}

# Visit times from data/field/springs_2026-10-25.csv, used as the sampling
# time. They are the time of the first photograph at each site, so they are
# accurate to a few minutes, not to the second.
SAMPLED_AT = {
    1: "2026-10-25T14:15:17+05:00",
    2: "2026-10-25T14:35:25+05:00",
    3: "2026-10-25T14:49:44+05:00",
    4: "2026-10-25T15:51:00+05:00",
    5: "2026-10-25T16:13:04+05:00",
    6: "2026-10-25T16:23:41+05:00",
}

# (header pattern as it appears in the report, analyte, unit, note)
#
# The patterns are matched against the report's own Russian headings rather
# than against English analyte names -- the heading for hardness is Russian
# only, and keying on "hardness" silently produced zero rows.
#
# `unit` of "unknown" is deliberate and must not be guessed: see the open
# questions at the end of the raw file.
SECTIONS = [
    (r"Cl2", "free_chlorine", "mg/L", "unit confirmed by the lab"),
    (r"на\s+pH", "ph", "pH", ""),
    (r"NO2", "nitrite", "mg/L", "confirmed by the lab as NO2- (the ion), not NO2-N"),
    (r"SO4\s*\(2-\)", "sulfate", "mg/L", ""),  # method set below
    (r"Fe", "iron", "mg/L", ""),
    # The report spells it "жестокость"; the intended word is "жёсткость".
    (r"жест[оё]к", "hardness", "mg/L CaCO3", ""),
]

# Total-hardness strip, grains per gallon -> mg/L CaCO3, taken from the
# manufacturer's own six-level chart rather than from the textbook factor of
# 17.118. The strip only ever returns one of these six levels, so converting a
# quantised reading with a more precise factor would invent resolution the
# measurement does not have.
#
# The laboratory reported the gpg column: 7 and 15 appear nowhere in the ppm
# column, which settles which of the two columns was being read.
HARDNESS_GPG_TO_PPM = {0: 0, 1.5: 25, 3: 50, 7: 120, 15: 250, 25: 425}
HARDNESS_TOP_OF_SCALE = 25  # gpg; readings here are right-censored

LAB = "DKU"
ANALYST = "Elizaveta Katkova"
ANALYSED_AT = "2026-10-26"

# Sulfate was measured by two deliveries of the same barium-chloride
# turbidimetric chemistry. The designations are provisional: the instrument
# was not identified, so these are the Hach names and the Merck Spectroquant
# equivalents would differ. The working ranges, not the brand, are what the
# analysis relies on.
SULFATE_POWDER = "turbidimetric_BaCl2_powder"      # approx. 2-70 mg/L
SULFATE_CUVETTE = "turbidimetric_BaCl2_cuvette"    # approx. 40-150 mg/L


def parse_number(token: str) -> float:
    return float(token.strip().replace(",", "."))


def parse_block(text: str, header: str) -> dict[int, list[float]]:
    """Pull the 'Проба N: a ; b ; c' lines that follow a section header."""
    lines = text.splitlines()
    pattern = re.compile(header, re.IGNORECASE)
    start = next((i for i, line in enumerate(lines) if pattern.search(line)), None)
    if start is None:
        raise SystemExit(f"section not found in raw file: {header}")

    results: dict[int, list[float]] = {}
    for line in lines[start + 1 :]:
        match = re.match(r"\s*Проба\s*(\d+)\s*:\s*(.+)", line)
        if not match:
            # Stop at the first non-sample line once samples have been seen,
            # so one section cannot swallow the next.
            if results and line.strip():
                break
            continue
        number = int(match.group(1))
        values = [parse_number(t) for t in match.group(2).split(";") if t.strip()]
        results[number] = values
    return results


def rows_for(
    analyte: str, unit: str, note: str, block: dict[int, list[float]], method: str
) -> list[dict]:
    out: list[dict] = []
    for sample, values in sorted(block.items()):
        for index, value in enumerate(values, start=1):
            row_note = note
            stored = value

            if analyte == "hardness":
                if value not in HARDNESS_GPG_TO_PPM:
                    raise SystemExit(
                        f"hardness {value} is not a level on the strip chart"
                    )
                stored = HARDNESS_GPG_TO_PPM[value]
                row_note = f"strip reading {value:g} gpg, converted with the chart"
                if value >= HARDNESS_TOP_OF_SCALE:
                    row_note += (
                        "; TOP OF SCALE -- right-censored, true value is >= "
                        f"{stored} and the strip cannot resolve how much more"
                    )

            # A reported zero means the sample read the same as distilled
            # water, which the lab confirmed. That is a non-detect, not a
            # measured zero. The numeric limit was not supplied, so `lod`
            # stays empty: the flag is known, the threshold is not.
            below_lod = "true" if (stored == 0 and analyte != "ph") else ""

            row = dict.fromkeys(FIELDNAMES, "")
            row.update(
                {
                    "spring_id": SAMPLE_TO_SPRING[sample],
                    "sample_id": f"P{sample}",
                    "replicate": index if len(values) > 1 else "",
                    "analyte": analyte,
                    "value": f"{stored:g}",
                    "unit": unit,
                    "below_lod": below_lod,
                    "method": method,
                    "analyst": ANALYST,
                    "analysed_at": ANALYSED_AT,
                    "lab": LAB,
                    "sampled_at": SAMPLED_AT[sample],
                    "notes": row_note,
                }
            )
            out.append(row)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path, help="raw laboratory report")
    parser.add_argument(
        "--out", type=Path, default=Path("data/field/lab_results_2026-10-25.csv")
    )
    args = parser.parse_args()

    if not args.raw.exists():
        print(f"No such file: {args.raw}", file=sys.stderr)
        return 1
    text = args.raw.read_text(encoding="utf-8")

    rows: list[dict] = []
    for header, analyte, unit, note in SECTIONS:
        block = parse_block(text, header)
        if sorted(block) != list(range(1, 7)):
            raise SystemExit(
                f"{analyte}: expected samples 1-6, parsed {sorted(block)}"
            )
        method = SULFATE_POWDER if analyte == "sulfate" else ""
        rows += rows_for(analyte, unit, note, block, method=method)

    # Sample 4 was re-measured for sulfate by a second method the lab calls a
    # "точная проба". Kept as its own row rather than replacing the routine
    # value: the gap between the two is the only estimate of the routine
    # method's bias that this batch contains.
    reference = dict.fromkeys(FIELDNAMES, "")
    reference.update(
        {
            "spring_id": SAMPLE_TO_SPRING[4],
            "sample_id": "P4",
            "analyte": "sulfate",
            "value": "65.7",
            "unit": "mg/L",
            "method": SULFATE_CUVETTE,
            "analyst": ANALYST,
            "analysed_at": ANALYSED_AT,
            "lab": LAB,
            "sampled_at": SAMPLED_AT[4],
            "notes": 'reported by the lab as "точная проба" (reference measurement)',
        }
    )
    rows.append(reference)

    rows.sort(key=lambda r: (r["spring_id"], r["analyte"], str(r["replicate"])))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    by_analyte: dict[str, int] = {}
    for row in rows:
        by_analyte[row["analyte"]] = by_analyte.get(row["analyte"], 0) + 1
    print(f"Wrote {len(rows)} rows to {args.out}")
    for analyte, count in sorted(by_analyte.items()):
        print(f"  {analyte:16} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
