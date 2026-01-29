#!/usr/bin/env python3
"""
Deep analysis of stroke payload header structure.
"""

import struct
import zipfile
import sys
from sdocx_extractor import BinaryReader, PageParser


def analyze_header_fields(payload: bytes, bbox: dict, stroke_idx: int):
    """Analyze header fields in detail."""
    print(f"\n{'=' * 70}")
    print(f"STROKE {stroke_idx} - HEADER ANALYSIS")
    print(f"{'=' * 70}")
    print(f"Payload size: {len(payload)} bytes")
    print(
        f"BBox: L={bbox['left']:.2f} T={bbox['top']:.2f} R={bbox['right']:.2f} B={bbox['bottom']:.2f}"
    )
    bbox_w = bbox["right"] - bbox["left"]
    bbox_h = bbox["bottom"] - bbox["top"]
    print(f"BBox size: {bbox_w:.2f} x {bbox_h:.2f}")

    if len(payload) < 80:
        print("Payload too short!")
        return

    # Analyze all fields byte by byte
    print(f"\n--- Field-by-field analysis ---")

    # Check int32 fields
    print(f"\nInt32 fields:")
    for off in range(0, 64, 4):
        val = struct.unpack_from("<I", payload, off)[0]
        val_signed = struct.unpack_from("<i", payload, off)[0]
        if val > 0 and val < 0xFFFFFFFF:
            print(f"  Offset {off:2d}: {val:10d} (0x{val:08x})  signed: {val_signed}")

    # Check int16 fields
    print(f"\nInt16 fields (around offset 32-48):")
    for off in range(30, 50, 2):
        val = struct.unpack_from("<H", payload, off)[0]
        val_signed = struct.unpack_from("<h", payload, off)[0]
        print(f"  Offset {off:2d}: {val:5d} (0x{val:04x})  signed: {val_signed:6d}")

    # Check float32 fields
    print(f"\nFloat32 fields:")
    for off in range(0, 64, 4):
        try:
            val = struct.unpack_from("<f", payload, off)[0]
            if not (val != val):  # not NaN
                if -1e6 < val < 1e6 and val != 0:
                    print(f"  Offset {off:2d}: {val:14.6f}")
        except:
            pass

    # Look for recognizable patterns
    print(f"\n--- Pattern search ---")

    # The bbox dimensions might be encoded somewhere
    # Let's look for values that match bbox width/height
    for off in range(0, min(80, len(payload) - 4)):
        # Float32
        try:
            val = struct.unpack_from("<f", payload, off)[0]
            if abs(val - bbox_w) < 1.0:
                print(
                    f"  Offset {off}: float32 {val:.2f} matches bbox width {bbox_w:.2f}"
                )
            if abs(val - bbox_h) < 1.0:
                print(
                    f"  Offset {off}: float32 {val:.2f} matches bbox height {bbox_h:.2f}"
                )
        except:
            pass

        # Fixed point 8.8
        if off + 2 <= len(payload):
            val = struct.unpack_from("<H", payload, off)[0]
            fp_8_8 = val / 256.0
            if abs(fp_8_8 - bbox_w) < 1.0:
                print(
                    f"  Offset {off}: 8.8 fixed {fp_8_8:.2f} matches bbox width {bbox_w:.2f}"
                )
            if abs(fp_8_8 - bbox_h) < 1.0:
                print(
                    f"  Offset {off}: 8.8 fixed {fp_8_8:.2f} matches bbox height {bbox_h:.2f}"
                )

    # Check if the data stream starts with something other than deltas
    print(f"\n--- First 20 uint16 values at offset 60 ---")
    off = 60
    for i in range(20):
        if off + 2 > len(payload):
            break
        val = struct.unpack_from("<H", payload, off)[0]
        # Check for patterns
        desc = ""
        if val == 0x0000:
            desc = "(zero)"
        elif val == 0x8000:
            desc = "(sign bit only)"
        elif val == 0x2000:
            desc = "(0.25 in 2.14?)"
        elif val == 0x4000:
            desc = "(0.5 in 2.14?)"
        elif val == 0xE000:
            desc = "(-0.25 in 2.14?)"
        elif val & 0x8000:
            desc = f"(negative, low bits: 0x{val & 0x7FFF:04x})"
        print(f"  [{i:2d}] offset {off}: 0x{val:04x} ({val:5d}) {desc}")
        off += 2

    # Let's try interpreting as different fixed-point formats
    print(f"\n--- Trying to find the START of actual delta data ---")

    # The pattern 0x4083 appears consistently - what is this?
    for search_off in range(40, min(100, len(payload) - 20)):
        # Look for where we first see small varying values
        vals = []
        for i in range(10):
            if search_off + i * 2 + 2 <= len(payload):
                v = struct.unpack_from("<H", payload, search_off + i * 2)[0]
                vals.append(v)

        # Check if this looks like delta data (small values, mostly around 0x8000)
        small_delta_count = sum(1 for v in vals if 0x7F00 <= v <= 0x80FF or v <= 0x00FF)
        if small_delta_count >= 7:
            print(f"  Offset {search_off}: looks like delta data starts here")
            print(f"    First 10 values: {[f'0x{v:04x}' for v in vals]}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_header.py <sdocx_file>")
        sys.exit(1)

    filepath = sys.argv[1]

    with zipfile.ZipFile(filepath, "r") as zf:
        for filename in zf.namelist():
            if filename.endswith(".page"):
                with zf.open(filename) as f:
                    page_data = f.read()

                reader = BinaryReader(page_data)
                layer_offset = struct.unpack_from("<I", page_data, 0)[0]
                reader.seek(layer_offset)

                layer_count = reader.read_short()
                reader.read_short()

                stroke_idx = 0
                for layer_i in range(layer_count):
                    reader.skip(4)
                    reader.read_int32()
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

                        if obj_type in [1, 15]:
                            binary_size = reader.read_int32()
                            obj_data = reader.read_bytes(binary_size)

                            obj_reader = BinaryReader(obj_data)
                            obj_reader.read_int32()
                            data_type = obj_reader.read_short()
                            var_data_offset = obj_reader.read_int32()
                            flag_byte_len = obj_reader.read_byte()
                            obj_reader.read_short()
                            if flag_byte_len > 2:
                                obj_reader.skip(flag_byte_len - 2)
                            obj_reader.read_byte()
                            obj_reader.read_int32()
                            obj_reader.read_int32()
                            uuid_len = obj_reader.read_short()
                            if uuid_len > 0:
                                obj_reader.skip(uuid_len)
                            obj_reader.read_int64()

                            bbox = {
                                "left": obj_reader.read_double(),
                                "top": obj_reader.read_double(),
                                "right": obj_reader.read_double(),
                                "bottom": obj_reader.read_double(),
                            }

                            payload_offset = (
                                var_data_offset
                                if 0 < var_data_offset < len(obj_data)
                                else obj_reader.tell() + 5
                            )
                            stroke_payload = obj_data[payload_offset:]

                            analyze_header_fields(stroke_payload, bbox, stroke_idx)
                            stroke_idx += 1

                            if stroke_idx >= 2:  # Just analyze first 2 strokes
                                break
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

                    reader.skip(32)


if __name__ == "__main__":
    main()
