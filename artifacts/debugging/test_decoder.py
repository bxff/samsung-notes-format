#!/usr/bin/env python3
"""
Test the correct 3.12 fixed-point decoder from sm_ShortToFloatDelta.

From disassembly at 0x2f8638:
  ubfx   w8, w0, #12, #3    ; Extract bits 12-14 (3 bits) -> integer part
  and    w9, w0, #0xfff     ; Mask low 12 bits -> fractional part
  scvtf  s0, w9, #0xc       ; Convert frac to float / 4096
  scvtf  s1, w8             ; Convert int to float
  sxth   w8, w0             ; Sign-extend to 16-bit
  cmp    w8, #0x0           ; Check sign
  fadd   s0, s0, s1         ; result = int + frac
  fneg   s1, s0             ; negate
  fcsel  s0, s1, s0, lt     ; if negative, use negated

Format:
  Bits 12-14 (3 bits): Integer part (0-7)
  Bits 0-11 (12 bits): Fractional part (value / 4096)
  Bit 15: Sign (if original signed 16-bit < 0, negate result)
"""

import struct


def decode_3_12_correct(word: int) -> float:
    """Decode using the exact algorithm from sm_ShortToFloatDelta."""
    integer_part = (word >> 12) & 0x7  # bits 12-14 (3 bits)
    fractional_part = word & 0xFFF  # bits 0-11 (12 bits)

    result = integer_part + (fractional_part / 4096.0)

    # Sign check: sign-extend the 16-bit value and check if negative
    if word & 0x8000:  # bit 15 set = negative
        result = -result

    return result


# Test vectors from the broken file:
test_values = [
    (0x0000, "zero"),
    (0x2000, "0.25 test"),
    (0x4000, "0.5 test"),
    (0x8000, "sign bit only"),
    (0x8001, "small negative"),
    (0x8005, "negative low bits"),
    (0x05E8, "positive value"),
    (0x4083, "positive with frac"),
    (0x4AE3, "larger positive"),
]

print("Testing 3.12 decoder:")
print("-" * 60)
for word, desc in test_values:
    result = decode_3_12_correct(word)
    # Also show 5.5 for comparison
    int_5 = (word >> 5) & 0x1F
    frac_5 = word & 0x1F
    result_5_5 = int_5 + frac_5 / 32.0
    if word & 0x8000:
        result_5_5 = -result_5_5
    print(f"  0x{word:04x}: 3.12={result:8.4f}  5.5={result_5_5:8.4f}  ({desc})")

print()
print("Now let's verify against bounding box spans...")

# From the broken file stroke 0:
# BBox: L=646.85 T=600.71 R=668.10 B=620.91
# Expected: width=21.25, height=20.20
# Point count at offset 32 = 1762

# Raw delta words from offset 60 (skipping first two which seem to be header):
# After (0,0) and first point...
test_stroke_data = [
    # These are dX, dY pairs from offset 68 onwards (after first 2 entries)
    (0x8000, 0x8000),  # Both sign bits set, both 0
    (0x8000, 0x8003),
    (0x8000, 0x8005),
    (0x8000, 0x800E),
    (0x8002, 0x8005),
    (0x8001, 0x8005),
    (0x8000, 0x8007),
    (0x8002, 0x8006),
]

print("Decoding first deltas with 3.12 format:")
x, y = 0.0, 0.0
for dx_raw, dy_raw in test_stroke_data:
    dx = decode_3_12_correct(dx_raw)
    dy = decode_3_12_correct(dy_raw)
    x += dx
    y += dy
    print(
        f"  dx=0x{dx_raw:04x} -> {dx:8.5f}  dy=0x{dy_raw:04x} -> {dy:8.5f}  pos=({x:8.4f}, {y:8.4f})"
    )

# Now the key insight: the first two values at offset 60 are NOT deltas
# Let's check what they might be
print()
print("First values at offset 60 (NOT deltas?):")
first_vals = [(0x0000, 0x2000), (0x05E8, 0x4083)]
for i, (v1, v2) in enumerate(first_vals):
    d1 = decode_3_12_correct(v1)
    d2 = decode_3_12_correct(v2)
    print(f"  [{i}] 0x{v1:04x}, 0x{v2:04x} -> ({d1:.4f}, {d2:.4f})")

# These look like initial X,Y coordinates: (0, 2) and (1.512, 4.032)
# The second pair appears to be the first point's absolute position!

print()
print("Hypothesis: First pair at offset 60 is not (dX,dY) deltas")
print("but rather some kind of scaling or initial state values.")
print()
print("Let's check if delta data starts at offset 68 (after 8 bytes of header)...")
