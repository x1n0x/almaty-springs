"""Render the campaign's results as a dashboard and as figures for the README.

Writes two things from the same two CSV files:

  index.html                     the dashboard GitHub Pages serves at the root
  reports/figures/*.svg          static figures the README embeds

Every number on the page is computed here from data/field/, through the same
functions src/summarise_lab.py prints from, so the dashboard, the figures and
the printed report cannot drift apart. Nothing is typed in by hand except
wording.

Standard library only, like the rest of src/. The charts are SVG written
directly; the page loads Leaflet for its map and degrades to a page without a
map when that is unavailable.

Usage:
    python src/make_dashboard.py
    python src/make_dashboard.py --out index.html --figures reports/figures
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import statistics
import sys
from pathlib import Path

import summarise_lab

REPO_URL = "https://github.com/x1n0x/almaty-springs"
LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"
LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"

# The spring every chart emphasises until the reader picks another. It is the
# one the README's argument is about.
DEFAULT_SPRING = "ALA-0004"

# Charts of what the water showed: key, title, unit, form, axis domain, ticks,
# decimals used on the axis.
#
# Concentrations are ratio scales and get bars from zero. pH is logarithmic
# and temperature in Celsius has an arbitrary zero, so a bar's length would
# mean nothing for either: those two get dots on a position scale instead.
PANELS = [
    ("ph", "pH", "", "dot", (6.5, 8.5), (6.5, 7.0, 7.5, 8.0, 8.5), 1),
    ("hardness", "Total hardness", "mg/L CaCO3", "bar", (0, 500), (0, 250, 500), 0),
    ("sulfate", "Sulfate", "mg/L", "bar", (0, 60), (0, 20, 40, 60), 0),
    ("copper", "Copper", "mg/L", "bar", (0, 0.15), (0, 0.05, 0.10, 0.15), 2),
    ("turbidity", "Turbidity", "NTU", "bar", (0, 1.5), (0, 0.5, 1.0, 1.5), 1),
    ("water_temp", "Water temperature", "°C", "dot", (0, 15), (0, 5, 10, 15), 0),
]

TITLES = {
    "ph": "pH", "hardness": "Total hardness", "sulfate": "Sulfate",
    "copper": "Copper", "turbidity": "Turbidity", "chlorine": "Chlorine",
    "nitrite": "Nitrite", "ammonium": "Ammonium", "iron": "Iron",
}
UNITS = {
    "ph": "", "hardness": "mg/L CaCO3", "sulfate": "mg/L", "copper": "mg/L",
    "turbidity": "NTU", "chlorine": "mg/L", "nitrite": "mg/L",
    "ammonium": "mg/L NH4-N", "iron": "mg/L",
}

# How each method is named on the page. Wording only; ranges and verdicts
# come from summarise_lab.
METHOD_NAMES = {
    "hach_dr3900_prog680_SulfaVer4": "SulfaVer 4, DR 3900 programme 680",
    "hach_cuvette_test_barcoded": "barcoded cuvette test, one sample",
    "hach_dr3900_CuVer1_bicinchoninate": "CuVer 1, DR 3900",
    "hach_dr3900_prog88_DPD_530nm": "DPD, DR 3900 programme 88",
    "test_strip_total_hardness": "six-level test strip",
    "hach_dr3900_prog373_NitriVer2_HR": "NitriVer 2 high range, programme 373",
    "hach_lck303_cuvette": "LCK 303 cuvette test",
    "UNKNOWN": "method not recorded",
}

# Order of the method rows: what fitted first, what did not last.
METHOD_ORDER = [
    "hach_dr3900_prog680_SulfaVer4",
    "hach_cuvette_test_barcoded",
    "hach_dr3900_CuVer1_bicinchoninate",
    "hach_dr3900_prog88_DPD_530nm",
    "test_strip_total_hardness",
    "hach_dr3900_prog373_NitriVer2_HR",
    "hach_lck303_cuvette",
    "UNKNOWN",
]

HARDNESS_STRIP_RANGE = (25, 425)   # lowest and highest non-zero chart levels

LIGHT = {
    "page": "#f4f7f7", "surface": "#ffffff", "ink": "#10242b", "ink2": "#47595f",
    "muted": "#647479", "grid": "#dfe6e7", "axis": "#b9c5c8",
    "accent": "#2a78d6", "dim": "#a9b5b9",
    "good": "#0ca30c", "warn": "#fab219", "bad": "#d03b3b", "bando": ".16",
}
DARK = {
    "page": "#0e171b", "surface": "#16232a", "ink": "#e9f0f1", "ink2": "#b4c2c6",
    "muted": "#8a999e", "grid": "#22323a", "axis": "#33464f",
    "accent": "#3987e5", "dim": "#4d5e66",
    "good": "#0ca30c", "warn": "#fab219", "bad": "#d03b3b", "bando": ".30",
}
SYSTEM_FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def notes_dict(row: dict) -> dict[str, str]:
    return dict(
        part.split("=", 1)
        for part in (row.get("notes") or "").split("; ")
        if "=" in part
    )


def fmt(key: str, value: float) -> str:
    """A value as the page prints it, with a true minus sign."""
    if key == "ph":
        text = f"{value:.2f}"
    elif key == "hardness":
        text = f"{value:.0f}"
    else:
        text = f"{round(value, 3):g}"
    return text.replace("-", "−")


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


NUMBER_WORDS = ("zero one two three four five six seven eight nine ten "
                "eleven twelve").split()


def words(count: int) -> str:
    """Small counts in running text are spelled out."""
    return NUMBER_WORDS[count] if 0 <= count < len(NUMBER_WORDS) else str(count)


def cap(text: str) -> str:
    """Capitalise a sentence without lowercasing the rest of it (pH stays pH)."""
    if text.startswith("pH"):
        return text
    return text[:1].upper() + text[1:]


def load_photos(path: Path | None) -> dict[str, list[dict]]:
    """Photographs per spring from the manifest, in the order it lists them.

    A photograph the manifest names but the repository does not hold is an
    error rather than a gap: the page would otherwise ship a broken image.
    """
    if path is None or not path.exists():
        return {}
    root = Path(__file__).resolve().parent.parent
    out: dict[str, list[dict]] = {}
    for row in read_rows(path):
        if not (root / row["file"]).exists():
            raise SystemExit(f"{path}: {row['file']} is listed but missing")
        out.setdefault(row["spring_id"], []).append(
            {"file": row["file"], "caption": row["caption"]})
    return out


def build_results(springs_path: Path, lab_path: Path,
                  photos_path: Path | None = None) -> dict:
    """Everything the page shows, as plain data."""
    spring_rows = read_rows(springs_path)
    photos = load_photos(photos_path)
    lab_rows = read_rows(lab_path)
    groups = summarise_lab.grouped(lab_rows)

    springs = []
    for number, row in enumerate(spring_rows, start=1):
        notes = notes_dict(row)
        springs.append({
            "id": row["spring_id"],
            "n": number,
            "name": row.get("name_local") or "",
            "translit": row.get("name_translit") or "",
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "elev": int(float(row["elevation_m"])),
            "water": float(row["water_temp_c"]),
            "air": float(row["air_temp_c"]),
            "visited": row["measured_at"][11:16],
            "date": row["measured_at"][:10],
            "photos": int(notes.get("photos", "0")),
            "osm": row.get("osm_id") or "",
            "osm_m": notes.get("osm_match_m", ""),
            # What a sign at the site calls it, where there is one.
            "sign": notes.get("sign_en", ""),
            "sign_elev": notes.get("sign_elev_m", ""),
            "shots": photos.get(row["spring_id"], []),
        })
    ids = [s["id"] for s in springs]

    censored = {
        (r["analyte"], r["spring_id"])
        for r in lab_rows if "TOP OF SCALE" in (r.get("notes") or "")
    }
    flagged: dict[str, int] = {}
    totals: dict[str, int] = {}
    for row in lab_rows:
        if row.get("method") in summarise_lab.SECONDARY_METHODS:
            continue
        totals[row["analyte"]] = totals.get(row["analyte"], 0) + 1
        if row.get("below_lod") == "true":
            flagged[row["analyte"]] = flagged.get(row["analyte"], 0) + 1

    analytes: dict[str, dict] = {}
    for analyte in sorted({a for a, _ in groups}):
        per_spring = {}
        for sid in ids:
            values = [v for _, v in groups.get((analyte, sid), [])]
            if not values:
                continue
            per_spring[sid] = {
                "values": values,
                "mean": statistics.mean(values),
                "censored": (analyte, sid) in censored,
            }
        analytes[analyte] = {
            "title": TITLES.get(analyte, analyte),
            "unit": UNITS.get(analyte, ""),
            "springs": per_spring,
            "n": totals.get(analyte, 0),
            "below": flagged.get(analyte, 0),
        }
    analytes["water_temp"] = {
        "title": "Water temperature", "unit": "°C", "n": len(springs),
        "below": 0,
        "springs": {
            s["id"]: {"values": [s["water"]], "mean": s["water"], "censored": False}
            for s in springs
        },
    }

    fits = {e["method"]: e for e in summarise_lab.method_fit(lab_rows)}
    unusable = {
        e["analyte"] for e in fits.values()
        if e["verdict"] in summarise_lab.UNUSABLE_VERDICTS
    }

    # Where each analyte stands, in the README's own four categories.
    status: dict[str, str] = {}
    for analyte, entry in analytes.items():
        if analyte == "water_temp":
            continue
        if analyte in unusable:
            status[analyte] = "unusable"
        elif any(s["censored"] for s in entry["springs"].values()):
            status[analyte] = "censored"
        elif entry["below"] > entry["n"] / 2:
            status[analyte] = "nondetect"
        else:
            status[analyte] = "usable"

    methods = build_method_rows(lab_rows, fits, analytes, ids)
    replicates = summarise_lab.replicate_order(groups)

    guidelines = []
    for analyte, (limit, unit, source) in summarise_lab.GUIDELINES.items():
        if analyte in unusable or analyte not in analytes:
            continue
        means = {sid: s["mean"] for sid, s in analytes[analyte]["springs"].items()}
        top = max(means.values())
        guidelines.append({
            "analyte": analyte, "title": TITLES[analyte], "limit": limit,
            "unit": unit, "source": source, "means": means,
            "top": top, "share": top / limit * 100,
        })
    withdrawn = sorted(a for a in summarise_lab.GUIDELINES if a in unusable)

    cross = None
    routine = [
        float(r["value"]) for r in lab_rows
        if r["method"] == "hach_dr3900_prog680_SulfaVer4"
        and r["spring_id"] == "ALA-0004"
    ]
    reference = [
        float(r["value"]) for r in lab_rows
        if r["method"] == "hach_cuvette_test_barcoded"
    ]
    if routine and reference:
        a, b = statistics.mean(routine), statistics.mean(reference)
        cross = {"routine": a, "reference": b, "gap_pct": (b - a) / b * 100}

    return {
        "springs": springs,
        "analytes": analytes,
        "status": status,
        "methods": methods,
        "replicates": replicates,
        "guidelines": guidelines,
        "withdrawn": withdrawn,
        "cross": cross,
        "superlatives": superlatives(springs, analytes),
        "counts": {
            "readings": len(lab_rows),
            "analytes": len(status),
            "usable": sum(1 for s in status.values() if s != "unusable"),
            "unusable": sum(1 for s in status.values() if s == "unusable"),
            "photos": sum(s["photos"] for s in springs),
            "unmapped": sum(1 for s in springs if not s["osm"]),
        },
        "analysed": sorted({r["analysed_at"] for r in lab_rows if r.get("analysed_at")}),
        "analysts": sorted({r["analyst"] for r in lab_rows if r.get("analyst")}),
    }


def build_method_rows(lab_rows, fits, analytes, ids) -> list[dict]:
    """One row per method: its working range, where the springs fell, a verdict."""
    values_by_method: dict[str, list[float]] = {}
    means_by_method: dict[str, dict[str, list[float]]] = {}
    for row in lab_rows:
        try:
            value = float(row["value"])
        except (KeyError, ValueError):
            continue
        method = row["method"]
        values_by_method.setdefault(method, []).append(value)
        means_by_method.setdefault(method, {}).setdefault(
            row["spring_id"], []).append(value)

    rows = []
    for method in METHOD_ORDER:
        if method not in values_by_method:
            continue
        values = values_by_method[method]
        analyte = next(r["analyte"] for r in lab_rows if r["method"] == method)
        means = {
            sid: statistics.mean(v) for sid, v in means_by_method[method].items()
        }
        entry = {
            "method": method,
            "analyte": analyte,
            "title": TITLES[analyte],
            "name": METHOD_NAMES.get(method, method),
            "means": means,
            "low": None, "high": None, "step": None, "top_censored": 0,
        }
        fit = fits.get(method)
        zeros = sum(1 for v in values if v == 0)

        if method == "test_strip_total_hardness":
            top = sum(1 for s in analytes["hardness"]["springs"].values()
                      if s["censored"])
            entry.update(
                low=HARDNESS_STRIP_RANGE[0], high=HARDNESS_STRIP_RANGE[1],
                top_censored=top, state="warn", verdict="Top of its scale",
                reason=f"{top} of {len(values)} read the strip's maximum, "
                       f"≥{HARDNESS_STRIP_RANGE[1]}",
            )
        elif fit is None:
            continue
        elif fit["verdict"] == "unknown_method":
            entry.update(
                state="bad", verdict="No method recorded",
                reason="range unknown; the readings cannot be assessed",
            )
        else:
            entry.update(low=fit["low"], high=fit["high"], step=fit["step"])
            if fit["verdict"] == "wrong_range":
                entry.update(
                    state="bad", verdict="Cannot resolve these levels",
                    reason=f"one step, {fit['step']:g}, is "
                           f"{fit['step_best']:.0f}–{fit['step_worst']:.0f}% "
                           "of each reading",
                )
            elif fit["verdict"] == "wrong_test":
                entry.update(
                    state="bad", verdict="Below its range",
                    reason=f"{fit['under']} of {fit['n']} readings under the "
                           f"floor of {fit['low']:g}, {fit['negative']} negative",
                )
            elif zeros > len(values) / 2:
                entry.update(
                    state="good", verdict="Not detected",
                    reason=f"{zeros} of {len(values)} readings at zero",
                )
            elif fit["under"]:
                entry.update(
                    state="good", verdict="In range, at its floor",
                    reason=f"{fit['under']} of {fit['n']} readings below "
                           f"{fit['low']:g}",
                )
            elif len(values) == 1:
                entry.update(
                    state="good", verdict="In range",
                    reason=f"cross-check of one sample, {values[0]:g} mg/L",
                )
            else:
                entry.update(
                    state="good", verdict="In range",
                    reason=f"{min(values):g}–{max(values):g} mg/L on a "
                           f"{fit['low']:g}–{fit['high']:g} method",
                )
        rows.append(entry)
    return rows


def superlatives(springs: list[dict], analytes: dict) -> dict[str, list[str]]:
    """What each spring is the most or least of, among the six.

    A spring is only called the most or the least of something when its
    readings stand clear of every other spring's: the whole spread of its
    replicates has to lie beyond the whole spread of each of the others. A
    lead that the replicates overlap is not a lead. Censored readings are
    skipped, and copper is left out because its readings sit at the floor of
    the method and do not order the springs reliably.
    """
    out: dict[str, list[str]] = {s["id"]: [] for s in springs}

    def consider(spans: dict[str, tuple[float, float]], low_phrase: str,
                 high_phrase: str, skip: set[str] = frozenset(),
                 margin: float = 0.0) -> None:
        for sid, (low, high) in spans.items():
            if sid in skip:
                continue
            rest = [span for other, span in spans.items() if other != sid]
            if low_phrase and all(high + margin <= other_low for other_low, _ in rest):
                out[sid].append(low_phrase)
            if high_phrase and all(low - margin >= other_high for _, other_high in rest):
                out[sid].append(high_phrase)

    def spans(key: str) -> dict[str, tuple[float, float]]:
        return {
            sid: (min(s["values"]), max(s["values"]))
            for sid, s in analytes[key]["springs"].items()
        }

    consider(spans("ph"), "the lowest pH", "the highest pH", margin=0.01)
    consider(spans("sulfate"), "the least sulfate", "the most sulfate", margin=0.5)
    hard = analytes["hardness"]["springs"]
    consider(spans("hardness"), "the softest water", "",
             skip={sid for sid, s in hard.items() if s["censored"]}, margin=1)
    consider(spans("turbidity"), "the clearest water", "the most turbid water",
             margin=0.01)
    # One thermometer reading per spring, so ask for a full degree of daylight.
    consider({s["id"]: (s["water"], s["water"]) for s in springs},
             "the coldest water", "the warmest water", margin=1.0)
    consider({s["id"]: (float(s["elev"]), float(s["elev"])) for s in springs},
             "the lowest elevation", "the highest elevation", margin=1)
    return out


# --------------------------------------------------------------------------
# SVG
# --------------------------------------------------------------------------

def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def chart_css(c: dict[str, str], font: str) -> str:
    """Styles for every chart mark. `c` holds colours or CSS variables."""
    return f"""
