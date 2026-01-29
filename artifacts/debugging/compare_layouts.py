#!/usr/bin/env python3
"""
Compare stroke payload headers between working and broken files.
"""

import struct
import zipfile
import sys
from sdocx_extractor import BinaryReader


def extract_payloads(filepath: str):
    """Extract all stroke payloads from file."""
    payloads = []

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
                            stroke_payload = obj_data[payload_offset:]

                            payloads.append(
                                {
                                    "format_version": format_version,
                                    "payload": stroke_payload,
                                    "bbox": bbox,
                                }
                            )
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

    return payloads


def compare_layouts():
    working_file = "sdocxFiles/ThisIsTheTitle_251009_042302.sdocx"
    broken_file = (
        "sdocxFiles/Mako OT N problem still exists Minimal dub_260129_190327.sdocx"
    )

    print("=" * 80)
    print("WORKING FILE")
    print("=" * 80)
    working = extract_payloads(working_file)
    for i, p in enumerate(working[:2]):
        payload = p["payload"]
        print(f"\nStroke {i}:")
        print(f"  Format version: {p['format_version']}")
        print(f"  Payload size: {len(payload)}")

        # Key fields
        print(f"  Header bytes 0-63:")
        for off in range(0, 64, 16):
            hex_str = " ".join(
                f"{payload[off + j]:02x}" for j in range(min(16, len(payload) - off))
            )
            print(f"    {off:3d}: {hex_str}")

        # Potential point count locations
        for off in [16, 18, 20, 32, 34, 36]:
            if off + 4 <= len(payload):
                val16 = struct.unpack_from("<H", payload, off)[0]
                val32 = struct.unpack_from("<I", payload, off)[0]
                if 1 <= val16 <= 10000:
                    print(f"  Offset {off} uint16: {val16}")
                if 1 <= val32 <= 10000 and val32 != val16:
                    print(f"  Offset {off} uint32: {val32}")

    print("\n" + "=" * 80)
    print("BROKEN FILE")
    print("=" * 80)
    broken = extract_payloads(broken_file)
    for i, p in enumerate(broken[:2]):
        payload = p["payload"]
        print(f"\nStroke {i}:")
        print(f"  Format version: {p['format_version']}")
        print(f"  Payload size: {len(payload)}")

        print(f"  Header bytes 0-63:")
        for off in range(0, 64, 16):
            hex_str = " ".join(
                f"{payload[off + j]:02x}" for j in range(min(16, len(payload) - off))
            )
            print(f"    {off:3d}: {hex_str}")

        for off in [16, 18, 20, 32, 34, 36]:
            if off + 4 <= len(payload):
                val16 = struct.unpack_from("<H", payload, off)[0]
                val32 = struct.unpack_from("<I", payload, off)[0]
                if 1 <= val16 <= 10000:
                    print(f"  Offset {off} uint16: {val16}")
                if 1 <= val32 <= 10000 and val32 != val16:
                    print(f"  Offset {off} uint32: {val32}")

    # Now let's look for the key difference
    print("\n" + "=" * 80)
    print("KEY DIFFERENCE ANALYSIS")
    print("=" * 80)

    # Check specific bytes that might indicate format
    for off in range(0, 60, 2):
        w_vals = set()
        b_vals = set()

        for p in working:
            if len(p["payload"]) > off + 2:
                w_vals.add(struct.unpack_from("<H", p["payload"], off)[0])

        for p in broken:
            if len(p["payload"]) > off + 2:
                b_vals.add(struct.unpack_from("<H", p["payload"], off)[0])

        if w_vals and b_vals and not w_vals.intersection(b_vals):
            print(
                f"Offset {off:2d}: Working={w_vals}, Broken={b_vals} *** DISTINCT ***"
            )


if __name__ == "__main__":
    compare_layouts()
