"""Tests for src/ingest_lab.py and the checks in src/summarise_lab.py.

The transcription step is where a laboratory report becomes data, and a
mistake there is invisible afterwards: a wrong number looks exactly like a
right one. These tests pin the awkward cases the real reports contained —
two different separators, two different decimal marks, a missing separator,
negative results — and the rules that decide when a value is not a
measurement.

Run:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ingest_lab  # noqa: E402
import summarise_lab  # noqa: E402


class TestExtractNumbers(unittest.TestCase):
    """The report changed its punctuation between batches; both must parse."""

    def test_semicolons_with_comma_decimals(self) -> None:
        # First batch: "Проба 4: 0,0 ; 0,0 ; 0,0"
        self.assertEqual(ingest_lab.extract_numbers("0,0 ; 0,0 ; 0,0"), [0.0, 0.0, 0.0])

    def test_semicolons_with_dot_decimals(self) -> None:
        self.assertEqual(
            ingest_lab.extract_numbers("7.27 ; 7.26 ; 7.23"), [7.27, 7.26, 7.23]
        )

    def test_comma_separators_with_dot_decimals(self) -> None:
        # Second batch: "Проба 1: 0.06 , 0.06, 0.06"
        self.assertEqual(
            ingest_lab.extract_numbers("0.06 , 0.06, 0.06"), [0.06, 0.06, 0.06]
        )

    def test_missing_separator(self) -> None:
        # The report really does contain "1.31, 1.07 0.56".
        self.assertEqual(
            ingest_lab.extract_numbers("1.31, 1.07 0.56"), [1.31, 1.07, 0.56]
        )

    def test_negative_values(self) -> None:
        self.assertEqual(
            ingest_lab.extract_numbers("-0.786; -0.735; -0.714"),
            [-0.786, -0.735, -0.714],
        )

    def test_single_value(self) -> None:
        self.assertEqual(ingest_lab.extract_numbers("25"), [25.0])

    def test_comma_decimal_is_not_a_separator(self) -> None:
        """"0,1" is one value, not two.

        The distinction that makes this work is that a comma used as a
        separator in these reports is always followed by a space.
        """
        self.assertEqual(ingest_lab.extract_numbers("0,1 ; 0.0 ; 0.0"), [0.1, 0.0, 0.0])


class TestParseBlock(unittest.TestCase):
    REPORT = """
на NO2: (mg/L)
Проба 1: 5 ; 3 ; 3
Проба 2: 5 ; 3 ; 3
Проба 3: 4 ; 3 ; 2
Проба 4: 3 ; 3 ; 3
Проба 5: 5 ; 4 ; 4
Проба 6: 7 ; 6 ; 6