.cv text{{font-family:{font}}}
.cv .t-title{{font-size:13px;font-weight:600;fill:{c['ink']}}}
.cv .t-unit{{font-weight:400;fill:{c['muted']}}}
.cv .t-note{{font-size:10.5px;fill:{c['muted']}}}
.cv .t-tick{{font-size:10.5px;fill:{c['muted']};font-variant-numeric:tabular-nums}}
.cv .t-row{{font-size:11px;fill:{c['ink2']};font-variant-numeric:tabular-nums}}
.cv .t-val{{font-size:11.5px;fill:{c['ink']};font-variant-numeric:tabular-nums}}
.cv .t-head{{font-size:17px;font-weight:650;fill:{c['ink']}}}
.cv .t-lead{{font-size:12px;fill:{c['ink2']}}}
.cv .t-name{{font-size:12.5px;font-weight:600;fill:{c['ink']}}}
.cv .t-verdict{{font-size:12px;font-weight:600;fill:{c['ink']}}}
.cv .t-small{{font-size:10.5px;fill:{c['ink2']}}}
.cv .grid{{stroke:{c['grid']};stroke-width:1}}
.cv .axis{{stroke:{c['axis']};stroke-width:1}}
.cv .frame{{fill:{c['page']}}}
.cv .hit{{fill:transparent}}
.cv .bar{{fill:{c['accent']}}}
.cv .tail{{fill:{c['accent']};opacity:.38}}
.cv .dot{{fill:{c['accent']};stroke:{c['page']};stroke-width:2}}
.cv .rep{{stroke:{c['ink']};stroke-width:1.5;stroke-linecap:round;opacity:.72}}
.cv .band{{fill:{c['accent']};opacity:{c['bando']}}}
.cv .pin{{fill:{c['ink2']}}}
.cv .step{{stroke:{c['ink2']};stroke-width:1.5}}
.cv .row.off .bar,.cv .row.off .tail,.cv .row.off .dot{{fill:{c['dim']}}}
.cv .row.off .rep{{opacity:.3}}
.cv .row.off .t-val{{fill:{c['ink2']}}}
.cv .row.on .t-val,.cv .row.on .t-row{{font-weight:650;fill:{c['ink']}}}
.cv .s-good{{fill:{c['good']}}}
.cv .s-warn{{fill:{c['warn']}}}
.cv .s-bad{{fill:{c['bad']}}}
.cv .glyph{{fill:none;stroke:#fff;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}}
.cv .glyph-dark{{fill:none;stroke:#10242b;stroke-width:1.8;stroke-linecap:round}}
.cv .swatch-dim{{fill:{c['dim']}}}
"""


def row_class(sid: str, highlight: str | None) -> str:
    if highlight is None:
        return "row"
    return "row on" if sid == highlight else "row off"


def bar_path(x0: float, x1: float, y: float, h: float, r: float = 4) -> str:
    """A bar that is square at the baseline and rounded at the data end."""
    x1 = max(x1, x0 + 2)
    r = min(r, x1 - x0, h / 2)
    return (
        f"M{x0:.1f},{y:.1f}H{x1 - r:.1f}Q{x1:.1f},{y:.1f} {x1:.1f},{y + r:.1f}"
        f"V{y + h - r:.1f}Q{x1:.1f},{y + h:.1f} {x1 - r:.1f},{y + h:.1f}H{x0:.1f}Z"
    )


PANEL_W, PANEL_H = 320, 216
P_LEFT, P_RIGHT, P_TOP, P_PITCH = 30, 244, 46, 24


def panel_note(key: str, results: dict) -> str:
    analyte = results["analytes"][key]
    if key == "ph":
        return "mean of three readings; axis spans the operational range"
    if key == "hardness":
        top = sum(1 for s in analyte["springs"].values() if s["censored"])
        return f"test strip; {top} of 6 read its maximum, so true values are higher"
    if key == "copper":
        return "at the floor of the method; do not rank the springs on it"
    if key == "turbidity":
        return "ticks are the three readings; they fall as particles settle"
    if key == "water_temp":
        return "one field reading per spring"
    if key == "sulfate":
        return "three identical readings at every spring"
    return ""


def tip(spring: dict, key: str, entry: dict, unit: str) -> str:
    """Tooltip text: who, the readings, and the mean."""
    readings = ", ".join(fmt(key, v) for v in entry["values"])
    unit_text = f" {unit}" if unit else ""
    head = f"Spring {spring['n']}, {spring['id']}"
    if entry["censored"]:
        return f"{head}|≥{fmt(key, entry['mean'])}{unit_text}|top of the strip's scale"
    if len(entry["values"]) == 1:
        return f"{head}|{readings}{unit_text}|single reading"
    return f"{head}|{readings}{unit_text}|mean {fmt(key, entry['mean'])}"


def panel_svg(panel: tuple, results: dict, highlight: str | None) -> str:
    """One small-multiple chart: six springs, one measurement."""
    key, title, unit, form, (lo, hi), ticks, decimals = panel
    data = results["analytes"][key]["springs"]

    def sx(value: float) -> float:
        return P_LEFT + (value - lo) / (hi - lo) * (P_RIGHT - P_LEFT)

    for sid, entry in data.items():
        for value in entry["values"]:
            if not lo <= value <= hi:
                raise SystemExit(f"{key} at {sid}: {value} is off the axis {lo}-{hi}")

    bottom = P_TOP + P_PITCH * len(results["springs"])
    out = [
        f'<text class="t-title" x="8" y="17">{esc(title)}'
        + (f' <tspan class="t-unit">{esc(unit)}</tspan>' if unit else "")
        + "</text>",
        f'<text class="t-note" x="8" y="33">{esc(panel_note(key, results))}</text>',
    ]
    for tick in ticks:
        x = sx(tick)
        cls = "axis" if (form == "bar" and tick == lo) else "grid"
        out.append(f'<line class="{cls}" x1="{x:.1f}" y1="{P_TOP}" x2="{x:.1f}" y2="{bottom}"/>')
        out.append(
            f'<text class="t-tick" x="{x:.1f}" y="{bottom + 15}" '
            f'text-anchor="middle">{tick:.{decimals}f}</text>'
        )

    for index, spring in enumerate(results["springs"]):
        sid = spring["id"]
        entry = data.get(sid)
        if entry is None:
            continue
        cy = P_TOP + index * P_PITCH + P_PITCH / 2
        mean_x = sx(entry["mean"])
        label_x = max([mean_x] + [sx(v) for v in entry["values"]]) + 8
        label = fmt(key, entry["mean"])

        out.append(
            f'<g class="{row_class(sid, highlight)}" data-spring="{esc(sid)}" '
            f'data-tip="{esc(tip(spring, key, entry, unit))}">'
        )
        out.append(f'<rect class="hit" x="0" y="{cy - P_PITCH / 2:.1f}" '
                   f'width="{PANEL_W}" height="{P_PITCH}"/>')
        out.append(f'<text class="t-row" x="14" y="{cy + 4:.1f}" '
                   f'text-anchor="middle">{spring["n"]}</text>')
        if form == "bar":
            out.append(f'<path class="bar" d="{bar_path(sx(lo), mean_x, cy - 6, 12)}"/>')
            if entry["censored"]:
                # The strip cannot read past its top level, so the bar is
                # drawn open-ended rather than as if it stopped there.
                out.append(f'<rect class="tail" x="{mean_x + 2:.1f}" y="{cy - 6:.1f}" '
                           f'width="12" height="12" rx="2"/>')
                label_x = mean_x + 14 + 7
                label = "≥" + label
        else:
            out.append(f'<line class="grid" x1="{P_LEFT}" y1="{cy:.1f}" '
                       f'x2="{P_RIGHT}" y2="{cy:.1f}"/>')
        # Readings that all sit inside the dot would only show as specks
        # around it; the tooltip and the table carry them instead.
        hidden = form == "dot" and all(
            abs(sx(v) - mean_x) < 6 for v in entry["values"])
        if len(set(entry["values"])) > 1 and not hidden:
            for value in entry["values"]:
                x = sx(value)
                out.append(f'<line class="rep" x1="{x:.1f}" y1="{cy - 9:.1f}" '
                           f'x2="{x:.1f}" y2="{cy + 9:.1f}"/>')
        if form == "dot":
            out.append(f'<circle class="dot" cx="{mean_x:.1f}" cy="{cy:.1f}" r="5.5"/>')
            label_x = max(label_x, mean_x + 12)
        out.append(f'<text class="t-val" x="{label_x:.1f}" y="{cy + 4:.1f}">{esc(label)}</text>')
        out.append("</g>")
    return "".join(out)


LOG_LO, LOG_HI = -2, 3     # the method chart runs from 0.01 to 1000 mg/L


def status_icon(state: str, x: float, y: float) -> str:
    """A status mark that differs in shape as well as colour."""
    if state == "good":
        return (f'<circle class="s-good" cx="{x}" cy="{y}" r="7.5"/>'
                f'<path class="glyph" d="M{x - 3.4},{y + 0.2}l2.4,2.5l4.4,-5"/>')
    if state == "warn":
        return (f'<path class="s-warn" d="M{x},{y - 8}l8.4,14.6h-16.8z"/>'
                f'<path class="glyph-dark" d="M{x},{y - 2.6}v4.2M{x},{y + 4.2}v.2"/>')
    return (f'<rect class="s-bad" x="{x - 7.5}" y="{y - 7.5}" width="15" height="15" rx="3"/>'
            f'<path class="glyph" d="M{x - 3},{y - 3}l6,6M{x + 3},{y - 3}l-6,6"/>')


def methods_svg(results: dict, layout: str, highlight: str | None) -> tuple[str, int, int]:
    """Each method's working range against where the six springs fell.

    A logarithmic axis, because the ranges and the readings span five orders
    of magnitude between them. Zero and negative results cannot sit on a log
    axis, so they are counted at its left edge instead of being dropped.
    """
    wide = layout == "wide"
    width = 960 if wide else 340
    sx0, sx1 = (228, 668) if wide else (18, 322)
    pitch = 50 if wide else 106
    top = 34 if wide else 50
    rows = results["methods"]
    by_id = {s["id"]: s for s in results["springs"]}

    def sx(value: float) -> float:
        frac = (math.log10(value) - LOG_LO) / (LOG_HI - LOG_LO)
        return sx0 + min(max(frac, 0), 1) * (sx1 - sx0)

    split = next((i for i, r in enumerate(rows) if r["state"] == "bad"), len(rows))
    gap = 14
    height = top + pitch * len(rows) + gap + 46

    out = []
    grid_bottom = top + pitch * len(rows) + gap
    for power in range(LOG_LO, LOG_HI + 1):
        x = sx(10 ** power)
        out.append(f'<line class="grid" x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{grid_bottom}"/>')
        label = f"{10 ** power:g}"
        out.append(f'<text class="t-tick" x="{x:.1f}" y="{top - 8}" text-anchor="middle">{label}</text>')
    if wide:
        out.append(f'<text class="t-note" x="0" y="{top - 8}">mg/L, log scale</text>')
    else:
        out.append(f'<text class="t-note" x="{sx1 + 8}" y="{top - 26}" '
                   'text-anchor="end">mg/L, log scale</text>')

    for index, row in enumerate(rows):
        y0 = top + index * pitch + (gap if index >= split else 0)
        cy = y0 + (25 if wide else 48)
        if index == split and split:
            out.append(f'<line class="axis" x1="0" y1="{y0 - gap / 2 + 0.5:.1f}" '
                       f'x2="{width}" y2="{y0 - gap / 2 + 0.5:.1f}"/>')

        if wide:
            out.append(f'<text class="t-name" x="0" y="{cy - 2}">{esc(row["title"])}</text>')
            out.append(f'<text class="t-small" x="0" y="{cy + 13}">{esc(row["name"])}</text>')
        else:
            out.append(f'<text class="t-name" x="10" y="{y0 + 16}">{esc(row["title"])} '
                       f'<tspan class="t-unit" font-size="10.5">{esc(row["name"])}</tspan></text>')

        if row["high"] is not None:
            left = sx0 if not row["low"] or row["low"] <= 0 else sx(row["low"])
            right = sx(row["high"])
            out.append(f'<rect class="band" x="{left:.1f}" y="{cy - 8}" '
                       f'width="{right - left:.1f}" height="16" rx="3"/>')
        if row["step"]:
            x = sx(row["step"])
            out.append(f'<line class="step" x1="{x:.1f}" y1="{cy - 12}" x2="{x:.1f}" y2="{cy + 12}"/>')
            out.append(f'<text class="t-small" x="{x - 5:.1f}" y="{cy - 12}" '
                       f'text-anchor="end">one step, {row["step"]:g}</text>')

        at_zero = [sid for sid, v in row["means"].items() if v <= 0]
        if at_zero:
            negative = any(row["means"][sid] < 0 for sid in at_zero)
            words = "below zero" if negative else "at zero"
            out.append(f'<path class="pin" d="M{sx0 - 1},{cy}l8,-5.5v11z"/>')
            out.append(f'<text class="t-small" x="{sx0 + 11}" y="{cy - 12}">'
                       f'{plural(len(at_zero), "spring")} {words}</text>')

        for sid, mean in sorted(row["means"].items()):
            if mean <= 0:
                continue
            spring = by_id[sid]
            x = sx(mean)
            unit = UNITS[row["analyte"]]
            text = fmt(row["analyte"], mean)
            capped = row["top_censored"] and mean >= row["high"]
            out.append(
                f'<g class="{row_class(sid, highlight)}" data-spring="{esc(sid)}" '
                f'data-tip="{esc("Spring %d, %s|%s%s %s|mean, %s" % (spring["n"], sid, chr(0x2265) if capped else "", text, unit, row["title"].lower()))}">'
                f'<circle class="hit" cx="{x:.1f}" cy="{cy}" r="12"/>'
                f'<circle class="dot" cx="{x:.1f}" cy="{cy}" r="4.5"/></g>'
            )
        if row["top_censored"]:
            x = sx(row["high"])
            out.append(f'<path class="pin" d="M{x + 17},{cy}l-8,-5.5v11z"/>')

        vx = 700 if wide else 18
        vy = cy - 4 if wide else y0 + 74
        out.append(status_icon(row["state"], vx + 8, vy))
        out.append(f'<text class="t-verdict" x="{vx + 23}" y="{vy + 4}">{esc(row["verdict"])}</text>')
        out.append(f'<text class="t-small" x="{vx + 23}" y="{vy + 19}">{esc(row["reason"])}</text>')

    ly = height - 14
    lx = 0 if wide else 10
    out.append(f'<rect class="band" x="{lx}" y="{ly - 10}" width="26" height="12" rx="3"/>')
    out.append(f'<text class="t-small" x="{lx + 32}" y="{ly}">working range of the method</text>')
    out.append(f'<circle class="dot" cx="{lx + 200}" cy="{ly - 4}" r="4.5"/>')
    out.append(f'<text class="t-small" x="{lx + 210}" y="{ly}">mean of one spring</text>')
    if wide:
        out.append(f'<path class="pin" d="M{lx + 335},{ly - 4}l8,-5.5v11z"/>')
        out.append(f'<text class="t-small" x="{lx + 349}" y="{ly}">readings at or below zero, '
                   'which a log axis cannot place</text>')
    return "".join(out), width, height


def svg_document(inner: str, width: int, height: int, theme: dict, title: str) -> str:
    """Wrap chart markup as a standalone SVG file with its own colours."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" class="cv" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-label="{esc(title)}">'
        f"<title>{esc(title)}</title>"
        f"<style>{chart_css(theme, SYSTEM_FONT)}</style>"
        f'<rect class="frame" width="{width}" height="{height}" rx="10"/>'
        f"{inner}</svg>\n"
    )


def chemistry_figure(results: dict, theme: dict) -> str:
    """The six small multiples as one figure, with the default spring picked out."""
    pad, head = 20, 76
    width = pad * 2 + PANEL_W * 3
    height = head + PANEL_H * 2 + 24 + pad
    spring = next(s for s in results["springs"] if s["id"] == DEFAULT_SPRING)
    title = f"{DEFAULT_SPRING} against the other five springs"
    out = [
        f'<text class="t-head" x="{pad + 8}" y="34">{esc(title)}</text>',
        f'<text class="t-lead" x="{pad + 8}" y="54">Six springs above Almaty, sampled '
        f'25 October 2026. Rows are the springs in the order they were visited.</text>',
        f'<rect class="bar" x="{width - pad - 262}" y="24" width="12" height="12" rx="2"/>',
        f'<text class="t-small" x="{width - pad - 244}" y="34">spring {spring["n"]}, {DEFAULT_SPRING}</text>',
        f'<rect class="swatch-dim" x="{width - pad - 114}" y="24" width="12" height="12" rx="2"/>',
        f'<text class="t-small" x="{width - pad - 96}" y="34">the other five</text>',
    ]
    for index, panel in enumerate(PANELS):
        x = pad + (index % 3) * PANEL_W
        y = head + (index // 3) * (PANEL_H + 24)
        out.append(f'<g transform="translate({x},{y})">{panel_svg(panel, results, DEFAULT_SPRING)}</g>')
    return svg_document("".join(out), width, height, theme, title)


def methods_figure(results: dict, theme: dict) -> str:
    pad, head = 28, 70
    inner, width, height = methods_svg(results, "wide", None)
    counts = results["counts"]
    title = cap(f"{words(counts['usable'])} of {words(counts['analytes'])} analytes "
                "were measured by a method that fits spring water")
    out = [
        f'<text class="t-head" x="{pad}" y="34">{esc(title)}</text>',
        f'<text class="t-lead" x="{pad}" y="54">Each method’s working range against '
        'where the six springs fell.</text>',
        f'<g transform="translate({pad},{head})">{inner}</g>',
    ]
    return svg_document("".join(out), width + pad * 2, height + head + 14, theme, title)


def inline_svg(inner: str, width: int, height: int, label: str, extra: str = "") -> str:
    return (f'<svg class="cv {extra}" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{esc(label)}">{inner}</svg>')


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

def css_vars(theme: dict) -> str:
    return "".join(f"--{k}:{v};" for k, v in theme.items())


def picker_html(results: dict) -> str:
    """The six stops of the afternoon, placed by elevation. Also the selector."""
    lo, hi = 1100, 1800
    out = []
    for spring in results["springs"]:
        pos = (spring["elev"] - lo) / (hi - lo) * 100
        pressed = "true" if spring["id"] == DEFAULT_SPRING else "false"
        out.append(
            f'<button type="button" class="stop" data-pick="{esc(spring["id"])}" '
            f'aria-pressed="{pressed}" aria-label="Spring {spring["n"]}, {esc(spring["id"])}, '
            f'{spring["elev"]} metres">'
            f'<span class="stop-track"><span class="stop-line" style="height:{pos:.1f}%"></span>'
            f'<span class="stop-dot" style="bottom:{pos:.1f}%"></span></span>'
            f'<span class="stop-n">{spring["n"]}</span>'
            f'<span class="stop-elev">{spring["elev"]} m</span>'
            f'<span class="stop-meta"><span class="stop-time">{esc(spring["visited"])}, </span>'
            f'{fmt("t", spring["water"])} °C</span>'
            f"</button>"
        )
    lines = "".join(
        f'<span class="alt" style="bottom:{(m - lo) / (hi - lo) * 100:.1f}%"><i>{m} m</i></span>'
        for m in (1200, 1500, 1800)
    )
    return (f'<div class="stops"><div class="alts" aria-hidden="true">{lines}</div>'
            f'{"".join(out)}</div>')


def guideline_html(results: dict) -> str:
    out = []
    for g in sorted(results["guidelines"], key=lambda g: -g["share"]):
        dots = "".join(
            f'<span class="gdot row{" on" if sid == DEFAULT_SPRING else " off"}" '
            f'data-spring="{esc(sid)}" style="left:{min(mean / g["limit"] * 100, 100):.2f}%" '
            f'data-tip="{esc("%s|%s %s|%.1f%% of %g" % (sid, fmt(g["analyte"], mean), g["unit"], mean / g["limit"] * 100, g["limit"]))}"></span>'
            for sid, mean in g["means"].items()
        )
        share = "under 1%" if g["share"] < 1 else f"{g['share']:.0f}%"
        out.append(
            f'<div class="g-row"><div class="g-name"><b>{esc(g["title"])}</b>'
            f'<span>{g["limit"]:g} {esc(g["unit"])}: {esc(g["source"])}</span></div>'
            f'<div class="g-track"><span class="g-end" aria-hidden="true"></span>{dots}</div>'
            f'<div class="g-fig">highest spring at <b>{share}</b></div></div>'
        )
    ph = results["analytes"]["ph"]["springs"]
    lo, hi = summarise_lab.PH_OPERATIONAL
    dots = "".join(
        f'<span class="gdot row{" on" if sid == DEFAULT_SPRING else " off"}" '
        f'data-spring="{esc(sid)}" style="left:{(s["mean"] - lo) / (hi - lo) * 100:.2f}%" '
        f'data-tip="{esc("%s|pH %s|operational range %g to %g" % (sid, fmt("ph", s["mean"]), lo, hi))}"></span>'
        for sid, s in ph.items()
    )
    means = [s["mean"] for s in ph.values()]
    out.append(
        f'<div class="g-row"><div class="g-name"><b>pH</b>'
        f'<span>operational range {lo:g} to {hi:g}; the track is that range</span></div>'
        f'<div class="g-track g-range"><span class="g-end" aria-hidden="true"></span>{dots}</div>'
        f'<div class="g-fig">all six inside, <b>{fmt("ph", min(means))} to {fmt("ph", max(means))}</b></div></div>'
    )
    return "".join(out)


def replicate_html(results: dict) -> str:
    rep = results["replicates"]
    out = []
    quiet = []
    for analyte, count in rep["analytes"].items():
        if not count["sets"]:
            quiet.append(TITLES[analyte].lower())
            continue
        share = count["first_max"] / count["sets"] * 100
        out.append(
            f'<div class="r-row" data-tip="{esc("%s|%d of %d triplicates|first reading the highest" % (TITLES[analyte], count["first_max"], count["sets"]))}">'
            f'<span class="r-name">{esc(TITLES[analyte])}</span>'
            f'<span class="r-track"><span class="r-fill" style="width:{share:.1f}%"></span>'
            f'<span class="r-chance" aria-hidden="true"></span></span>'
            f'<span class="r-fig">{count["first_max"]} of {count["sets"]}</span></div>'
        )
    key = ('<div class="r-key"><i></i>what chance alone would give, one in three</div>')
    note = ""
    if quiet:
        note = (f'<p class="fine">{esc(cap(sentence_list(quiet)))} had no triplicate '
                'whose readings differed, so they say nothing about order and are left out.</p>')
    return f'<div class="r-rows">{"".join(out)}</div>{key}{note}'


def table_html(results: dict) -> str:
    columns = ["ph", "hardness", "sulfate", "copper", "turbidity", "chlorine"]
    head = "".join(
        f'<th scope="col">{esc(TITLES[c])}<span>{esc(UNITS[c]) or "&nbsp;"}</span></th>'
        for c in columns
    )
    body = []
    for spring in results["springs"]:
        cells = []
        for column in columns:
            entry = results["analytes"][column]["springs"].get(spring["id"])
            if entry is None:
                cells.append("<td></td>")
            elif entry["censored"]:
                cells.append(f'<td>≥{fmt(column, entry["mean"])}</td>')
            elif all(v == 0 for v in entry["values"]):
                cells.append('<td class="quiet">not detected</td>')
            else:
                cells.append(f'<td>{fmt(column, entry["mean"])}</td>')
        osm = (f'<a href="https://www.openstreetmap.org/{esc(spring["osm"])}">mapped</a>'
               if spring["osm"] else "not mapped")
        on = " on" if spring["id"] == DEFAULT_SPRING else ""
        body.append(
            f'<tr class="row{on}" data-spring="{esc(spring["id"])}">'
            f'<th scope="row">{spring["n"]}<span>{esc(spring["id"])}</span></th>'
            f'<td>{spring["elev"]}</td><td>{fmt("t", spring["water"])}</td>'
            f'{"".join(cells)}<td class="left">{osm}</td></tr>'
        )
    return (
        '<table><thead><tr><th scope="col">Spring</th>'
        '<th scope="col">Elevation<span>m</span></th>'
        '<th scope="col">Water<span>°C</span></th>'
        f'{head}<th scope="col" class="left">OpenStreetMap<span>&nbsp;</span></th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
    )


def page_data(results: dict) -> dict:
    """What the page's script needs: the springs and a line about each."""
    springs = []
    for spring in results["springs"]:
        chem = {}
        for key in ("ph", "hardness", "sulfate", "copper", "turbidity", "chlorine"):
            entry = results["analytes"][key]["springs"].get(spring["id"])
            if entry is None:
                continue
            if entry["censored"]:
                text = "≥" + fmt(key, entry["mean"])
            elif all(v == 0 for v in entry["values"]):
                text = "not detected"
            else:
                text = fmt(key, entry["mean"])
            unit = UNITS[key] if text != "not detected" else ""
            chem[TITLES[key]] = f"{text} {unit}".strip()
        springs.append({
            **spring, "chem": chem,
            "best": results["superlatives"][spring["id"]],
            "thumb": thumb_of(spring["shots"][0]["file"]) if spring["shots"] else "",
        })
    return {"springs": springs, "initial": DEFAULT_SPRING}


def sentence_list(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def narrative(results: dict) -> dict[str, str]:
    """The sentences that state the findings, built from the numbers.

    Shared by the dashboard and the README so the two cannot disagree.
    """
    counts = results["counts"]
    springs = results["springs"]
    rep = results["replicates"]
    a = results["analytes"]
    status = results["status"]
    target = next(s for s in springs if s["id"] == DEFAULT_SPRING)
    others = [s for s in springs if s["id"] != DEFAULT_SPRING]

    def mean(key: str, sid: str) -> float:
        return a[key]["springs"][sid]["mean"]

    other_sulfate = [mean("sulfate", s["id"]) for s in others]
    other_water = [s["water"] for s in others]
    top_hard = sum(1 for s in a["hardness"]["springs"].values() if s["censored"])
    reading_order = ["ph", "sulfate", "copper", "turbidity", "chlorine",
                     "hardness", "nitrite", "ammonium", "iron"]
    ordered = sorted(status, key=lambda k: reading_order.index(k)
                     if k in reading_order else len(reading_order))
    usable_names = [TITLES[k].lower() if k != "ph" else "pH"
                    for k in ordered if status[k] == "usable"]
    bad_names = [TITLES[k].lower() for k in ordered if status[k] == "unusable"]
    expected = rep["sets"] / 3
    p_text = f"{rep['p']:.5f}" if rep["p"] >= 0.00001 else "below 0.00001"
    cross = results["cross"]
    ph_means = [s["mean"] for s in a["ph"]["springs"].values()]
    lo, hi = summarise_lab.PH_OPERATIONAL
    shares = sentence_list([
        ("under 1%" if g["share"] < 1 else f"{g['share']:.0f}%")
        + (" of the WHO value" if index == 0 else "") + f" for {g['title'].lower()}"
        for index, g in enumerate(
            sorted(results["guidelines"], key=lambda g: -g["share"]))
    ])

    return {
        "lead": (
            f"On 25 October 2026 six springs on the northern slope of the Ile-Alatau "
            f"were located from {counts['photos']} geotagged photographs and sampled. "
            f"A university teaching laboratory returned {counts['readings']} readings "
            f"across {words(counts['analytes'])} analytes. "
            f"{cap(words(counts['usable']))} of the {words(counts['analytes'])} can be "
            f"used, {words(counts['unusable'])} cannot, and one spring turned out "
            f"unlike the other five."
        ),
        "distinct_head": "One spring is unlike the other five",
        "distinct": (
            f"Spring {target['n']} ({DEFAULT_SPRING}) has the highest pH ({fmt('ph', mean('ph', DEFAULT_SPRING))}), "
            f"the most sulfate ({fmt('sulfate', mean('sulfate', DEFAULT_SPRING))} mg/L against "
            f"{fmt('sulfate', min(other_sulfate))} to {fmt('sulfate', max(other_sulfate))} "
            f"elsewhere), the softest water ({fmt('hardness', mean('hardness', DEFAULT_SPRING))} "
            f"mg/L where {words(top_hard)} others read at least 425) and the warmest water: "
            f"{fmt('t', target['water'])} °C on an afternoon when the air was "
            f"{fmt('t', target['air'])} °C and the other springs ran at "
            f"{fmt('t', min(other_water))} to {fmt('t', max(other_water))} °C."
        ),
        "sign": (
            f"A municipal sign at the outlet reads \u201c{target['sign']}, "
            f"{target['sign_elev']} m\u201d; the elevation model puts it at "
            f"{target['elev']} m."
            if target["sign"] and target["sign_elev"] else ""
        ),
        "hypothesis": (
            "Sulfate rising while hardness falls is not what dissolving gypsum does. "
            + ("A sulfide spring offers another source for it, since sulfate is what "
               "sulfide oxidises to, and together " if "sulfide" in target["sign"].lower()
               else "Together ")
            + "with the warmth and the pH that is the pattern of water that has "
            "travelled a deeper path. It remains a hypothesis one visit cannot test: "
            "sulfide, sodium, calcium and conductivity were not measured."
        ),
        "chlorine": (
            f"Chlorine is not charted: {a['chlorine']['below']} of its "
            f"{a['chlorine']['n']} readings were indistinguishable from distilled water."
        ),
        "guide_head": "Nothing measured came near a guideline value",
        "guide": (
            f"The highest spring reached {shares}; pH ran {fmt('ph', min(ph_means))} to "
            f"{fmt('ph', max(ph_means))}, inside the {lo:g} to {hi:g} operational range."
        ),
        "caution": (
            "No microbiological testing was done, and what makes spring water dangerous "
            "is usually microbiological."
        ),
        "methods_head": cap(
            f"{words(counts['usable'])} of {words(counts['analytes'])} analytes were "
            "measured by a method that fits spring water"
        ),
        "methods_lead": (
            f"{cap(sentence_list(usable_names))} came through as reported, chlorine "
            f"as a clean non-detect, and hardness with its top readings cut off by the "
            f"strip’s scale. {cap(sentence_list(bad_names))} did not: the tests "
            "the laboratory holds are built for water far stronger than a mountain spring, "
            "and nothing in the numbers themselves gave that away."
        ),
        "cross": (
            f"Sulfate at spring {target['n']} was also run on a second method. It read "
            f"{cross['reference']:g} mg/L against {cross['routine']:g}, a gap of "
            f"{cross['gap_pct']:.0f}%, which is the only measure of bias this batch contains."
            if cross else ""
        ),
        "rep_head": (
            f"The first reading was the highest in {rep['first_max']} of "
            f"{rep['sets']} triplicates"
        ),
        "rep_lead": (
            f"That is among the {rep['sets']} triplicates whose three readings were not "
            f"all identical. If the order of readings did not matter, the first would be "
            f"the highest in about a third of them, {expected:.0f}; the chance of "
            f"{rep['first_max']} or more is {p_text}. Turbidity shows one cause, particles "
            "settling in the cuvette between readings. A finding like this exists only "
            "because the laboratory ran its measurements in triplicate."
        ),
    }


README_START = "<!-- results:start -->"
README_END = "<!-- results:end -->"


def readme_block(results: dict) -> str:
    """The results section of the README, as Markdown."""
    n = narrative(results)

    def picture(stem: str, alt: str) -> str:
        return (
            "<picture>\n"
            f'  <source media="(prefers-color-scheme: dark)" srcset="reports/figures/{stem}-dark.svg">\n'
            f'  <img src="reports/figures/{stem}-light.svg" alt="{esc(alt)}" width="100%">\n'
            "</picture>"
        )

    columns = ["ph", "hardness", "sulfate", "copper", "turbidity", "chlorine"]
    head = ("| Spring | Elevation, m | Water, °C | pH | Hardness, mg/L CaCO3 | "
            "Sulfate, mg/L | Copper, mg/L | Turbidity, NTU | Chlorine, mg/L | OpenStreetMap |")
    rule = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"
    rows = []
    for spring in results["springs"]:
        cells = []
        for column in columns:
            entry = results["analytes"][column]["springs"][spring["id"]]
            if entry["censored"]:
                cells.append("≥" + fmt(column, entry["mean"]))
            elif all(v == 0 for v in entry["values"]):
                cells.append("not detected")
            else:
                cells.append(fmt(column, entry["mean"]))
        osm = (f"[{spring['osm']}](https://www.openstreetmap.org/{spring['osm']})"
               if spring["osm"] else "not mapped")
        rows.append(
            f"| {spring['id']} | {spring['elev']} | {fmt('t', spring['water'])} | "
            + " | ".join(cells) + f" | {osm} |"
        )
    unusable = sentence_list(
        [TITLES[k].lower() for k, v in sorted(results["status"].items()) if v == "unusable"])

    parts = [
        README_START,
        "<!-- Generated by src/make_dashboard.py from data/field/. Edit the script, not this block. -->",
        "",
        *photo_strip(results),
        f"**{n['distinct_head']}.** {' '.join(x for x in (n['distinct'], n['sign'], n['hypothesis']) if x)}",
        "",
        picture("chemistry", "Six charts comparing spring ALA-0004 with the other five"),
        "",
        f"**{n['methods_head']}.** {n['methods_lead']}",
        "",
        picture("methods", "Working range of each laboratory method against the readings"),
        "",
        f"**{n['rep_head']}.** {n['rep_lead']}",
        "",
        f"**{n['guide_head']}, and that is not a safety verdict.** {n['guide']} "
        f"{n['caution']}",
        "",
        head, rule, *rows,
        "",
        "Means of three readings, except hardness and water temperature, which were "
        f"read once. The readings for {unusable} are in the data file and are left out "
        "of this table on purpose.",
        README_END,
    ]
    return "\n".join(parts)


def photo_strip(results: dict) -> list[str]:
    """One photograph per spring across the README, where there are any."""
    springs = [s for s in results["springs"] if s["shots"]]
    if not springs:
        return []
    width = 100 // len(springs) - 1
    images = "\n".join(
        f'  <img src="{esc(thumb_of(s["shots"][0]["file"]))}" width="{width}%" '
        f'alt="{esc(s["id"] + ": " + s["shots"][0]["caption"])}">'
        for s in springs
    )
    return [
        f"<p>\n{images}\n</p>",
        "",
        "<sub>The six springs in the order they were visited, 25 October 2026.</sub>",
        "",
    ]


def thumb_of(file: str) -> str:
    """The small version of a spring's first photograph, if one was made."""
    root = Path(__file__).resolve().parent.parent
    thumb = file.rsplit("-", 1)[0] + "-thumb.jpg"
    return thumb if (root / thumb).exists() else file


def update_readme(path: Path, results: dict) -> bool:
    """Replace the generated block in the README. False if it has no markers."""
    text = path.read_text(encoding="utf-8")
    if README_START not in text or README_END not in text:
        return False
    start = text.index(README_START)
    end = text.index(README_END) + len(README_END)
    path.write_text(text[:start] + readme_block(results) + text[end:],
                    encoding="utf-8", newline="\n")
    return True


def render_page(results: dict) -> str:
    n = narrative(results)
    status = results["status"]
    date = results["springs"][0]["date"]

    panels = "".join(
        f'<figure class="panel">{inline_svg(panel_svg(p, results, DEFAULT_SPRING), PANEL_W, PANEL_H, p[1] + " at the six springs")}</figure>'
        for p in PANELS
    )
    wide, ww, wh = methods_svg(results, "wide", DEFAULT_SPRING)
    narrow, nw, nh = methods_svg(results, "narrow", DEFAULT_SPRING)

    fill = {
        "TITLE": "Six springs above Almaty",
        "LIGHT_VARS": css_vars(LIGHT),
        "DARK_VARS": css_vars(DARK),
        "CHART_CSS": chart_css({k: f"var(--{k})" for k in LIGHT}, "inherit"),
        "LEAFLET_CSS": LEAFLET_CSS,
        "LEAFLET_JS": LEAFLET_JS,
        "REPO": REPO_URL,
        "DATA": json.dumps(page_data(results), ensure_ascii=False).replace("</", "<\\/"),
        "LEAD": n["lead"],
        "PICKER": picker_html(results),
        "PANELS": panels,
        "DISTINCT_HEAD": n["distinct_head"],
        "DISTINCT": " ".join(x for x in (n["distinct"], n["sign"]) if x),
        "HYPOTHESIS": n["hypothesis"],
        "CHLORINE": n["chlorine"],
        "GUIDE_HEAD": n["guide_head"],
        "GUIDELINES": guideline_html(results),
        "CAUTION": n["caution"],
        "WITHDRAWN": sentence_list([TITLES[w].lower() for w in results["withdrawn"]]),
        "METHODS_HEAD": n["methods_head"],
        "METHODS_LEAD": n["methods_lead"],
        "METHODS_WIDE": inline_svg(wide, ww, wh, "Method ranges against spring readings", "wide"),
        "METHODS_NARROW": inline_svg(narrow, nw, nh, "Method ranges against spring readings", "narrow"),
        "CROSS": n["cross"],
        "REP_HEAD": n["rep_head"],
        "REP_LEAD": n["rep_lead"],
        "REPLICATES": replicate_html(results),
        "TABLE": table_html(results),
        "UNUSABLE": sentence_list(
            [TITLES[k].lower() for k, v in sorted(status.items()) if v == "unusable"]),
        "ANALYST": esc(sentence_list(results["analysts"])),
        # The photographs are the one thing here that is not openly licensed.
        "PHOTO_RIGHTS": (
            " The photographs are © Vladislav Karelin, all rights reserved."
            if any(s["shots"] for s in results["springs"]) else ""
        ),
        "DATE": date,
    }
    page = PAGE
    for key, value in fill.items():
        page = page.replace(f"@@{key}@@", value)
    if "@@" in page:
        start = page.index("@@")
        raise SystemExit(f"unfilled placeholder near: {page[start:start + 40]!r}")
    return page


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@TITLE@@</title>
<meta name="description" content="Results of a field and laboratory study of six natural springs above Almaty, 25 October 2026.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="@@LEAFLET_CSS@@">
<style>
:root{@@LIGHT_VARS@@--wash:rgba(42,120,214,.10);color-scheme:light}
@media (prefers-color-scheme:dark){:root{@@DARK_VARS@@--wash:rgba(57,135,229,.16);color-scheme:dark}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);
  font-family:"Golos Text",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration-color:var(--axis);text-underline-offset:3px}
a:hover{text-decoration-color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:4px}
.wrap{max-width:1128px;margin:0 auto;padding:0 28px}
.top{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;
  padding:22px 0;font-size:14px;color:var(--ink2)}
.top nav{display:flex;gap:22px;flex-wrap:wrap}
h1{font-size:clamp(44px,8.4vw,104px);line-height:.94;letter-spacing:-.045em;
  font-weight:800;margin:40px 0 0;max-width:11ch}
.lead{font-size:clamp(17px,1.6vw,20px);line-height:1.5;max-width:62ch;margin:28px 0 0;color:var(--ink2)}
h2{font-size:clamp(24px,2.7vw,34px);line-height:1.12;letter-spacing:-.025em;
  font-weight:700;margin:0;max-width:24ch}
section{padding:84px 0 0}
section>p,.text p{max-width:66ch;margin:16px 0 0;color:var(--ink2)}
.fine{font-size:14px;color:var(--muted);max-width:70ch}
strong,b{font-weight:650;color:var(--ink)}

/* The afternoon's six stops, set by elevation. They also pick the spring. */
.pickbar{display:flex;justify-content:space-between;align-items:baseline;gap:16px;
  flex-wrap:wrap;margin:64px 0 10px}
.pickbar p{margin:0;font-size:14px;color:var(--muted)}
.all{font:inherit;font-size:14px;font-weight:500;color:var(--ink);background:none;
  border:1px solid var(--axis);border-radius:999px;padding:6px 16px;cursor:pointer}
.all[aria-pressed=true]{background:var(--ink);color:var(--page);border-color:var(--ink)}
.stops{position:relative;display:grid;grid-template-columns:repeat(6,1fr);gap:0;
  padding-left:54px;border-bottom:1px solid var(--axis)}
.alts{position:absolute;left:0;right:0;top:0;height:168px;pointer-events:none}
.alt{position:absolute;left:0;right:0;border-top:1px solid var(--grid)}
.alt i{position:absolute;left:0;top:-9px;font-style:normal;font-size:11px;color:var(--muted);
  background:var(--page);padding-right:8px;font-variant-numeric:tabular-nums}
.stop{position:relative;font:inherit;color:inherit;background:none;border:0;cursor:pointer;
  padding:0 2px 16px;text-align:center;display:flex;flex-direction:column;align-items:center}
.stop-track{position:relative;display:block;width:100%;height:168px}
.stop-line{position:absolute;left:50%;bottom:0;width:1px;margin-left:-.5px;background:var(--axis)}
.stop-dot{position:absolute;left:50%;width:16px;height:16px;margin:0 0 -8px -8px;border-radius:50%;
  background:var(--dim);box-shadow:0 0 0 3px var(--page);transition:transform .15s}
.stop:hover .stop-dot{transform:scale(1.2)}
.stop-n{font-size:clamp(26px,3.4vw,40px);font-weight:800;letter-spacing:-.04em;line-height:1;
  margin-top:14px;color:var(--muted)}
.stop-elev{font-size:13px;font-weight:600;margin-top:6px;font-variant-numeric:tabular-nums}
.stop-meta{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.stop[aria-pressed=true] .stop-dot,.stops.all-on .stop-dot{background:var(--accent)}
.stop[aria-pressed=true] .stop-n{color:var(--ink)}
.stop[aria-pressed=true] .stop-line{background:var(--accent);width:2px;margin-left:-1px}
.stops.all-on .stop-n{color:var(--ink)}

.site{display:grid;grid-template-columns:minmax(0,4fr) minmax(0,3fr) minmax(0,5fr);gap:32px;padding-top:36px;align-items:stretch}
.shot{margin:0;min-width:0}
.shot:empty{display:none}
.shot img{display:block;width:100%;aspect-ratio:3/4;object-fit:cover;border-radius:14px;background:var(--grid)}
.shot figcaption{margin-top:10px;display:grid;gap:4px;justify-items:start}
.shot figcaption button{font:inherit;font-size:13.5px;text-align:left;color:var(--muted);background:none;
  border:0;padding:0;cursor:pointer;text-decoration:underline;text-decoration-color:var(--axis);text-underline-offset:3px}
.shot figcaption button[aria-pressed=true]{color:var(--ink);font-weight:600;text-decoration:none;cursor:default}
.shot figcaption span{font-size:13.5px;color:var(--ink2)}
.thumbs{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.thumbs button{position:relative;padding:0;border:0;background:none;cursor:pointer;border-radius:10px;overflow:hidden}
.thumbs img{border-radius:10px}
.thumbs b{position:absolute;left:8px;bottom:6px;color:#fff;font-size:15px;font-weight:800;text-shadow:0 1px 6px rgba(0,0,0,.7)}
.site h3{font-size:22px;letter-spacing:-.02em;margin:0;font-weight:700}
.site h3 span{font-weight:400;color:var(--muted);font-size:15px;letter-spacing:0;margin-left:8px}
.site .say{margin:10px 0 0;color:var(--ink2);max-width:46ch}
.facts{display:grid;grid-template-columns:auto 1fr;gap:6px 20px;margin:20px 0 0;font-size:14.5px}
.facts dt{color:var(--muted)}
.facts dd{margin:0;font-variant-numeric:tabular-nums}
#map{min-height:380px;border-radius:14px;overflow:hidden;background:var(--grid);z-index:0}
.leaflet-container{font:inherit;background:var(--grid)}
@media (prefers-color-scheme:dark){.leaflet-tile-pane{filter:brightness(.72) contrast(1.08) saturate(.6)}}
.mk{display:grid;place-items:center;width:28px;height:28px;border-radius:50%;
  background:var(--accent);color:#fff;font-weight:700;font-size:13px;
  box-shadow:0 0 0 3px var(--page),0 2px 8px rgba(0,0,0,.3)}
.mk.off{background:var(--dim)}

.panels{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:36px 28px;margin-top:36px}
.panel{margin:0}
.cv{display:block;width:100%;height:auto;overflow:visible}
.panel .cv{max-width:360px}
@@CHART_CSS@@
.cv .row:hover .hit{fill:var(--wash)}
svg.narrow{display:none;max-width:380px}
figure.methods{margin:36px 0 0}

.caution{margin:28px 0 0;padding:16px 20px;border-left:3px solid var(--warn);
  background:var(--surface);border-radius:0 10px 10px 0;max-width:70ch;color:var(--ink)}
.g-rows{margin-top:32px;display:grid;gap:22px}
.g-row{display:grid;grid-template-columns:minmax(0,300px) minmax(0,1fr) minmax(0,230px);gap:10px 28px;align-items:center}
.g-name b{display:block}
.g-name span,.g-fig{font-size:13.5px;color:var(--muted)}
.g-fig b{color:var(--ink)}
.g-track{position:relative;height:10px;border-radius:5px;background:var(--wash)}
.g-end{position:absolute;right:0;top:-6px;bottom:-6px;width:2px;background:var(--ink2);border-radius:1px}
.g-range .g-end{display:none}
.gdot{position:absolute;top:50%;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;
  background:var(--accent);box-shadow:0 0 0 2px var(--page)}
.gdot.off{background:var(--dim)}
.gdot.on{z-index:1}

.r-rows{margin-top:30px;display:grid;gap:14px;max-width:640px}
.r-row{display:grid;grid-template-columns:110px minmax(0,1fr) 64px;gap:16px;align-items:center;font-size:14.5px}
.r-track{position:relative;height:10px;border-radius:5px;background:var(--wash)}
.r-fill{position:absolute;left:0;top:0;bottom:0;border-radius:5px;background:var(--accent)}
.r-chance{position:absolute;left:33.33%;top:-6px;bottom:-6px;width:2px;background:var(--ink2);border-radius:1px}
.r-fig{font-variant-numeric:tabular-nums;color:var(--ink2)}
.r-key{display:flex;align-items:center;gap:10px;margin-top:18px;font-size:13.5px;color:var(--muted)}
.r-key i{display:block;width:2px;height:18px;background:var(--ink2);border-radius:1px}

.scroll{overflow-x:auto;margin-top:30px}
table{border-collapse:collapse;width:100%;min-width:760px;font-size:14.5px;font-variant-numeric:tabular-nums}
th,td{padding:11px 12px;text-align:right;border-bottom:1px solid var(--grid);white-space:nowrap}
thead th{font-weight:600;vertical-align:bottom;border-bottom-color:var(--axis)}
thead th span{display:block;font-weight:400;font-size:12px;color:var(--muted)}
tbody th{text-align:left;font-weight:700}
tbody th span{font-weight:400;color:var(--muted);margin-left:10px;font-size:13px}
th:first-child{text-align:left}
.left{text-align:left}
td.quiet{color:var(--muted)}
tr.row.on td,tr.row.on th{background:var(--wash)}

footer{margin-top:96px;padding:36px 0 64px;border-top:1px solid var(--axis);
  display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:28px 40px;
  font-size:14.5px;color:var(--ink2)}
footer b{display:block;color:var(--ink)}
footer p{margin:0}

#tip{position:fixed;z-index:1000;pointer-events:none;background:var(--ink);color:var(--page);
  padding:9px 12px;border-radius:9px;font-size:13px;line-height:1.35;max-width:260px;
  opacity:0;transition:opacity .1s;box-shadow:0 6px 24px rgba(0,0,0,.22)}
#tip.show{opacity:1}
#tip b{display:block;color:inherit;font-size:14.5px;font-variant-numeric:tabular-nums}
#tip span{display:block;opacity:.72}

@media (max-width:860px){
  .wrap{padding:0 16px}
  section{padding-top:64px}
  .site{grid-template-columns:1fr;gap:28px}
  .shot{max-width:420px}
  .g-row{grid-template-columns:1fr;gap:8px}
  .g-track{margin:6px 0}
  svg.wide{display:none}
  svg.narrow{display:block}
  .stops{padding-left:46px}
  .stop-time{display:none}
  .alt i{font-size:10px}
  .stop-track,.alts{height:120px}
  .stop-meta{font-size:10.5px}
  .stop-elev{font-size:11.5px}
  #map{min-height:300px;height:300px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <span>Almaty Springs, field campaign of 25 October 2026</span>
    <nav>
      <a href="@@REPO@@">Repository</a>
      <a href="@@REPO@@/tree/main/data/field">Data</a>
      <a href="reports/map.html">Regional map</a>
    </nav>
  </header>

  <h1>@@TITLE@@</h1>
  <p class="lead">@@LEAD@@</p>

  <div class="pickbar">
    <p>The six springs in the order they were visited, each at its elevation. Pick one to follow it down the page.</p>
    <button type="button" class="all" id="all" aria-pressed="false">Show all six alike</button>
  </div>
  @@PICKER@@

  <div class="site">
    <div id="site" aria-live="polite"></div>
    <figure id="shot" class="shot"></figure>
    <div id="map" role="img" aria-label="Map of the six springs"></div>
  </div>

  <section>
    <h2>@@DISTINCT_HEAD@@</h2>
    <p>@@DISTINCT@@</p>
    <p>@@HYPOTHESIS@@</p>
    <div class="panels">@@PANELS@@</div>
    <p class="fine">Bars and dots are the mean of three readings and the ticks are the readings
    themselves. @@CHLORINE@@</p>
  </section>

  <section>
    <h2>@@GUIDE_HEAD@@</h2>
    <p>Each track runs from zero to the WHO value for that measurement, marked at its right
    end, with one dot per spring.</p>
    <div class="g-rows">@@GUIDELINES@@</div>
    <p class="caution"><strong>This is not a safety assessment.</strong> @@CAUTION@@
    The comparison for @@WITHDRAWN@@ is withdrawn, because those measurements cannot support one.</p>
  </section>

  <section>
    <h2>@@METHODS_HEAD@@</h2>
    <p>@@METHODS_LEAD@@</p>
    <figure class="methods">@@METHODS_WIDE@@@@METHODS_NARROW@@</figure>
    <p class="fine">pH was read on a Metrohm 913 meter and turbidity on a VELP TB1 turbidimeter;
    neither is a range-limited colour test, so they are not in this comparison. @@CROSS@@</p>
  </section>

  <section>
    <h2>@@REP_HEAD@@</h2>
    <p>@@REP_LEAD@@</p>
    @@REPLICATES@@
  </section>

  <section>
    <h2>Every usable result, by spring</h2>
    <p>Means of three readings, except hardness and water temperature, which were read once.
    The readings for @@UNUSABLE@@ are in the data file and are left out here on purpose.</p>
    <div class="scroll">@@TABLE@@</div>
    <p class="fine">Source files:
      <a href="@@REPO@@/blob/main/data/field/springs_@@DATE@@.csv">springs</a>,
      <a href="@@REPO@@/blob/main/data/field/lab_results_@@DATE@@.csv">laboratory results</a>,
      <a href="@@REPO@@/blob/main/data/field/lab_raw_@@DATE@@.txt">the laboratory report as received</a>,
      <a href="@@REPO@@/blob/main/data/field/photos_@@DATE@@.csv">the photographs</a>.
      This page is built from them by <a href="@@REPO@@/blob/main/src/make_dashboard.py">one script</a>.</p>
  </section>

  <footer>
    <p><b>Vladislav Karelin</b>Project design, field survey, data and analysis.</p>
    <p><b>@@ANALYST@@</b>Laboratory analysis and hydrochemical interpretation, in the teaching
    laboratory of the Kazakh-German University, Almaty.</p>
    <p><b>Open data</b>Data under CC BY 4.0, code under MIT. Map tiles and the regional
    inventory are from OpenStreetMap contributors.@@PHOTO_RIGHTS@@</p>
  </footer>
</div>
<div id="tip" role="status"></div>

<script src="@@LEAFLET_JS@@" defer></script>
<script>
const DATA = @@DATA@@;
const byId = Object.fromEntries(DATA.springs.map(s => [s.id, s]));
let active = DATA.initial;
let markers = {};

const el = (tag, text, cls) => {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (cls) node.className = cls;
  return node;
};
const minus = v => String(v).replace('-', '−');

function list(items) {
  if (items.length < 2) return items.join('');
  return items.slice(0, -1).join(', ') + ' and ' + items[items.length - 1];
}

function renderSite() {
  const box = document.getElementById('site');
  box.replaceChildren();
  if (!active) {
    const s = DATA.springs;
    const elev = s.map(x => x.elev), water = s.map(x => x.water);
    box.append(el('h3', 'All six springs'));
    box.append(el('p', 'Between ' + Math.min(...elev) + ' and ' + Math.max(...elev) +
      ' metres, visited between ' + s[0].visited + ' and ' + s[s.length - 1].visited +
      '. Water ran from ' + minus(Math.min(...water)) + ' to ' + minus(Math.max(...water)) +
      ' °C. ' + ['None', 'One', 'Two', 'Three', 'Four', 'Five', 'All'][s.filter(x => !x.osm).length] +
      ' of the six ' + (s.filter(x => !x.osm).length === 1 ? 'is' : 'are') + ' not in OpenStreetMap.', 'say'));
    return;
  }
  const s = byId[active];
  const h = el('h3', 'Spring ' + s.n);
  h.append(el('span', s.name ? s.id + ', ' + s.name : s.id));
  box.append(h);
  const say = s.best.length ? 'Of the six, it has ' + list(s.best) + '.' : 'No measurement sets it apart from the other five.';
  box.append(el('p', say, 'say'));
  const dl = el('dl', null, 'facts');
  const fact = (k, v) => { dl.append(el('dt', k)); const dd = el('dd'); dd.append(v); dl.append(dd); };
  fact('Elevation', s.elev + ' m');
  fact('Water', minus(s.water) + ' °C, air ' + minus(s.air) + ' °C');
  fact('Visited', s.visited + ', ' + s.photos + ' photographs');
  fact('Position', s.lat.toFixed(5) + ', ' + s.lon.toFixed(5));
  if (s.osm) {
    const a = el('a', 'mapped, ' + s.osm_m + ' m from the photographed position');
    a.href = 'https://www.openstreetmap.org/' + s.osm;
    fact('OpenStreetMap', a);
  } else {
    fact('OpenStreetMap', 'not mapped');
  }
  if (s.sign) fact('Sign at the site', s.sign + (s.sign_elev ? ', ' + s.sign_elev + ' m' : ''));
  for (const [k, v] of Object.entries(s.chem)) fact(k, v);
  box.append(dl);
}

function renderShot(pick) {
  const box = document.getElementById('shot');
  box.replaceChildren();
  if (!active) {
    const grid = el('div', null, 'thumbs');
    for (const s of DATA.springs) {
      if (!s.thumb) continue;
      const b = el('button');
      b.type = 'button';
      b.setAttribute('aria-label', 'Spring ' + s.n + ', ' + s.id);
      const img = el('img');
      img.src = s.thumb; img.alt = ''; img.loading = 'lazy';
      b.append(img, el('b', String(s.n)));
      b.addEventListener('click', () => select(s.id));
      grid.append(b);
    }
    if (grid.children.length) box.append(grid);
    return;
  }
  const shots = byId[active].shots;
  if (!shots.length) return;
  const index = Math.min(pick || 0, shots.length - 1);
  const img = el('img');
  img.src = shots[index].file;
  img.alt = 'Spring ' + byId[active].n + ': ' + shots[index].caption;
  const cap = el('figcaption');
  shots.forEach((shot, i) => {
    if (shots.length === 1) { cap.append(el('span', shot.caption)); return; }
    const b = el('button', shot.caption);
    b.type = 'button';
    b.setAttribute('aria-pressed', String(i === index));
    b.addEventListener('click', () => renderShot(i));
    cap.append(b);
  });
  box.append(img, cap);
}

function select(id) {
  active = id;
  document.querySelectorAll('.row[data-spring]').forEach(node => {
    node.classList.toggle('on', !!id && node.dataset.spring === id);
    node.classList.toggle('off', !!id && node.dataset.spring !== id);
  });
  document.querySelectorAll('[data-pick]').forEach(b =>
    b.setAttribute('aria-pressed', String(b.dataset.pick === id)));
  document.getElementById('all').setAttribute('aria-pressed', String(!id));
  document.querySelector('.stops').classList.toggle('all-on', !id);
  for (const [sid, m] of Object.entries(markers)) {
    const node = m.getElement();
    if (node) node.firstChild.classList.toggle('off', !!id && sid !== id);
    m.setZIndexOffset(sid === id ? 1000 : 0);
  }
  renderSite();
  renderShot(0);
}

document.querySelectorAll('[data-pick]').forEach(b =>
  b.addEventListener('click', () => select(b.dataset.pick)));
document.getElementById('all').addEventListener('click', () => select(null));

/* One tooltip for every mark. Text only: values are never set as HTML. */
const tipBox = document.getElementById('tip');
function showTip(target, x, y) {
  const [head, value, note] = target.dataset.tip.split('|');
  tipBox.replaceChildren(el('span', head), el('b', value));
  if (note) tipBox.append(el('span', note));
  tipBox.classList.add('show');
  const w = tipBox.offsetWidth, h = tipBox.offsetHeight;
  tipBox.style.left = Math.max(8, Math.min(x + 14, innerWidth - w - 8)) + 'px';
  tipBox.style.top = (y + h + 22 > innerHeight ? y - h - 12 : y + 16) + 'px';
}
document.addEventListener('pointermove', e => {
  const target = e.target.closest && e.target.closest('[data-tip]');
  if (target) showTip(target, e.clientX, e.clientY); else tipBox.classList.remove('show');
});
document.addEventListener('pointerleave', () => tipBox.classList.remove('show'));
addEventListener('scroll', () => tipBox.classList.remove('show'), {passive: true});

function initMap() {
  const box = document.getElementById('map');
  if (!window.L) { box.style.display = 'none'; return; }
  const map = L.map(box, {scrollWheelZoom: false, attributionControl: true});
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);
  const bounds = [];
  for (const s of DATA.springs) {
    const icon = L.divIcon({className: '', iconSize: [28, 28], iconAnchor: [14, 14],
      html: '<span class="mk">' + Number(s.n) + '</span>'});
    const m = L.marker([s.lat, s.lon], {icon, keyboard: false}).addTo(map);
    m.on('click', () => select(s.id));
    markers[s.id] = m;
    bounds.push([s.lat, s.lon]);
  }
  const fit = () => { map.invalidateSize(); map.fitBounds(bounds, {paddingTopLeft: [40, 40], paddingBottomRight: [40, 52]}); };
  fit();
  addEventListener('resize', fit);
  if (window.ResizeObserver) new ResizeObserver(fit).observe(box);
  select(active);
}

select(active);
addEventListener('DOMContentLoaded', initMap);
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--springs", type=Path,
                        default=Path("data/field/springs_2026-10-25.csv"))
    parser.add_argument("--lab", type=Path,
                        default=Path("data/field/lab_results_2026-10-25.csv"))
    parser.add_argument("--photos", type=Path,
                        default=Path("data/field/photos_2026-10-25.csv"),
                        help="photograph manifest; the page goes without if absent")
    parser.add_argument("--out", type=Path, default=Path("index.html"))
    parser.add_argument("--figures", type=Path, default=Path("reports/figures"))
    parser.add_argument("--readme", type=Path, default=Path("README.md"),
                        help="README whose results block is regenerated")
    args = parser.parse_args()

    for path in (args.springs, args.lab):
        if not path.exists():
            print(f"No such file: {path}", file=sys.stderr)
            return 1

    results = build_results(args.springs, args.lab, args.photos)

    args.out.write_text(render_page(results), encoding="utf-8", newline="\n")
    print(f"Wrote {args.out}")

    args.figures.mkdir(parents=True, exist_ok=True)
    for name, theme in (("light", LIGHT), ("dark", DARK)):
        for stem, figure in (("chemistry", chemistry_figure), ("methods", methods_figure)):
            target = args.figures / f"{stem}-{name}.svg"
            target.write_text(figure(results, theme), encoding="utf-8", newline="\n")
            print(f"Wrote {target}")

    if args.readme.exists() and update_readme(args.readme, results):
        print(f"Updated the results block in {args.readme}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
