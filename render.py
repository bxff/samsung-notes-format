#!/usr/bin/env python3
"""Render the handwriting in a Samsung Notes .sdocx file to an SVG.

Reads the strokes straight out of the binary `.page` record, decodes the
delta-encoded pen coordinates, and draws every stroke inside its stored
bounding box. If the decode is right, each stroke sits snugly in its box.

    python3 render.py note.sdocx [out.svg]

Format notes (worked out from libSPenModel.so; see the write-up linked in the
README): coordinates are 16-bit deltas, magnitude = (word & 0x7FFF) / 32, sign
in bit 15, accumulated from the start of the stroke.
"""

import struct
import sys
import zipfile

STROKE_TYPES = (1, 15)            # Stroke, StrokeV2
# object types that carry a 4-byte size prefix we can skip over
SIZED_TYPES = (1, 2, 3, 4, 7, 8, 10, 11, 13, 14, 15, 17, 19, 20, 21, 23)


def decode_delta(word):
    """One X/Y delta word -> pixels. magnitude = (word & 0x7FFF)/32, sign bit 15."""
    magnitude = (word & 0x7FFF) / 32.0
    return -magnitude if word & 0x8000 else magnitude


def decode_stroke(payload):
    """Delta stream -> points relative to (0, 0). Returns [] if it doesn't parse."""
    if len(payload) < 64:
        return []
    # Two payload variants: a padded one prepends 16 zero bytes and shifts the
    # point count and delta stream forward by 16.
    padded = all(b == 0 for b in payload[16:32])
    count_off, delta_off = (50, 76) if padded else (34, 60)
    if len(payload) < delta_off + 4:
        return []

    count = struct.unpack_from("<I", payload, count_off)[0]
    if not (1 <= count <= 200_000):
        return []

    x = y = 0.0
    points = [(x, y)]
    off = delta_off
    for _ in range(count - 1):
        if off + 4 > len(payload):
            break
        dx, dy = struct.unpack_from("<HH", payload, off)
        off += 4
        x += decode_delta(dx)
        y += decode_delta(dy)
        points.append((x, y))
    return points


def read_strokes(page):
    """Walk the .page record and yield (bbox, points) for every stroke."""
    base = struct.unpack_from("<I", page, 0)[0]
    page_w = struct.unpack_from("<I", page, 0x16)[0]
    page_h = struct.unpack_from("<I", page, 0x1A)[0]

    strokes = []
    pos = base
    layer_count = struct.unpack_from("<H", page, pos)[0]
    pos += 4
    for _ in range(layer_count):
        pos += 4
        pos += 4  # next-layer offset
        pos += 4  # 4 flag bytes
        content_flags = page[pos - 1]
        pos += 4  # layer id
        if content_flags & 0x01:
            pos += 1
        if content_flags & 0x02:
            pos += 4
        for bit in (0x04, 0x08):
            if content_flags & bit:
                n = struct.unpack_from("<h", page, pos)[0]
                pos += 2 + (n * 2 if n > 0 else 0)
        if content_flags & 0x10:
            pos += 8
        if content_flags & 0x20:
            pos += 4

        object_count = struct.unpack_from("<I", page, pos)[0]
        pos += 4
        for _ in range(object_count):
            obj_type = page[pos]
            pos += 3  # type byte + child count (short)
            if obj_type not in SIZED_TYPES:
                continue
            size = struct.unpack_from("<I", page, pos)[0]
            pos += 4
            obj = page[pos:pos + size]
            pos += size
            if obj_type in STROKE_TYPES:
                parsed = parse_stroke_object(obj)
                if parsed:
                    strokes.append(parsed)
        pos += 32  # layer hash

    return page_w, page_h, strokes


def parse_stroke_object(obj):
    """One stroke object -> (bbox, absolute points), or None."""
    if len(obj) < 80:
        return None
    try:
        pos = 0
        pos += 4                                              # total size
        if struct.unpack_from("<h", obj, pos)[0] != 0:        # data type, must be 0
            return None
        pos += 2
        var_data_offset = struct.unpack_from("<I", obj, pos)[0]
        pos += 4
        flag_len = obj[pos]
        pos += 1 + 2 + max(0, flag_len - 2)                   # flag length + flags
        pos += 1 + 4 + 4                                      # field length, flags, version
        uuid_len = struct.unpack_from("<h", obj, pos)[0]
        pos += 2 + (uuid_len if uuid_len > 0 else 0)
        pos += 8                                              # modified time
        left, top, right, bottom = struct.unpack_from("<4d", obj, pos)
        pos += 32

        payload_off = var_data_offset if 0 < var_data_offset < len(obj) else pos + 5
        points = decode_stroke(obj[payload_off:])
        if len(points) <= 2:
            return None

        # Drop the 2-point terminator, then anchor the stroke's top-left to the box.
        points = points[:-2]
        min_x = min(p[0] for p in points)
        min_y = min(p[1] for p in points)
        points = [(px - min_x + left, py - min_y + top) for px, py in points]
        return (left, top, right, bottom), points
    except (struct.error, IndexError):
        return None


def to_svg(strokes, pad=24):
    # Crop to the strokes themselves so the handwriting fills the frame and each
    # box is visible, rather than floating in a mostly-empty page.
    x0 = min(b[0] for b, _ in strokes) - pad
    y0 = min(b[1] for b, _ in strokes) - pad
    x1 = max(b[2] for b, _ in strokes) + pad
    y1 = max(b[3] for b, _ in strokes) + pad
    w, h = x1 - x0, y1 - y0
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.1f} {y0:.1f} {w:.1f} {h:.1f}" '
        f'width="{w:.0f}" height="{h:.0f}">',
        f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" fill="white"/>',
    ]
    for (left, top, right, bottom), points in strokes:
        out.append(
            f'<rect x="{left:.1f}" y="{top:.1f}" width="{right - left:.1f}" '
            f'height="{bottom - top:.1f}" fill="none" stroke="#bbb" '
            f'stroke-width="1" stroke-dasharray="4 3"/>'
        )
        d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        out.append(f'<path d="{d}" fill="none" stroke="#111" stroke-width="2" '
                   f'stroke-linecap="round" stroke-linejoin="round"/>')
    out.append("</svg>")
    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 render.py note.sdocx [out.svg]")
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "out.svg"

    with zipfile.ZipFile(src) as z:
        page_name = next(n for n in z.namelist() if n.endswith(".page"))
        page = z.read(page_name)

    _, _, strokes = read_strokes(page)
    if not strokes:
        sys.exit("no strokes found")
    with open(out, "w") as f:
        f.write(to_svg(strokes))
    print(f"{len(strokes)} strokes -> {out}")


if __name__ == "__main__":
    main()
