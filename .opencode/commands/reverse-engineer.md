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
```
Offset 34: uint32 point_count
Offset 60: Delta stream (dX:uint16, dY:uint16 pairs)
Last 2 points: Termination marker (+12.0 Y delta) - trim these
```

## Commands

Run extractor: `python3 sdocx_extractor.py sdocxFiles/ThisIsTheTitle_251009_042302.sdocx`
Generate SVG: `python3 plot_strokes.py`

## Task: $ARGUMENTS
