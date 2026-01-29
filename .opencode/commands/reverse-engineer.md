---
description: Reverse engineer binary format from .so native library
agent: explore
---

# Reverse Engineering Workflow for Samsung Notes SDOCX Format

You are reverse engineering the Samsung Notes `.sdocx` file format by analyzing the native library `libSPenModel.so`.

## Target Files

- **Native library:** `decompiled_source/resources/lib/arm64-v8a/libSPenModel.so`
- **Java wrapper:** `decompiled_source/sources/j0/p.java` (ObjectStroke class)
- **Test files:** `sdocxFiles/*.sdocx`
- **Current extractor:** `sdocx_extractor.py`

## Workflow

### Phase 1: Identify Target Functions

Search for relevant exported symbols in the .so file:
- Functions containing "stroke", "restore", "delta", "float", "point"
- Key functions discovered so far:
  - `sm_RestoreStroke` at 0x2f62b0 - main stroke restoration
  - `sm_ShortToFloatDelta` at 0x2f8638 - scalar delta decoding (3.12 format)
  - SIMD block at 0x2f6790-0x2f6870 - vector delta decoding (5.5 format)

### Phase 2: Disassembly Analysis

When analyzing ARM64 assembly, look for:
- **Fixed-point patterns:** `AND` with masks (0x1F, 0xFFF), bit shifts (`LSR`, `UBFX`)
- **Float conversion:** `SCVTF` instructions
- **Scale factors:** `FMUL` with constants like 1/32.0 (0x3D000000) or 1/4096.0
- **Structure offsets:** `LDR` with immediate offsets reveal data layout

### Phase 3: Validate Hypothesis

Test decoded values against known data:
1. Extract stroke from SDOCX using current extractor
2. Decode using hypothesized format
3. Calculate span (max - min) of decoded points
4. Compare to bounding box from object header
5. Error should be < 1 pixel for correct decoding

### Phase 4: Update Implementation

When updating `sdocx_extractor.py`:
1. Modify the decoder function (`_decode_samsung_fixed5_5`)
2. Verify X/Y order in delta stream
3. Check for termination markers
4. Run full extraction test

## Current Format Knowledge

### 5.5 Fixed-Point Encoding (for X/Y deltas)
```
16-bit word:
Bit 15:   Sign (1=negative)
Bits 10-14: Unused (cleared)
Bits 5-9:  Integer part (0-31)
Bits 0-4:  Fractional part (/32.0)
```

### Stroke Payload Layout

The payload has **two header variants**, detected by checking bytes 16-31:

**Variant A (Standard)** - bytes 16-31 contain data:
```
Offset 0-15:  Header (timestamp, page dimensions 1440x4072)
Offset 16-31: Additional metadata (non-zero)
Offset 34:    uint32 point_count
Offset 60:    Delta stream (dX:uint16, dY:uint16 pairs)
```

**Variant B (Padded)** - bytes 16-31 are all zeros:
```
Offset 0-15:  Header (timestamp, page dimensions)
Offset 16-31: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ← Padding
Offset 50:    uint32 point_count (shifted +16)
Offset 76:    Delta stream (shifted +16)
```

**Hex dump examples:**

Variant A (standard):
```
     0: b0 f7 d0 04 ab 40 06 00 a0 05 00 00 e8 0f 00 00
    16: 72 0a 00 00 01 00 56 0a 00 00 02 25 04 04 8e 25  ← Non-zero
    32: 00 00 d9 00 00 00 ...
           ^^^^^ point_count=217 at offset 34
```

Variant B (padded):
```
     0: 53 c8 4a 59 0b 3a 06 00 a0 05 00 00 e8 0f 00 00
    16: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ← All zeros
    32: e2 06 00 00 01 00 c6 06 00 00 02 25 04 04 8e 25
    48: 00 00 8d 00 00 00 ...
           ^^^^^ point_count=141 at offset 50
```

**Detection code:**
```python
has_padding = all(b == 0 for b in payload[16:32])
point_count_offset = 50 if has_padding else 34
delta_offset = 76 if has_padding else 60
```

Last 2 points: Termination marker (large +Y delta like +25.0) - trim these

### Debugging Stroke Parsing Issues

If strokes render incorrectly (zigzag patterns, wrong scale):

1. **Check error ratio**: Compare decoded span to bounding box
   ```python
   xs = [p[0] for p in points]
   ys = [p[1] for p in points]
   span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
   expected_x, expected_y = bbox.right - bbox.left, bbox.bottom - bbox.top
   ratio_x, ratio_y = span_x / expected_x, span_y / expected_y
   # Should be ~1.0, if 2-10x then offsets are wrong
   ```

2. **Dump payload bytes 16-31** to detect variant:
   ```python
   print(payload[16:32].hex())  # All zeros = Variant B
   ```

3. **Verify point_count is reasonable** (usually 50-500, not 65536)

## Commands

Run extractor: `python3 sdocx_extractor.py sdocxFiles/ThisIsTheTitle_251009_042302.sdocx`
Generate SVG: `python3 plot_strokes.py`

## Task: $ARGUMENTS
