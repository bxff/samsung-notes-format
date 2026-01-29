#!/usr/bin/env python3
"""
Compare header layout between working and broken files.
Focus on finding the point count and understanding stride.
"""

import struct
import zipfile
from sdocx_extractor import BinaryReader


def decode_3_12(word: int) -> float:
    """Decode using 3.12 fixed-point from sm_ShortToFloatDelta."""
    integer_part = (word >> 12) & 0x7
    fractional_part = word & 0xFFF
    result = integer_part + (fractional_part / 4096.0)
    if word & 0x8000:
        result = -result
    return result


def extract_and_analyze(filepath: str, name: str):
    print(f"\n{'=' * 70}")
    print(f"FILE: {name}")
    print(f"{'=' * 70}")

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
                            format_version = obj_reader.read_int32()
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
                            payload = obj_data[payload_offset:]

                            bbox_w = bbox["right"] - bbox["left"]
                            bbox_h = bbox["bottom"] - bbox["top"]

                            print(
                                f"\nStroke {obj_i}: type={obj_type}, format_version={format_version}"
                            )
                            print(f"  BBox: {bbox_w:.2f} x {bbox_h:.2f}")
                            print(f"  Payload size: {len(payload)} bytes")

                            # Check potential point counts
                            for off in [16, 32, 34]:
                                if off + 2 <= len(payload):
                                    val16 = struct.unpack_from("<H", payload, off)[0]
                                    if 1 <= val16 <= 10000:
                                        print(
                                            f"  Point count at offset {off}? = {val16}"
                                        )

                            # First 8 uint16 at offset 60
                            print(f"  First 8 values at offset 60:")
                            for i in range(8):
                                if 60 + i * 2 + 2 <= len(payload):
                                    val = struct.unpack_from("<H", payload, 60 + i * 2)[
                                        0
                                    ]
                                    d = decode_3_12(val)
                                    print(f"    [{i}] 0x{val:04x} -> 3.12={d:8.4f}")

                            # Try decoding with 3.12 at offset 68 (skip first 8 bytes = 4 values)
                            # and see if it matches bbox
                            point_count = (
                                struct.unpack_from("<H", payload, 32)[0]
                                if len(payload) > 34
                                else 0
                            )
                            print(
                                f"\n  Trying offset 68 with point_count={point_count}:"
                            )

                            if point_count > 0 and point_count < 10000:
                                x, y = 0.0, 0.0
                                min_x, max_x = 0.0, 0.0
                                min_y, max_y = 0.0, 0.0

                                off = 68  # Skip first 8 bytes of "header"
                                for i in range(
                                    min(point_count, (len(payload) - off) // 4)
                                ):
                                    if off + 4 > len(payload):
                                        break
                                    dx_raw, dy_raw = struct.unpack_from(
                                        "<HH", payload, off
                                    )
                                    off += 4

                                    dx = decode_3_12(dx_raw)
                                    dy = decode_3_12(dy_raw)
                                    x += dx
                                    y += dy
                                    min_x, max_x = min(min_x, x), max(max_x, x)
                                    min_y, max_y = min(min_y, y), max(max_y, y)

                                span_x = max_x - min_x
                                span_y = max_y - min_y

                                print(
                                    f"    Decoded span: X={span_x:.2f} Y={span_y:.2f}"
                                )
                                print(
                                    f"    Expected:     X={bbox_w:.2f} Y={bbox_h:.2f}"
                                )
                                print(
                                    f"    Error:        X={abs(span_x - bbox_w):.2f} Y={abs(span_y - bbox_h):.2f}"
                                )

                            if obj_i >= 0:  # Just first stroke
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


# Compare
extract_and_analyze("sdocxFiles/ThisIsTheTitle_251009_042302.sdocx", "WORKING")
extract_and_analyze(
    "sdocxFiles/Mako OT N problem still exists Minimal dub_260129_190327.sdocx",
    "BROKEN",
)
