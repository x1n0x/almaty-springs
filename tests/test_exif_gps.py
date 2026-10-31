"""Tests for src/exif_gps.py.

Fixtures are JPEG files built here rather than committed binaries, so the test
states exactly which bytes produce which result. Both byte orders are covered:
phones write little-endian, but plenty of cameras write big-endian, and a
parser that only handles one silently returns nonsense on the other.

Run:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from exif_gps import ExifError, read_location  # noqa: E402

RATIONAL, ASCII, LONG, BYTE = 5, 2, 4, 1


def _build_ifd(order: str, items: list[tuple], ifd_offset: int) -> tuple[bytes, int]:
    """Pack one IFD plus its overflow data area.

    items: (tag, type_id, count, payload_bytes)
    Returns (bytes, total length including the data area).
    """
    count = len(items)
    ifd_size = 2 + 12 * count + 4
    data_base = ifd_offset + ifd_size

    out = struct.pack(order + "H", count)
    data = b""
    for tag, type_id, n, payload in items:
        if len(payload) <= 4:
            value = payload.ljust(4, b"\x00")
        else:
            value = struct.pack(order + "I", data_base + len(data))
            data += payload
            if len(data) % 2:
                data += b"\x00"
        out += struct.pack(order + "HHI", tag, type_id, n) + value
    out += struct.pack(order + "I", 0)  # no next IFD
    return out + data, ifd_size + len(data)


def _dms(order: str, degrees: float) -> bytes:
    """Encode decimal degrees as the three rationals EXIF expects."""
    degrees = abs(degrees)
    d = int(degrees)
    minutes_f = (degrees - d) * 60
    m = int(minutes_f)
    seconds = (minutes_f - m) * 60
    return struct.pack(
        order + "IIIIII", d, 1, m, 1, int(round(seconds * 10000)), 10000
    )


def make_jpeg(
    path: Path,
    lat: float | None = None,
    lon: float | None = None,
    lat_ref: str = "N",
    lon_ref: str = "E",
    altitude: float | None = None,
    altitude_ref: int = 0,
    taken: str | None = None,
    offset: str | None = None,
    model: str | None = None,
    big_endian: bool = False,
) -> Path:
    order = ">" if big_endian else "<"

    gps_items: list[tuple] = []
    if lat is not None and lon is not None:
        gps_items += [
            (1, ASCII, 2, lat_ref.encode() + b"\x00"),
            (2, RATIONAL, 3, _dms(order, lat)),
            (3, ASCII, 2, lon_ref.encode() + b"\x00"),
            (4, RATIONAL, 3, _dms(order, lon)),
        ]
    if altitude is not None:
        gps_items += [
            (5, BYTE, 1, bytes([altitude_ref])),
            (6, RATIONAL, 1, struct.pack(order + "II", int(abs(altitude) * 10), 10)),
        ]

    exif_items: list[tuple] = []
    if taken:
        exif_items.append((0x9003, ASCII, len(taken) + 1, taken.encode() + b"\x00"))
    if offset:
        exif_items.append((0x9011, ASCII, len(offset) + 1, offset.encode() + b"\x00"))

    ifd0_items: list[tuple] = []
    if model:
        ifd0_items.append((0x0110, ASCII, len(model) + 1, model.encode() + b"\x00"))
    ifd0_items.append((0x8769, LONG, 1, struct.pack(order + "I", 0)))  # Exif pointer
    ifd0_items.append((0x8825, LONG, 1, struct.pack(order + "I", 0)))  # GPS pointer

    # Sizes are independent of the pointer values, so lay out once, then
    # rewrite IFD0 with the offsets now known.
    _, len0 = _build_ifd(order, ifd0_items, 8)
    exif_offset = 8 + len0
    exif_bytes, len_e = _build_ifd(order, exif_items, exif_offset)
    gps_offset = exif_offset + len_e
    gps_bytes, _ = _build_ifd(order, gps_items, gps_offset)

    ifd0_items[-2] = (0x8769, LONG, 1, struct.pack(order + "I", exif_offset))
    ifd0_items[-1] = (0x8825, LONG, 1, struct.pack(order + "I", gps_offset))
    ifd0_bytes, _ = _build_ifd(order, ifd0_items, 8)

    tiff = (
        (b"MM" if big_endian else b"II")
        + struct.pack(order + "H", 42)
        + struct.pack(order + "I", 8)
        + ifd0_bytes
        + exif_bytes
        + gps_bytes
    )

    app1 = b"Exif\x00\x00" + tiff
    jpeg = (
        b"\xff\xd8"
        + b"\xff\xe1"
        + struct.pack(">H", len(app1) + 2)
        + app1
        + b"\xff\xd9"
    )
    path.write_bytes(jpeg)
    return path


def _tiff_from_jpeg(jpeg: bytes) -> bytes:
    """Pull the raw TIFF block out of a JPEG built by make_jpeg."""
    index = jpeg.find(b"Exif\x00\x00")
    return jpeg[index + 6 : -2]  # drop the trailing EOI marker


def make_heic(path: Path, decoy: bool = True, **kwargs) -> Path:
    """A minimal HEIC-shaped file carrying a real EXIF block.

    Not a decodable image: it exercises the container detection and the
    marker search, which is all this parser touches. When `decoy` is set the
    literal "Exif\\0\\0" also appears earlier without a TIFF header after it,
    exactly as it does in the metadata boxes of a real iPhone photograph.
    """
    jpeg = make_jpeg(path.with_suffix(".tmp"), **kwargs).read_bytes()
    tiff = _tiff_from_jpeg(jpeg)
    path.with_suffix(".tmp").unlink()

    header = struct.pack(">I", 0x18) + b"ftypheic" + b"\x00" * 12
    trap = b"Exif\x00\x00\x00\x01\xa0iref" if decoy else b""
    path.write_bytes(header + trap + b"\x00" * 32 + b"Exif\x00\x00" + tiff)
    return path


def make_png(path: Path, **kwargs) -> Path:
    """A PNG whose eXIf chunk holds the EXIF block."""
    jpeg = make_jpeg(path.with_suffix(".tmp"), **kwargs).read_bytes()
    tiff = _tiff_from_jpeg(jpeg)
    path.with_suffix(".tmp").unlink()

    def chunk(kind: bytes, payload: bytes) -> bytes:
        import zlib

        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"eXIf", tiff)
        + chunk(b"IEND", b"")
    )
    return path


class TestHeicAndPng(unittest.TestCase):
    """Formats the field photographs actually arrive in."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_heic_position(self) -> None:
        path = make_heic(self.dir / "a.heic", lat=43.18696, lon=77.00465)
        got = read_location(path)
        self.assertAlmostEqual(got.lat, 43.18696, places=4)
        self.assertAlmostEqual(got.lon, 77.00465, places=4)

    def test_heic_decoy_marker_is_skipped(self) -> None:
        """The first "Exif\\0\\0" in a real HEIC is not the EXIF block.

        Taking it without checking for a TIFF header after it is the bug this
        guards: it does not raise, it returns wrong coordinates.
        """
        with_decoy = make_heic(self.dir / "b.heic", decoy=True, lat=43.25, lon=76.75)
        without = make_heic(self.dir / "c.heic", decoy=False, lat=43.25, lon=76.75)
        self.assertAlmostEqual(
            read_location(with_decoy).lat, read_location(without).lat, places=6
        )
        self.assertAlmostEqual(read_location(with_decoy).lat, 43.25, places=5)

    def test_png_exif_chunk(self) -> None:
        path = make_png(self.dir / "d.png", lat=43.25, lon=76.75)
        got = read_location(path)
        self.assertAlmostEqual(got.lat, 43.25, places=5)

    def test_png_screenshot_has_time_but_no_position(self) -> None:
        """A map screenshot: EXIF present, GPS absent. Must not raise."""
        path = make_png(self.dir / "e.png", taken="2026:10:25 14:24:19")
        got = read_location(path)
        self.assertFalse(got.has_position)
        self.assertEqual(got.taken_at.hour, 14)

    def test_png_without_exif_chunk_raises(self) -> None:
        path = self.dir / "f.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 0) + b"IEND" + b"\x00" * 4)
        with self.assertRaises(ExifError):
            read_location(path)


