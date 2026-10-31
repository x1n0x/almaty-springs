"""Minimal EXIF reader for GPS coordinates and capture time.

Pure standard library, deliberately. Field photographs are the one input every
collaborator has, and requiring a Pillow install before anyone can turn a
folder of photos into coordinates is a barrier this project does not need.

Only the tags the project actually uses are decoded: GPS position, GPS
altitude, capture timestamp, and camera make/model (which identifies the
device, and therefore the likely accuracy of its GPS fix).

Reference: EXIF 2.32 / TIFF 6.0. Offsets inside the EXIF block are relative to
the start of the TIFF header, not to the start of the file -- the most common
mistake when parsing this format by hand.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

# TIFF field types -> (struct code, byte size)
TYPES: dict[int, tuple[str, int]] = {
    1: ("B", 1),   # BYTE
    2: ("s", 1),   # ASCII
    3: ("H", 2),   # SHORT
    4: ("I", 4),   # LONG
    5: ("II", 8),  # RATIONAL (numerator, denominator)
    6: ("b", 1),   # SBYTE
    7: ("s", 1),   # UNDEFINED
    8: ("h", 2),   # SSHORT
    9: ("i", 4),   # SLONG
    10: ("ii", 8), # SRATIONAL
    11: ("f", 4),  # FLOAT
    12: ("d", 8),  # DOUBLE
}

TAG_EXIF_IFD = 0x8769
TAG_GPS_IFD = 0x8825
TAG_MAKE = 0x010F
TAG_MODEL = 0x0110

TAG_DATETIME_ORIGINAL = 0x9003
TAG_OFFSET_TIME_ORIGINAL = 0x9011

GPS_LAT_REF, GPS_LAT = 1, 2
GPS_LON_REF, GPS_LON = 3, 4
GPS_ALT_REF, GPS_ALT = 5, 6
GPS_TIMESTAMP, GPS_DATESTAMP = 7, 29
GPS_DOP = 11  # dilution of precision: a rough fix-quality indicator


class ExifError(Exception):
    pass


@dataclass
class PhotoLocation:
    path: Path
    lat: float | None = None
    lon: float | None = None
    altitude_m: float | None = None
    taken_at: datetime | None = None
    gps_dop: float | None = None
    camera: str | None = None

    @property
    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None


TIFF_HEADERS = (b"II*\x00", b"MM\x00*")


def _find_heif_exif(data: bytes) -> int:
    """Offset of the TIFF header inside a HEIC/HEIF file.

    Properly, the Exif item is located through the meta/iinf/iloc boxes. In
    practice the payload is always preceded by the literal "Exif\\0\\0", so
    this scans for that marker and keeps the first hit followed by a valid
    TIFF header.

    The validation is not optional: the string also appears earlier in the
    file as an item type inside the metadata boxes, and on a real iPhone
    photograph that decoy comes first. Taking the first match without checking
    yields garbage coordinates.
    """
    pos = 0
    while True:
        index = data.find(b"Exif\x00\x00", pos)
        if index < 0:
            raise ExifError("no EXIF block found in HEIF container")
        tiff = index + 6
        if data[tiff : tiff + 4] in TIFF_HEADERS:
            return tiff
        pos = index + 1


def _find_png_exif(data: bytes) -> int:
    """Offset of the TIFF header inside a PNG `eXIf` chunk."""
    offset = 8  # past the PNG signature
    while offset + 8 <= len(data):
        (length,) = struct.unpack_from(">I", data, offset)
        chunk = data[offset + 4 : offset + 8]
        if chunk == b"eXIf":
            start = offset + 8
            if data[start : start + 4] not in TIFF_HEADERS:
                raise ExifError("PNG eXIf chunk does not start with a TIFF header")
            return start
        if chunk == b"IEND":
            break
        offset += 12 + length  # length + type + data + CRC
    raise ExifError("no eXIf chunk in PNG")


def _find_exif_block(data: bytes) -> tuple[bytes, int]:
    """Return (buffer, offset of the TIFF header within it).

    Handles JPEG (APP1 segment), HEIC/HEIF, PNG (eXIf chunk) and bare TIFF.
    Returns the whole buffer so that internal offsets, which are relative to
    the TIFF header, stay valid.
    """
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return data, _find_png_exif(data)

    # ISO base media file format: HEIC, HEIF, AVIF. Size (4 bytes) then 'ftyp'.
    if len(data) > 12 and data[4:8] == b"ftyp":
        return data, _find_heif_exif(data)

    if data[:2] == b"\xff\xd8":  # JPEG SOI
        pos = 2
        while pos + 4 <= len(data):
            if data[pos] != 0xFF:
                raise ExifError("malformed JPEG: expected a segment marker")
            marker = data[pos + 1]
            # Standalone markers carry no length.
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                pos += 2
                continue
            if marker == 0xDA:  # start of scan: image data follows, no more metadata
                break
            (length,) = struct.unpack_from(">H", data, pos + 2)
            segment = data[pos + 4 : pos + 2 + length]
            if marker == 0xE1 and segment[:6] == b"Exif\x00\x00":
                return data, pos + 4 + 6
            pos += 2 + length
        raise ExifError("no EXIF block found")

    if data[:2] in (b"II", b"MM"):  # bare TIFF
        return data, 0

    raise ExifError("not a JPEG or TIFF file")


def _read_ifd(buf: bytes, tiff: int, offset: int, order: str) -> dict[int, object]:
    """Decode one IFD into {tag: value}."""
    pos = tiff + offset
    if pos + 2 > len(buf):
        raise ExifError("IFD offset past end of file")
    (count,) = struct.unpack_from(order + "H", buf, pos)
    pos += 2

    entries: dict[int, object] = {}
    for _ in range(count):
        if pos + 12 > len(buf):
            break
        tag, type_id, n = struct.unpack_from(order + "HHI", buf, pos)
        value_pos = pos + 8
        pos += 12

        if type_id not in TYPES:
            continue
        code, size = TYPES[type_id]
        # `size` is the whole field's width, 8 bytes for a RATIONAL's two
        # longs included -- it must not be doubled again for those types.
        total = size * n

        # Values of four bytes or fewer are stored inline, not at an offset.
        if total > 4:
            (data_offset,) = struct.unpack_from(order + "I", buf, value_pos)
            value_pos = tiff + data_offset
        if value_pos + total > len(buf):
            continue

        if type_id in (2, 7):  # ASCII / UNDEFINED
            raw = buf[value_pos : value_pos + n]
            entries[tag] = raw.split(b"\x00", 1)[0].decode("ascii", "replace")
        elif type_id in (5, 10):  # RATIONAL / SRATIONAL
            parts = struct.unpack_from(order + code * n, buf, value_pos)
            entries[tag] = [
                (parts[i], parts[i + 1]) for i in range(0, len(parts), 2)
            ]
        else:
            values = struct.unpack_from(order + code * n, buf, value_pos)
            entries[tag] = values[0] if n == 1 else list(values)

    return entries


def _ratio(pair: tuple[int, int]) -> float:
    numerator, denominator = pair
    return float(numerator) / denominator if denominator else 0.0


def _dms_to_degrees(values: list[tuple[int, int]], ref: str | None) -> float | None:
    """Convert degrees/minutes/seconds rationals to signed decimal degrees."""
    if not values or len(values) < 3:
        return None
    degrees = _ratio(values[0]) + _ratio(values[1]) / 60 + _ratio(values[2]) / 3600
    if ref and ref.upper() in ("S", "W"):
        degrees = -degrees
    return round(degrees, 7)


def _capture_time(exif: dict, gps: dict) -> datetime | None:
    """Prefer the camera's local timestamp; fall back to GPS UTC.

    The camera clock can be wrong or unset. GPS time comes from satellites and
    is always UTC, so it is the more trustworthy of the two when both exist --
    but it is recorded less often, which is why the camera value is tried
    first and only its missing offset is filled from GPS.
    """
    raw = exif.get(TAG_DATETIME_ORIGINAL)
    if isinstance(raw, str) and raw.strip():
        try:
            stamp = datetime.strptime(raw.strip(), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            stamp = None
        if stamp is not None:
            offset = exif.get(TAG_OFFSET_TIME_ORIGINAL)
            if isinstance(offset, str) and len(offset) >= 6 and offset[0] in "+-":
                try:
                    sign = 1 if offset[0] == "+" else -1
                    hours, minutes = int(offset[1:3]), int(offset[4:6])
                    delta = timedelta(hours=hours, minutes=minutes)
                    return stamp.replace(tzinfo=timezone(sign * delta))
                except ValueError:
                    pass
            return stamp  # naive: the caller decides which zone it belongs to

    datestamp = gps.get(GPS_DATESTAMP)
    timestamp = gps.get(GPS_TIMESTAMP)
    if isinstance(datestamp, str) and timestamp:
        try:
            year, month, day = (int(p) for p in datestamp.split(":"))
            hour = int(_ratio(timestamp[0]))
            minute = int(_ratio(timestamp[1]))
            second = int(_ratio(timestamp[2]))
            return datetime.combine(
                date(year, month, day), time(hour, minute, second), tzinfo=timezone.utc
            )
        except (ValueError, IndexError):
            return None
    return None


def read_location(path: Path) -> PhotoLocation:
    """Extract position and capture time from one photograph.

    Raises ExifError when the file has no EXIF block at all. A file that has
    EXIF but no GPS returns a PhotoLocation with has_position False, which is
    a normal outcome rather than an error: location services may simply have
    been off.
    """
    data = path.read_bytes()
    buf, tiff = _find_exif_block(data)

    if buf[tiff : tiff + 2] == b"II":
        order = "<"
    elif buf[tiff : tiff + 2] == b"MM":
        order = ">"
    else:
        raise ExifError("bad TIFF byte-order mark")

    (magic,) = struct.unpack_from(order + "H", buf, tiff + 2)
    if magic != 42:
        raise ExifError(f"bad TIFF magic number: {magic}")
    (ifd0_offset,) = struct.unpack_from(order + "I", buf, tiff + 4)

    ifd0 = _read_ifd(buf, tiff, ifd0_offset, order)
    exif = {}
    gps = {}
    if isinstance(ifd0.get(TAG_EXIF_IFD), int):
        exif = _read_ifd(buf, tiff, ifd0[TAG_EXIF_IFD], order)
    if isinstance(ifd0.get(TAG_GPS_IFD), int):
        gps = _read_ifd(buf, tiff, ifd0[TAG_GPS_IFD], order)

    result = PhotoLocation(path=path)

    lat = gps.get(GPS_LAT)
    lon = gps.get(GPS_LON)
    if lat and lon:
        result.lat = _dms_to_degrees(lat, gps.get(GPS_LAT_REF))
        result.lon = _dms_to_degrees(lon, gps.get(GPS_LON_REF))

    altitude = gps.get(GPS_ALT)
    if altitude:
        metres = _ratio(altitude[0])
        # GPSAltitudeRef 1 means the value is measured below sea level.
        if gps.get(GPS_ALT_REF) == 1:
            metres = -metres
        result.altitude_m = round(metres, 1)

    dop = gps.get(GPS_DOP)
    if dop:
        result.gps_dop = round(_ratio(dop[0]), 2)

    result.taken_at = _capture_time(exif, gps)

    make = ifd0.get(TAG_MAKE)
    model = ifd0.get(TAG_MODEL)
    parts = [p.strip() for p in (make, model) if isinstance(p, str) and p.strip()]
    if parts:
        # "Apple Apple iPhone 13" -> "Apple iPhone 13"
        if len(parts) == 2 and parts[1].lower().startswith(parts[0].lower()):
            parts = [parts[1]]
        result.camera = " ".join(parts)

    return result
