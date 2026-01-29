#!/usr/bin/env python3
"""
Diagnostic script to analyze stroke payloads and compare decoded values against bounding boxes.
"""

import struct
import zipfile
import sys
from sdocx_extractor import BinaryReader, PageParser


def hex_dump(data: bytes, offset: int = 0, length: int = 128) -> str:
    """Create a hex dump of data."""
    lines = []
    for i in range(0, min(length, len(data)), 16):
        hex_part = " ".join(f"{b:02x}" for b in data[i : i + 16])
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data[i : i + 16])
        lines.append(f"{offset + i:04x}: {hex_part:<48} {ascii_part}")
    return "\n".join(lines)


def decode_5_5(word: int) -> float:
    """Current 5.5 fixed-point decoder."""
    fractional_part = word & 0x1F  # bits 0-4
    integer_part = (word >> 5) & 0x1F  # bits 5-9
    result = integer_part + (fractional_part / 32.0)
    if word & 0x8000:
        result = -result
    return result


def decode_3_12(word: int) -> float:
    """Alternative 3.12 fixed-point decoder."""
    # Interpret as signed 16-bit, then divide by 4096
    if word & 0x8000:
        word = word - 0x10000
    return word / 4096.0


def decode_4_11(word: int) -> float:
    """Alternative 4.11 fixed-point decoder."""
    if word & 0x8000:
        word = word - 0x10000
    return word / 2048.0


def decode_signed_16(word: int) -> float:
    """Plain signed 16-bit."""
    if word & 0x8000:
        word = word - 0x10000
    return float(word)


