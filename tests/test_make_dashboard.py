"""Tests for src/make_dashboard.py.

The dashboard is where the numbers meet a reader, so the tests pin three
things: that what it states matches the data, that it never claims more than
the replicates support, and that the committed page and figures are the ones
the current data produces.

Run:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import make_dashboard  # noqa: E402

SPRINGS = ROOT / "data/field/springs_2026-10-25.csv"
LAB = ROOT / "data/field/lab_results_2026-10-25.csv"


def results() -> dict:
    return make_dashboard.build_results(SPRINGS, LAB)


class TestResults(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.r = results()

    def test_counts(self) -> None:
        counts = self.r["counts"]
        self.assertEqual(len(self.r["springs"]), 6)
        self.assertEqual(counts["readings"], 151)
        self.assertEqual(counts["analytes"], 9)
        self.assertEqual(counts["usable"] + counts["unusable"], 9)

    def test_status_matches_the_written_account(self) -> None:
        """Four usable, one non-detect, one censored, three unusable."""
        status = self.r["status"]
        by = lambda state: {k for k, v in status.items() if v == state}  # noqa: E731
        self.assertEqual(by("usable"), {"ph", "sulfate", "copper", "turbidity"})
        self.assertEqual(by("nondetect"), {"chlorine"})
        self.assertEqual(by("censored"), {"hardness"})
        self.assertEqual(by("unusable"), {"nitrite", "ammonium", "iron"})

    def test_unusable_analytes_get_no_guideline_comparison(self) -> None:
        compared = {g["analyte"] for g in self.r["guidelines"]}
        self.assertFalse(compared & {"nitrite", "ammonium", "iron"})
        self.assertEqual(self.r["withdrawn"], ["iron", "nitrite"])

    def test_second_method_is_not_averaged_into_sulfate(self) -> None:
        """The 65.7 cross-check is a different method, not a fourth replicate."""
        entry = self.r["analytes"]["sulfate"]["springs"]["ALA-0004"]
        self.assertEqual(entry["values"], [54.0, 54.0, 54.0])
        self.assertAlmostEqual(self.r["cross"]["reference"], 65.7)

    def test_every_method_row_has_a_verdict(self) -> None:
        rows = self.r["methods"]
        self.assertEqual(len(rows), 8)
        for row in rows:
            self.assertIn(row["state"], {"good", "warn", "bad"})
            self.assertTrue(row["verdict"] and row["reason"])
        bad = {row["analyte"] for row in rows if row["state"] == "bad"}
        self.assertEqual(bad, {"nitrite", "ammonium", "iron"})

    def test_replicate_count_is_the_one_the_report_prints(self) -> None:
        rep = self.r["replicates"]
        self.assertEqual((rep["first_max"], rep["sets"]), (23, 33))
        self.assertLess(rep["p"], 0.0001)


class TestSuperlatives(unittest.TestCase):
    """A spring is only 'the most' of something when its readings stand clear."""

    @staticmethod
    def analytes(turbidity: dict, ph: dict | None = None) -> dict:
        def block(values: dict) -> dict:
            return {"springs": {
                sid: {"values": v, "mean": sum(v) / len(v), "censored": False}
                for sid, v in values.items()
            }}
        flat = {"A": [7.0], "B": [7.0]}
        return {
            "ph": block(ph or flat),
            "sulfate": block({"A": [5.0], "B": [5.0]}),
            "hardness": block({"A": [100.0], "B": [100.0]}),
            "turbidity": block(turbidity),
        }

    @staticmethod
    def springs() -> list[dict]:
        return [{"id": "A", "water": 5.0, "elev": 1000},
                {"id": "B", "water": 5.0, "elev": 1000}]

    def test_overlapping_replicates_make_no_claim(self) -> None:
        # A has the lower mean, but one of its readings is above all of B's.
        out = make_dashboard.superlatives(
            self.springs(), self.analytes({"A": [0.02, 0.05, 0.10], "B": [0.06, 0.07, 0.07]}))
        self.assertEqual(out, {"A": [], "B": []})

    def test_clear_separation_is_claimed(self) -> None:
        out = make_dashboard.superlatives(
            self.springs(), self.analytes({"A": [0.02, 0.03, 0.03], "B": [0.50, 0.60, 0.70]}))
        self.assertIn("the clearest water", out["A"])
        self.assertIn("the most turbid water", out["B"])

    def test_ties_make_no_claim(self) -> None:
        out = make_dashboard.superlatives(
            self.springs(), self.analytes({"A": [0.1], "B": [0.1]}))
        self.assertEqual(out, {"A": [], "B": []})

    def test_real_data(self) -> None:
        best = results()["superlatives"]
        self.assertEqual(
            best["ALA-0004"],
            ["the highest pH", "the most sulfate", "the softest water",
             "the warmest water"],
        )
        # 0.057 against 0.067 NTU with overlapping replicates is not a lead.
        self.assertNotIn("the clearest water", best["ALA-0004"])
        # 1.5 against 2.0 degrees on single readings is not one either.
        self.assertNotIn("the coldest water", best["ALA-0005"])


class TestWording(unittest.TestCase):
    def test_cap_keeps_ph(self) -> None:
        self.assertEqual(make_dashboard.cap("pH, sulfate and copper"), "pH, sulfate and copper")
        self.assertEqual(make_dashboard.cap("nitrite and iron"), "Nitrite and iron")

    def test_fmt_uses_a_true_minus(self) -> None:
        self.assertEqual(make_dashboard.fmt("t", -1.0), "−1")
        self.assertEqual(make_dashboard.fmt("ph", 8.1533), "8.15")
        self.assertEqual(make_dashboard.fmt("hardness", 425.0), "425")

    def test_words(self) -> None:
        self.assertEqual(make_dashboard.words(6), "six")
        self.assertEqual(make_dashboard.words(151), "151")


class TestOutputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.r = results()
        cls.page = make_dashboard.render_page(cls.r)

    def test_page_has_no_unfilled_placeholders(self) -> None:
        self.assertNotIn("@@", self.page)

    def test_page_data_is_valid_json_with_all_six_springs(self) -> None:
        match = re.search(r"const DATA = (.*);\n", self.page)
        self.assertIsNotNone(match)
        data = json.loads(match.group(1).replace("<\\/", "</"))
        self.assertEqual([s["id"] for s in data["springs"]],
                         [f"ALA-{n:04d}" for n in range(1, 7)])

    def test_page_carries_the_safety_caveat(self) -> None:
        self.assertIn("This is not a safety assessment", self.page)

    def test_unusable_readings_are_not_tabulated(self) -> None:
        table = self.page[self.page.index("<table>"):self.page.index("</table>")]
        for word in ("Nitrite", "Ammonium", "Iron"):
            self.assertNotIn(word, table)

    def test_figures_are_well_formed_svg(self) -> None:
        for theme in (make_dashboard.LIGHT, make_dashboard.DARK):
            for figure in (make_dashboard.chemistry_figure, make_dashboard.methods_figure):
                text = figure(self.r, theme)
                ET.fromstring(text)
                self.assertNotIn("nan", text)
                self.assertNotIn("inf", text.replace("info", ""))

    def test_a_reading_off_the_axis_is_fatal(self) -> None:
        """A chart must not silently clip a value the axis cannot show."""
        panel = ("sulfate", "Sulfate", "mg/L", "bar", (0, 10), (0, 5, 10), 0)
        with self.assertRaises(SystemExit):
            make_dashboard.panel_svg(panel, self.r, None)

    def test_committed_page_and_figures_are_current(self) -> None:
        """index.html and the README figures must match what the data builds."""
        page = ROOT / "index.html"
        if not page.exists():
            self.skipTest("dashboard not built")
        self.assertEqual(
            page.read_text(encoding="utf-8"), self.page,
            "index.html is stale: run python src/make_dashboard.py",
        )
        for name, theme in (("light", make_dashboard.LIGHT), ("dark", make_dashboard.DARK)):
            for stem, figure in (("chemistry", make_dashboard.chemistry_figure),
                                 ("methods", make_dashboard.methods_figure)):
                path = ROOT / "reports/figures" / f"{stem}-{name}.svg"
                self.assertEqual(
                    path.read_text(encoding="utf-8"), figure(self.r, theme),
                    f"{path.name} is stale: run python src/make_dashboard.py",
                )
        self.assertIn(
            make_dashboard.readme_block(self.r),
            (ROOT / "README.md").read_text(encoding="utf-8"),
            "the README results block is stale: run python src/make_dashboard.py",
        )


if __name__ == "__main__":
    unittest.main()