class TestExifGps(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_reads_position(self) -> None:
        path = make_jpeg(self.dir / "a.jpg", lat=43.25, lon=76.75)
        got = read_location(path)
        self.assertTrue(got.has_position)
        self.assertAlmostEqual(got.lat, 43.25, places=5)
        self.assertAlmostEqual(got.lon, 76.75, places=5)

    def test_southern_and_western_refs_are_negative(self) -> None:
        path = make_jpeg(
            self.dir / "b.jpg", lat=43.25, lon=76.75, lat_ref="S", lon_ref="W"
        )
        got = read_location(path)
        self.assertAlmostEqual(got.lat, -43.25, places=5)
        self.assertAlmostEqual(got.lon, -76.75, places=5)

    def test_big_endian(self) -> None:
        path = make_jpeg(self.dir / "c.jpg", lat=43.25, lon=76.75, big_endian=True)
        got = read_location(path)
        self.assertAlmostEqual(got.lat, 43.25, places=5)
        self.assertAlmostEqual(got.lon, 76.75, places=5)

    def test_altitude_above_and_below_sea_level(self) -> None:
        above = make_jpeg(self.dir / "d.jpg", lat=43.25, lon=76.75, altitude=1850.4)
        self.assertAlmostEqual(read_location(above).altitude_m, 1850.4, places=1)

        below = make_jpeg(
            self.dir / "e.jpg", lat=43.25, lon=76.75, altitude=12.0, altitude_ref=1
        )
        self.assertAlmostEqual(read_location(below).altitude_m, -12.0, places=1)

    def test_timestamp_with_offset(self) -> None:
        path = make_jpeg(
            self.dir / "f.jpg",
            lat=43.25,
            lon=76.75,
            taken="2026:04:12 09:30:00",
            offset="+05:00",
        )
        got = read_location(path)
        self.assertIsNotNone(got.taken_at)
        self.assertEqual(got.taken_at.year, 2026)
        self.assertEqual(got.taken_at.hour, 9)
        self.assertEqual(got.taken_at.utcoffset(), timedelta(hours=5))

    def test_timestamp_without_offset_is_naive(self) -> None:
        path = make_jpeg(
            self.dir / "g.jpg", lat=43.25, lon=76.75, taken="2026:04:12 09:30:00"
        )
        got = read_location(path)
        self.assertIsNone(got.taken_at.tzinfo)

    def test_camera_model(self) -> None:
        path = make_jpeg(self.dir / "h.jpg", lat=43.25, lon=76.75, model="iPhone 13")
        self.assertEqual(read_location(path).camera, "iPhone 13")

    def test_photo_without_gps_is_not_an_error(self) -> None:
        path = make_jpeg(self.dir / "i.jpg", taken="2026:04:12 09:30:00")
        got = read_location(path)
        self.assertFalse(got.has_position)
        self.assertIsNone(got.lat)
        self.assertIsNotNone(got.taken_at)

    def test_file_without_exif_raises(self) -> None:
        path = self.dir / "j.jpg"
        path.write_bytes(b"\xff\xd8\xff\xd9")
        with self.assertRaises(ExifError):
            read_location(path)

    def test_not_an_image_raises(self) -> None:
        path = self.dir / "k.txt"
        path.write_bytes(b"spring notes, not a photo")
        with self.assertRaises(ExifError):
            read_location(path)


if __name__ == "__main__":
    unittest.main()