def analyze_stroke_payload(payload: bytes, bbox: dict, stroke_idx: int):
    """Analyze a stroke payload in detail."""
    print(f"\n{'=' * 60}")
    print(f"STROKE {stroke_idx}")
    print(f"{'=' * 60}")
    print(f"Payload size: {len(payload)} bytes")
    print(
        f"Bounding box: L={bbox['left']:.2f} T={bbox['top']:.2f} R={bbox['right']:.2f} B={bbox['bottom']:.2f}"
    )
    print(f"Expected width:  {bbox['right'] - bbox['left']:.2f}")
    print(f"Expected height: {bbox['bottom'] - bbox['top']:.2f}")

    if len(payload) < 64:
        print("Payload too short!")
        return

    # Header analysis
    print(f"\n--- Header bytes 0-63 ---")
    print(hex_dump(payload, 0, 64))

    # Read point count at offset 34
    point_count = struct.unpack_from("<I", payload, 34)[0]
    print(f"\nPoint count (at offset 34): {point_count}")

    # Check for alternative point count locations
    for off in [30, 32, 34, 36, 38, 40]:
        if off + 4 <= len(payload):
            val = struct.unpack_from("<I", payload, off)[0]
            if 1 <= val <= 10000:
                print(f"  Potential count at offset {off}: {val}")

    # Try different decoding strategies
    print(f"\n--- Decoding comparison (first 10 deltas) ---")

    off = 60
    decoders = [
        ("5.5 fixed (current)", decode_5_5),
        ("3.12 fixed", decode_3_12),
        ("4.11 fixed", decode_4_11),
        ("signed 16-bit", decode_signed_16),
    ]

    print(f"\nRaw delta words at offset 60:")
    for i in range(min(10, (len(payload) - off) // 4)):
        dx_raw, dy_raw = struct.unpack_from("<HH", payload, off + i * 4)
        print(
            f"  Point {i}: dx_raw=0x{dx_raw:04x} ({dx_raw:5d})  dy_raw=0x{dy_raw:04x} ({dy_raw:5d})"
        )

    print("\nDecoded deltas:")
    for name, decoder in decoders:
        print(f"\n  {name}:")
        x, y = 0.0, 0.0
        min_x, max_x = 0.0, 0.0
        min_y, max_y = 0.0, 0.0

        for i in range(min(point_count, (len(payload) - off) // 4)):
            dx_raw, dy_raw = struct.unpack_from("<HH", payload, off + i * 4)
            dx = decoder(dx_raw)
            dy = decoder(dy_raw)
            x += dx
            y += dy
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)

            if i < 5:
                print(
                    f"    Point {i}: dx={dx:8.3f} dy={dy:8.3f} -> ({x:8.3f}, {y:8.3f})"
                )

        span_x = max_x - min_x
        span_y = max_y - min_y
        expected_w = bbox["right"] - bbox["left"]
        expected_h = bbox["bottom"] - bbox["top"]

        x_error = abs(span_x - expected_w)
        y_error = abs(span_y - expected_h)

        print(f"    Decoded span: X={span_x:.2f} Y={span_y:.2f}")
        print(f"    Expected:     X={expected_w:.2f} Y={expected_h:.2f}")
        print(f"    Error:        X={x_error:.2f} Y={y_error:.2f}")

        if x_error < 2 and y_error < 2:
            print(f"    *** GOOD MATCH! ***")

    # Check if there's a different data layout
    print(f"\n--- Alternative offset analysis ---")
    for start_off in [52, 56, 60, 64, 68]:
        if start_off + 8 > len(payload):
            continue
        x, y = 0.0, 0.0
        min_x, max_x = 0.0, 0.0
        min_y, max_y = 0.0, 0.0

        for i in range(min(point_count, (len(payload) - start_off) // 4)):
            dx_raw, dy_raw = struct.unpack_from("<HH", payload, start_off + i * 4)
            dx = decode_5_5(dx_raw)
            dy = decode_5_5(dy_raw)
            x += dx
            y += dy
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)

        span_x = max_x - min_x
        span_y = max_y - min_y
        expected_w = bbox["right"] - bbox["left"]
        expected_h = bbox["bottom"] - bbox["top"]

        x_error = abs(span_x - expected_w)
        y_error = abs(span_y - expected_h)

        match = "*** MATCH ***" if x_error < 2 and y_error < 2 else ""
        print(
            f"  Offset {start_off}: span=({span_x:.1f}, {span_y:.1f}) error=({x_error:.1f}, {y_error:.1f}) {match}"
        )


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 diagnose_stroke.py <sdocx_file>")
        sys.exit(1)

    filepath = sys.argv[1]

    with zipfile.ZipFile(filepath, "r") as zf:
        for filename in zf.namelist():
            if filename.endswith(".page"):
                with zf.open(filename) as f:
                    page_data = f.read()

                # Parse page to get object locations and bounding boxes
                parser = PageParser()
                page = parser.parse(page_data)

                print(f"Page: {page.width}x{page.height}")
                print(f"Layers: {len(page.layers)}")

                # We need to re-parse to get raw payload data
                # Let's do a manual extraction
                reader = BinaryReader(page_data)

                # Skip to layer offset
                layer_offset = struct.unpack_from("<I", page_data, 0)[0]
                reader.seek(layer_offset)

                layer_count = reader.read_short()
                reader.read_short()  # current_layer_index

                stroke_idx = 0
                for layer_i in range(layer_count):
                    reader.skip(4)
                    reader.read_int32()  # next offset
                    reader.read_byte()
                    flags2 = reader.read_byte()
                    reader.read_byte()
                    content_flags = reader.read_byte()
                    reader.read_int32()

                    if content_flags & 0x01:
                        reader.read_byte()
                    if content_flags & 0x02:
                        reader.read_int32()
                    if content_flags & 0x04:
                        reader.read_string()
                    if content_flags & 0x08:
                        reader.read_string()
                    if content_flags & 0x10:
                        reader.read_int64()
                    if content_flags & 0x20:
                        reader.read_int32()

                    object_count = reader.read_int32()

                    for obj_i in range(object_count):
                        obj_type = reader.read_byte()
                        child_count = reader.read_short()

                        if obj_type in [1, 15]:  # Stroke types
                            binary_size = reader.read_int32()
                            obj_start = reader.tell()
                            obj_data = reader.read_bytes(binary_size)

                            # Parse object header to get bounding box
                            obj_reader = BinaryReader(obj_data)
                            obj_reader.read_int32()  # total_size
                            data_type = obj_reader.read_short()
                            var_data_offset = obj_reader.read_int32()
                            flag_byte_len = obj_reader.read_byte()
                            obj_reader.read_short()  # flags
                            if flag_byte_len > 2:
                                obj_reader.skip(flag_byte_len - 2)
                            obj_reader.read_byte()  # field_byte_len
                            obj_reader.read_int32()  # field_flags
                            obj_reader.read_int32()  # format_version
                            uuid_len = obj_reader.read_short()
                            if uuid_len > 0:
                                obj_reader.skip(uuid_len)
                            obj_reader.read_int64()  # modified_time

                            bbox = {
                                "left": obj_reader.read_double(),
                                "top": obj_reader.read_double(),
                                "right": obj_reader.read_double(),
                                "bottom": obj_reader.read_double(),
                            }

                            # Extract stroke payload
                            payload_offset = (
                                var_data_offset
                                if 0 < var_data_offset < len(obj_data)
                                else obj_reader.tell() + 5
                            )
                            stroke_payload = obj_data[payload_offset:]

                            analyze_stroke_payload(stroke_payload, bbox, stroke_idx)
                            stroke_idx += 1
                        else:
                            if obj_type in [
                                1,
                                2,
                                3,
                                4,
                                7,
                                8,
                                10,
                                11,
                                13,
                                14,
                                15,
                                17,
                                19,
                                20,
                                21,
                                23,
                            ]:
                                binary_size = reader.read_int32()
                                reader.skip(binary_size)

                    reader.skip(32)  # layer hash


if __name__ == "__main__":
    main()
