#!/usr/bin/env python3
"""
Diagnostic script to analyze stroke payloads and identify rendering issues.

Key observation: Some strokes work, others don't, and broken strokes appear
to repeat patterns from previous strokes.
"""

import struct
import zipfile
import sys
from typing import List, Tuple


def extract_stroke_payloads(sdocx_path: str) -> List[Tuple[dict, bytes]]:
    """Extract all stroke payloads with their metadata."""
    strokes = []

    with zipfile.ZipFile(sdocx_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith(".page"):
                with zf.open(name) as f:
                    page_data = f.read()
                    strokes.extend(parse_page_for_strokes(page_data))

    return strokes


def parse_page_for_strokes(data: bytes) -> List[Tuple[dict, bytes]]:
    """Parse page data and extract stroke payloads with bounding boxes."""
    strokes = []
    pos = 0

    # Skip to layer offset
    layer_offset = struct.unpack_from("<I", data, 0)[0]
    pos = layer_offset

    if pos + 4 > len(data):
        return strokes

    layer_count = struct.unpack_from("<H", data, pos)[0]
    pos += 4  # layer_count (2) + current_layer_index (2)

    for layer_idx in range(layer_count):
        if pos + 4 > len(data):
            break
        pos += 4  # skip 4 before each layer

        if pos + 12 > len(data):
            break

        next_offset = struct.unpack_from("<I", data, pos)[0]
        pos += 4

        # Skip layer header
        pos += 4  # 4 flag bytes
        pos += 4  # c value

        # Read content_flags from offset -5 from current pos
        content_flags = data[pos - 5] if pos >= 5 else 0

        # Skip optional fields based on content_flags
        if content_flags & 0x01:
            pos += 1
        if content_flags & 0x02:
            pos += 4
        if content_flags & 0x04:
            str_len = struct.unpack_from("<h", data, pos)[0]
            pos += 2 + (str_len * 2 if str_len > 0 else 0)
        if content_flags & 0x08:
            str_len = struct.unpack_from("<h", data, pos)[0]
            pos += 2 + (str_len * 2 if str_len > 0 else 0)
        if content_flags & 0x10:
            pos += 8
        if content_flags & 0x20:
            pos += 4

        if pos + 4 > len(data):
            break

        object_count = struct.unpack_from("<I", data, pos)[0]
        pos += 4

        # Parse objects
        for obj_idx in range(object_count):
            if pos + 3 > len(data):
                break

            obj_type = data[pos]
            child_count = struct.unpack_from("<h", data, pos + 1)[0]
            pos += 3

            if obj_type in [1, 15]:  # Stroke or StrokeV2
                if pos + 4 > len(data):
                    break
                binary_size = struct.unpack_from("<I", data, pos)[0]
                pos += 4

                if (
                    binary_size > 0
                    and binary_size < 2097152
                    and pos + binary_size <= len(data)
                ):
                    obj_data = data[pos : pos + binary_size]
                    pos += binary_size

                    # Parse object header to get bounding box
                    stroke_info = parse_stroke_object(obj_data, obj_idx)
                    if stroke_info:
                        strokes.append(stroke_info)
                else:
                    pos += binary_size if binary_size > 0 else 0
            elif obj_type in [2, 3, 4, 7, 8, 10, 11, 13, 14, 17, 19, 20, 21, 23]:
                if pos + 4 > len(data):
                    break
                binary_size = struct.unpack_from("<I", data, pos)[0]
                pos += 4 + binary_size
            else:
                # Skip unknown
                pass

        # Skip layer hash
        pos += 32

    return strokes


def parse_stroke_object(data: bytes, idx: int) -> Tuple[dict, bytes]:
    """Parse stroke object and extract payload with metadata."""
    if len(data) < 80:
        return None

    try:
        pos = 0
        total_size = struct.unpack_from("<I", data, pos)[0]
        pos += 4

        data_type = struct.unpack_from("<h", data, pos)[0]
        pos += 2
        if data_type != 0:
            return None

        var_data_offset = struct.unpack_from("<I", data, pos)[0]
        pos += 4

        flag_byte_len = data[pos]
        pos += 1

        flags = struct.unpack_from("<h", data, pos)[0]
        pos += 2
        if flag_byte_len > 2:
            pos += flag_byte_len - 2

        field_byte_len = data[pos]
        pos += 1

        field_flags = struct.unpack_from("<I", data, pos)[0]
        pos += 4

        format_version = struct.unpack_from("<I", data, pos)[0]
        pos += 4

        # UUID
        uuid_len = struct.unpack_from("<h", data, pos)[0]
        pos += 2
        uuid = ""
        if 0 < uuid_len <= 36:
            uuid = (
                data[pos : pos + uuid_len]
                .split(b"\x00")[0]
                .decode("utf-8", errors="replace")
            )
            pos += uuid_len
        elif uuid_len > 36:
            pos += uuid_len

        # Modified time
        modified_time = struct.unpack_from("<q", data, pos)[0]
        pos += 8

        # Bounding rect (4 doubles)
        left = struct.unpack_from("<d", data, pos)[0]
        top = struct.unpack_from("<d", data, pos + 8)[0]
        right = struct.unpack_from("<d", data, pos + 16)[0]
        bottom = struct.unpack_from("<d", data, pos + 24)[0]
        pos += 32

        # Get stroke payload
        payload_offset = var_data_offset if 0 < var_data_offset < len(data) else pos + 5
        payload = data[payload_offset:]

        info = {
            "index": idx,
            "uuid": uuid,
            "bbox": {"left": left, "top": top, "right": right, "bottom": bottom},
            "bbox_width": right - left,
            "bbox_height": bottom - top,
            "var_data_offset": var_data_offset,
            "payload_offset": payload_offset,
            "payload_size": len(payload),
            "total_obj_size": len(data),
        }

        return (info, payload)

    except Exception as e:
        return None


def analyze_payload(payload: bytes, info: dict):
    """Analyze stroke payload in detail."""
    print(f"\n{'=' * 60}")
    print(f"Stroke {info['index']}: {info['uuid'][:20]}...")
    print(
        f"  Bounding box: ({info['bbox']['left']:.2f}, {info['bbox']['top']:.2f}) - ({info['bbox']['right']:.2f}, {info['bbox']['bottom']:.2f})"
    )
    print(f"  Bbox size: {info['bbox_width']:.2f} x {info['bbox_height']:.2f}")
    print(
        f"  var_data_offset: {info['var_data_offset']}, payload_offset: {info['payload_offset']}"
    )
    print(f"  Payload size: {info['payload_size']} bytes")

    if len(payload) < 64:
        print(f"  [Payload too small]")
        return

    # Show first 80 bytes as hex
    print(f"\n  First 80 bytes of payload:")
    for i in range(0, min(80, len(payload)), 16):
        hex_str = " ".join(f"{b:02x}" for b in payload[i : i + 16])
        print(f"    {i:3d}: {hex_str}")

    # Check point_count at various offsets
    print(f"\n  Point count candidates:")
    for offset in [30, 32, 34, 36, 38]:
        if offset + 4 <= len(payload):
            val = struct.unpack_from("<I", payload, offset)[0]
            print(f"    Offset {offset}: {val}")

    # Try decoding first few deltas with 5.5 format starting at offset 60
    print(f"\n  Delta decoding (5.5 format) starting at offset 60:")
    point_count = struct.unpack_from("<I", payload, 34)[0]
    print(f"    Point count (offset 34): {point_count}")

    if point_count > 0 and point_count < 10000:
        x, y = 0.0, 0.0
        print(f"    First 10 deltas:")
        for i in range(min(10, point_count - 1)):
            off = 60 + i * 4
            if off + 4 <= len(payload):
                dx_raw, dy_raw = struct.unpack_from("<HH", payload, off)
                dx = decode_5_5(dx_raw)
                dy = decode_5_5(dy_raw)
                x += dx
                y += dy
                print(
                    f"      {i}: raw=({dx_raw:04x}, {dy_raw:04x}) -> delta=({dx:+.3f}, {dy:+.3f}) -> pos=({x:.3f}, {y:.3f})"
                )

        # Calculate full span
        x, y = 0.0, 0.0
        min_x, max_x, min_y, max_y = 0.0, 0.0, 0.0, 0.0
        for i in range(point_count - 1):
            off = 60 + i * 4
            if off + 4 > len(payload):
                break
            dx_raw, dy_raw = struct.unpack_from("<HH", payload, off)
            x += decode_5_5(dx_raw)
            y += decode_5_5(dy_raw)
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)

        span_x = max_x - min_x
        span_y = max_y - min_y
        print(f"\n    Decoded span: {span_x:.2f} x {span_y:.2f}")
        print(
            f"    Expected (bbox): {info['bbox_width']:.2f} x {info['bbox_height']:.2f}"
        )
        print(
            f"    Error: X={abs(span_x - info['bbox_width']):.2f}, Y={abs(span_y - info['bbox_height']):.2f}"
        )


def decode_5_5(word: int) -> float:
    """5.5 fixed-point decoder."""
    fractional = word & 0x1F
    integer = (word >> 5) & 0x1F
    result = integer + (fractional / 32.0)
    if word & 0x8000:
        result = -result
    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 diagnose_strokes.py <sdocx_file>")
        sys.exit(1)

    sdocx_path = sys.argv[1]
    print(f"Analyzing: {sdocx_path}")

    strokes = extract_stroke_payloads(sdocx_path)
    print(f"Found {len(strokes)} strokes")

    for info, payload in strokes:
        analyze_payload(payload, info)


if __name__ == "__main__":
    main()