На жестокость:
Проба 1: 25
Проба 2: 7
"""

    def test_finds_section_by_russian_heading(self) -> None:
        block = ingest_lab.parse_block(self.REPORT, r"NO2")
        self.assertEqual(sorted(block), [1, 2, 3, 4, 5, 6])
        self.assertEqual(block[6], [7.0, 6.0, 6.0])

    def test_section_stops_before_the_next_one(self) -> None:
        """A section must not swallow the samples of the one after it."""
        block = ingest_lab.parse_block(self.REPORT, r"NO2")
        self.assertEqual(len(block), 6)

    def test_hardness_heading_is_matched_despite_the_misspelling(self) -> None:
        # The report writes "жестокость" for "жёсткость"; keying on the
        # English name silently produced zero rows once already.
        block = ingest_lab.parse_block(self.REPORT, r"жест[оё]к")
        self.assertEqual(block[1], [25.0])

    def test_missing_section_is_fatal(self) -> None:
        with self.assertRaises(SystemExit):
            ingest_lab.parse_block(self.REPORT, r"Phosphate")

    def test_wrong_replicate_count_is_fatal(self) -> None:
        """Two values means something was mis-transcribed; fail loudly."""
        with self.assertRaises(SystemExit):
            ingest_lab.parse_block("на NO2:\nПроба 1: 5 ; 3\n", r"NO2")


class TestRowsFor(unittest.TestCase):
    def rows(self, analyte, unit, block, method=""):
        return ingest_lab.rows_for(analyte, unit, "", block, method)

    def test_replicates_are_numbered_and_kept_separate(self) -> None:
        rows = self.rows("nitrite", "mg/L", {1: [5.0, 3.0, 3.0]})
        self.assertEqual([r["replicate"] for r in rows], [1, 2, 3])
        self.assertEqual([r["value"] for r in rows], ["5", "3", "3"])

    def test_single_measurement_has_no_replicate_index(self) -> None:
        rows = self.rows("hardness", "mg/L CaCO3", {1: [7.0]})
        self.assertEqual(rows[0]["replicate"], "")

    def test_hardness_is_converted_from_gpg(self) -> None:
        rows = self.rows("hardness", "mg/L CaCO3", {1: [7.0]})
        self.assertEqual(rows[0]["value"], "120")
        self.assertIn("7 gpg", rows[0]["notes"])

    def test_top_of_hardness_scale_is_marked_censored(self) -> None:
        rows = self.rows("hardness", "mg/L CaCO3", {1: [25.0]})
        self.assertEqual(rows[0]["value"], "425")
        self.assertIn("TOP OF SCALE", rows[0]["notes"])

    def test_hardness_off_the_chart_is_fatal(self) -> None:
        """A value that is not a chart level means the column was misread."""
        with self.assertRaises(SystemExit):
            self.rows("hardness", "mg/L CaCO3", {1: [9.0]})

    def test_zero_is_flagged_as_a_non_detect(self) -> None:
        rows = self.rows("chlorine", "mg/L", {1: [0.0, 0.0, 0.1]})
        self.assertEqual([r["below_lod"] for r in rows], ["true", "true", ""])

    def test_ph_zero_is_not_treated_as_a_non_detect(self) -> None:
        rows = self.rows("ph", "pH", {1: [0.0]})
        self.assertEqual(rows[0]["below_lod"], "")

    def test_below_the_method_floor_is_flagged(self) -> None:
        rows = self.rows(
            "ammonium", "mg/L NH4-N", {1: [2.99, 0.36]}, "hach_lck303_cuvette"
        )
        self.assertEqual(rows[0]["below_lod"], "")       # 2.99 is in range
        self.assertEqual(rows[1]["below_lod"], "true")   # 0.36 is not
        self.assertIn("working range", rows[1]["notes"])

    def test_negative_results_say_so_explicitly(self) -> None:
        rows = self.rows(
            "ammonium", "mg/L NH4-N", {1: [-0.786]}, "hach_lck303_cuvette"
        )
        self.assertEqual(rows[0]["below_lod"], "true")
        self.assertIn("NEGATIVE", rows[0]["notes"])

    def test_sample_number_maps_to_spring_id(self) -> None:
        rows = self.rows("nitrite", "mg/L", {4: [3.0, 3.0, 3.0]})
        self.assertEqual(rows[0]["spring_id"], "ALA-0004")
        self.assertEqual(rows[0]["sample_id"], "P4")


class TestBinomialTail(unittest.TestCase):
    """The replicate-order check reports a p-value; it should be right."""

    def test_certain_event(self) -> None:
        self.assertAlmostEqual(summarise_lab.binomial_tail(0, 5, 1 / 3), 1.0)

    def test_all_successes(self) -> None:
        # P(X = 5) for n=5, p=1/3 is (1/3)^5.
        self.assertAlmostEqual(
            summarise_lab.binomial_tail(5, 5, 1 / 3), (1 / 3) ** 5
        )

    def test_known_value(self) -> None:
        # P(X >= 1) = 1 - (2/3)^3
        self.assertAlmostEqual(
            summarise_lab.binomial_tail(1, 3, 1 / 3), 1 - (2 / 3) ** 3
        )

    def test_monotonic_in_k(self) -> None:
        tails = [summarise_lab.binomial_tail(k, 17, 1 / 3) for k in range(18)]
        self.assertEqual(tails, sorted(tails, reverse=True))


class TestRealReportParses(unittest.TestCase):
    """The committed report must still produce the committed table."""

    def test_every_section_yields_six_samples(self) -> None:
        raw = Path(__file__).resolve().parent.parent / "data/field/lab_raw_2026-10-25.txt"
        if not raw.exists():
            self.skipTest("raw report not present")
        text = raw.read_text(encoding="utf-8")
        for header, analyte, _unit, _method, _note in ingest_lab.SECTIONS:
            block = ingest_lab.parse_block(text, header)
            self.assertEqual(
                sorted(block), [1, 2, 3, 4, 5, 6], f"{analyte} did not yield 1-6"
            )


if __name__ == "__main__":
    unittest.main()
