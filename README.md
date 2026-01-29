# Samsung Notes SDOCX Format - Reverse Engineering & Extraction

## Overview

This project documents the reverse engineering of Samsung Notes `.sdocx` files and provides a Python extraction tool that parses handwritten stroke data with accurate coordinates.

**Status:** Stroke extraction is working with sub-pixel accuracy.

---

## Quick Start

```bash
# Extract strokes to JSON
python3 sdocx_extractor.py <path_to_sdocx>

# Generate SVG visualization
python3 sdocx_extractor.py file.sdocx | python3 -c "
import json, sys
data = json.load(sys.stdin)
# ... generates output_strokes.svg
"
```

---

## 1. File Format Discovery

### SDOCX Archive Structure

Samsung Notes `.sdocx` files are ZIP archives containing:

```
├── note.note           # Note metadata (title, dimensions, timestamps)
├── pageIdInfo.dat      # Page UUID list with hashes
├── <uuid>.page         # Page content (layers, objects)
├── media/
│   ├── mediaInfo.dat   # Media file registry
│   └── *.spi           # Stroke Point Image files
└── end_tag.bin         # Archive terminator
```

### Key SDK Classes Analyzed

From the decompiled Samsung Notes SDK:

| Class | Purpose |
|-------|---------|
| `T.q` | Little-Endian I/O utilities |
| `g0.h` | `note.note` parser (WNote) |
| `g0.u` | `.page` parser (Page) |
| `g0.C1316b` | Layer structure |
| `j0.b` | Object base class |
| `j0.p` | Stroke object |
| `k0.x` | UUID parser (UTF-8) |

### Native Library Analysis

The key to accurate stroke extraction was reverse engineering `libSPenModel.so`:

| Function | Address | Purpose |
|----------|---------|---------|
| `sm_RestoreStroke` | 0x2f62b0 | Main stroke data restoration |
| `sm_ShortToFloatDelta` | 0x2f8638 | Scalar delta decoding (3.12 format) |
| SIMD block | 0x2f6790-0x2f6870 | Vector delta decoding (**5.5 format**) |

See [REVERSE_ENGINEERING_WORKFLOW.md](REVERSE_ENGINEERING_WORKFLOW.md) for the complete methodology.

---

## 2. Binary Format Details

### I/O Primitives (from `T.q`)

| Method | Type | Bytes |
|--------|------|-------|
| `T.q.P()` | int32 | 4 |
| `T.q.Q()` | int64 | 8 |
| `T.q.S()` | short | 2 |
| `T.q.U()` | UTF-16LE string | 2 + len*2 |

### Object Header Structure (from `j0.b.l()`)

```
┌─────────────────────────┐
│ int32: total_size       │
│ short: data_type (=0)   │
│ int32: var_data_offset  │
│ byte: flag_byte_len     │
│ short: flags            │
│ [padding...]            │
│ byte: field_byte_len    │
│ int32: field_flags      │
│ int32: format_version   │
├─────────────────────────┤
│ UUID (UTF-8):           │
│   short: length         │
│   bytes: utf8_chars     │
├─────────────────────────┤
│ int64: modified_time    │
│ 4 doubles: bounding_rect│
│   left, top, right, bot │
│ int32: timestamp        │
│ byte: resizable         │
├─────────────────────────┤
│ [stroke binary data...] │
└─────────────────────────┘
```

### Stroke Payload Structure (from native library analysis)

```
┌─────────────────────────┐
│ @ Offset 34:            │
│   uint32: point_count   │
├─────────────────────────┤
│ @ Offset 60:            │
│   [Packed XY Deltas...] │
│   stride: 4 bytes       │
│     uint16: dX          │
│     uint16: dY          │
└─────────────────────────┘
```

### 5.5 Fixed-Point Delta Encoding

Discovered by disassembling the SIMD code path in `sm_RestoreStroke` at offset `0x2f6790` in `libSPenModel.so`.

#### ARM64 Assembly Evidence

```asm
; From libSPenModel.so @ 0x2f6790-0x2f6870 (SIMD delta decoding)
movi v0.2s, #0x1f             ; mask = 0x1F (5 bits for fractional)
movi v1.2s, #0x3d, lsl #24    ; scale = 0.03125 (1/32 in IEEE 754)
...
and  v3.8b, v2.8b, v0.8b      ; fractional = value & 0x1F
ushr v4.2s, v2.2s, #0x5       ; integer = value >> 5
bic  v4.2s, #0x4, lsl #8      ; clear bit 10 (mask to 5 bits)
scvtf v3.2s, v3.2s            ; convert fractional to float
scvtf v4.2s, v4.2s            ; convert integer to float
fmul v3.2s, v3.2s, v1.2s      ; frac = frac * (1/32)
fadd v3.2s, v3.2s, v4.2s      ; result = integer + fractional
```

