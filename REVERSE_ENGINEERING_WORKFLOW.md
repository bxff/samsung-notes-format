# Reverse Engineering Workflow: Samsung Notes SDOCX Format

This document outlines the workflow for reverse engineering the Samsung Notes `.sdocx` file format by analyzing the native library `libSPenModel.so`.

## Prerequisites

### Tools Required
- **Ghidra** (NSA reverse engineering tool) - Free, excellent for ARM64 analysis
- **IDA Pro** or **Binary Ninja** - Alternative disassemblers
- **Python 3** - For testing and validation scripts
- **Hex editor** - For examining raw binary data (e.g., HxD, xxd)

### Files Location
```
decompiled_source/resources/lib/arm64-v8a/libSPenModel.so  # Primary target
decompiled_source/sources/j0/p.java                        # Java wrapper (ObjectStroke)
sdocxFiles/*.sdocx                                         # Test files
```

---

## Phase 1: Identify Target Functions

### 1.1 Export Analysis
List all exported symbols to find relevant function names:

```bash
# Using nm or objdump
nm -D libSPenModel.so | grep -i stroke
nm -D libSPenModel.so | grep -i restore
nm -D libSPenModel.so | grep -i delta
nm -D libSPenModel.so | grep -i float
```

### 1.2 Key Functions to Target
Based on our analysis, these are the critical functions:

| Function | Address | Purpose |
|----------|---------|---------|
| `sm_RestoreStroke` | 0x2f62b0 | Main stroke data restoration |
| `sm_ShortToFloatDelta` | 0x2f8638 | Scalar delta decoding (3.12 format) |
| SIMD block | 0x2f6790-0x2f6870 | Vector delta decoding (5.5 format) |

### 1.3 String References
Search for strings that indicate data handling:

```bash
strings libSPenModel.so | grep -i point
strings libSPenModel.so | grep -i stroke
strings libSPenModel.so | grep -i delta
```

---

## Phase 2: Disassembly Analysis

### 2.1 Load in Ghidra
1. Create new project
2. Import `libSPenModel.so` (ARM64/AARCH64)
3. Run auto-analysis
4. Navigate to target functions

### 2.2 Identify Encoding Patterns

#### Look for Fixed-Point Conversion
Fixed-point decoding typically involves:
- **Bit masking**: `AND` instructions with constants like `0x1F`, `0xFFF`
- **Bit shifting**: `LSR`, `ASR`, `UBFX` instructions
- **Float conversion**: `SCVTF` (signed convert to float)
- **Scaling**: `FMUL` with constants like `1/32.0`, `1/4096.0`

#### Example: 5.5 Fixed-Point (SIMD)
```asm
movi v0.2s, #0x1f             ; mask = 0x1F (5 bits)
movi v1.2s, #0x3d, lsl #24    ; scale = 0.03125 (1/32)
and  v3.8b, v2.8b, v0.8b      ; fractional = value & 0x1F
ushr v4.2s, v2.2s, #0x5       ; integer = value >> 5
scvtf v3.2s, v3.2s            ; convert to float
fmul v3.2s, v3.2s, v1.2s      ; frac = frac * (1/32)
fadd v3.2s, v3.2s, v4.2s      ; result = int + frac
```

#### Example: 3.12 Fixed-Point (Scalar)
```asm
ubfx  w8, w0, #12, #3         ; integer_part = (value >> 12) & 0x7
and   w9, w0, #0xfff          ; fractional_part = value & 0xFFF
scvtf s0, w9, #12             ; frac_float = fractional_part / 4096.0
```

### 2.3 Identify Data Layout

#### Look for Structure Offsets
```asm
ldr   w8, [x0, #0x22]         ; offset 34 (0x22) = point_count
ldr   s0, [x0, #0x28]         ; offset 40 = start_x (float)
ldr   s1, [x0, #0x30]         ; offset 48 = start_y (float)
```

#### Loop Patterns
Delta decompression typically has a loop structure:
```asm
loop:
    ldrh  w8, [x1], #2        ; load uint16, advance pointer
    ; ... decode delta ...
    subs  w9, w9, #1          ; decrement counter
    b.ne  loop                ; continue if not zero
```

---

## Phase 3: Hypothesis Formation

### 3.1 Document Observations
Create a table of observed patterns:

| Offset | Size | Observed Values | Hypothesis |
|--------|------|-----------------|------------|
| 0 | 4 | Varies | Header/flags |
| 34 | 4 | 217, 373, 194 | Point count |
| 60 | 4*N | Delta stream | X/Y pairs |

### 3.2 Cross-Reference with Java Code
Check `j0/p.java` (ObjectStroke) for:
- Field names and their purposes
- Constants (e.g., `f391Z = 12` = header size)
- Method signatures that hint at data layout

---

## Phase 4: Validation Testing

### 4.1 Create Test Script
```python
import struct

def decode_5_5(word: int) -> float:
    """Decode 5.5 fixed-point format."""
    fractional = word & 0x1F
    integer = (word >> 5) & 0x1F
    result = integer + (fractional / 32.0)
    if word & 0x8000:
        result = -result
    return result

# Test with known values from hex dump
test_value = 0x003b  # From actual stroke data
print(f"Decoded: {decode_5_5(test_value)}")
```

### 4.2 Compare Against Known Results
1. Extract stroke from SDOCX
2. Decode using hypothesis
3. Calculate span (max - min)
4. Compare to bounding box from object header

```python
# Validation check
bbox_width = obj['bounding_rect']['right'] - obj['bounding_rect']['left']
calculated_width = max(xs) - min(xs)
error = abs(bbox_width - calculated_width)
print(f"Error: {error:.2f} pixels")  # Should be < 1.0
```

### 4.3 Iterate on Failures
If validation fails:
1. Check byte order (little-endian vs big-endian)
2. Check X/Y order (may be swapped)
3. Check offset alignment (try +2 or +4)
4. Look for termination markers

---

## Phase 5: Document Findings

### 5.1 Final Data Structure
```
Stroke Payload Structure:
Offset 0-33:   Header/metadata
Offset 34-37:  Point count (uint32)
Offset 38-59:  Additional metadata
Offset 60+:    Delta stream
  - Each delta: 4 bytes (dX:uint16, dY:uint16)
  - Encoding: 5.5 fixed-point
  - Last 2 points: termination marker (+12.0 Y delta)
```

### 5.2 Encoding Format
```
5.5 Fixed-Point Format:
┌─────────┬───────────┬───────────┬──────────────┐
│ Bit 15  │  10-14    │   5-9     │    0-4       │
├─────────┼───────────┼───────────┼──────────────┤
│ Sign    │ Unused    │ Integer   │ Fractional   │
│ (1=neg) │           │ (0-31)    │ (/32.0)      │
└─────────┴───────────┴───────────┴──────────────┘
```

---

## Common Pitfalls

### 1. Multiple Code Paths
The library may have different code paths:
- **SIMD path**: For X/Y coordinate pairs (uses 5.5 format)
- **Scalar path**: For individual values like pressure (uses 3.12 format)

Always check which path is actually used for your target data.

### 2. Termination Markers
Samsung uses special values to mark end of data:
- Look for sudden large deltas (e.g., +12.0)
- Duplicate trailing points
- Trim these from final output

### 3. Coordinate Systems
- Points may be relative (deltas from previous)
- Start point may be at a different offset
- Bounding box may include stroke width/pen radius

### 4. Endianness
ARM64 is typically little-endian, but verify:
```python
# Little-endian (correct for ARM64)
value = struct.unpack('<H', data)[0]

# Big-endian (wrong, but try if results are off)
value = struct.unpack('>H', data)[0]
```

---

## Quick Reference: ARM64 Instructions

| Instruction | Meaning |
|-------------|---------|
| `UBFX Wd, Wn, #lsb, #width` | Extract unsigned bitfield |
| `AND Wd, Wn, #imm` | Bitwise AND |
| `LSR Wd, Wn, #shift` | Logical shift right |
| `SCVTF Sd, Wn` | Signed int to float |
| `FMUL Sd, Sn, Sm` | Float multiply |
| `FADD Sd, Sn, Sm` | Float add |
| `MOVI Vd.T, #imm` | Move immediate to vector |
| `USHR Vd.T, Vn.T, #shift` | Vector unsigned shift right |

---

## Workflow Summary

```
1. IDENTIFY → Find relevant functions via exports/strings
2. DISASSEMBLE → Analyze in Ghidra, focus on bit operations
3. HYPOTHESIZE → Form theory about data format
4. VALIDATE → Test against real data with known bounding boxes
5. ITERATE → Adjust hypothesis based on errors
6. DOCUMENT → Record final format for implementation
```