The key insights from this assembly:
1. `movi v0.2s, #0x1f` - Mask is 0x1F (5 bits), not 0xFFF (12 bits)
2. `movi v1.2s, #0x3d, lsl #24` - Scale factor is 0x3D000000 = 0.03125 = 1/32
3. `ushr v4.2s, v2.2s, #0x5` - Integer part is shifted by 5, not 12
4. This is a **5.5 format**, not the 3.12 format used in the scalar `sm_ShortToFloatDelta`

#### Bit Layout

```
16-bit word layout:
┌─────────┬───────────┬───────────┬──────────────┐
│ Bit 15  │  10-14    │   5-9     │    0-4       │
├─────────┼───────────┼───────────┼──────────────┤
│ Sign    │ Unused    │ Integer   │ Fractional   │
│ (1=neg) │ (cleared) │ (5 bits)  │ (5 bits)     │
│         │           │ range 0-31│ /32.0        │
└─────────┴───────────┴───────────┴──────────────┘
```

#### Python Decoding Implementation

```python
def decode_5_5(word: int) -> float:
    fractional = word & 0x1F           # bits 0-4
    integer = (word >> 5) & 0x1F       # bits 5-9
    result = integer + (fractional / 32.0)
    if word & 0x8000:                  # sign bit
        result = -result
    return result
```

#### Important Notes

- **Two code paths exist**: The scalar `sm_ShortToFloatDelta` uses 3.12 format, but the SIMD path (used for X/Y pairs) uses 5.5 format
- Last 2 points are a termination marker (+12.0 Y delta) and should be trimmed
- Coordinates are deltas that accumulate from (0, 0)
- Final points are aligned to the object's bounding box

---

## 3. Verification Results

### Test File: `ThisIsTheTitle_251009_042302.sdocx`

| Field | Value |
|-------|-------|
| Title | `ThisIsTheTitle` |
| Page UUID | `243e1166-a480-11f0-906e-2f736af9493c` |
| Dimensions | 1440 × 4072 |
| Format Version | 4000 |
| Layer Count | 1 |
| Stroke Count | **3** |

### Extraction Accuracy

| Stroke | BBox Size | Calculated Span | Width Error | Height Error |
|--------|-----------|-----------------|-------------|--------------|
| 0 | 37.12 × 684.34 | 37.12 × 683.75 | **0.01 px** | **0.59 px** |
| 1 | 38.13 × 652.09 | 38.16 × 652.09 | **0.02 px** | **0.00 px** |
| 2 | 67.34 × 573.19 | 66.94 × 569.53 | **0.40 px** | **3.66 px** |

Sub-pixel accuracy achieved for stroke extraction.

---

## 4. Usage

### Basic Extraction

```bash
python3 sdocx_extractor.py <path_to_sdocx>
```

### Output Format

```json
{
  "metadata": { "title": "...", "width": 1440, "height": 4072 },
  "page_ids": ["uuid1", "uuid2"],
  "pages": [
    {
      "uuid": "...",
      "layers": [
        {
          "objects": [
            {
              "object_type": 1,
              "object_type_name": "Stroke",
              "uuid": "...",
              "bounding_rect": { "left": 602.8, "top": 309.2, ... },
              "stroke_points": [ [602.8, 309.2], [602.8, 311.0], ... ]
            }
          ]
        }
      ]
    }
  ],
  "summary": { "stroke_count": 3 }
}
```

### Generate SVG

```bash
python3 plot_strokes.py
# Creates: output_strokes.svg
```

---

## 5. Project Files

| File | Purpose |
|------|---------|
| `sdocx_extractor.py` | Main extraction tool |
| `plot_strokes.py` | Generate SVG/PNG visualizations |
| `REVERSE_ENGINEERING_WORKFLOW.md` | Detailed RE methodology |
| `sdocxFiles/` | Test SDOCX files |
| `decompiled_source/` | Decompiled SDK and native libraries |

---

## 6. Future Work

- [x] Parse stroke point data from binary
- [x] Accurate coordinate extraction (5.5 fixed-point)
- [x] SVG export
- [ ] Implement `.spi` file parsing for rendered strokes
- [ ] Add `mediaInfo.dat` parser
- [ ] Support text box content extraction
- [ ] PDF export with handwriting

---

## License

This project is for educational and research purposes. Samsung Notes is a trademark of Samsung Electronics.
