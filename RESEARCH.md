# Samsung Notes `.sdocx` format notes

Reverse-engineering notes for the handwriting in a Samsung Notes `.sdocx` file: how a page is laid out on disk and how a single pen stroke is decoded. The narrative version (how this was actually worked out, and where the other tool that reads this format gets the encoding wrong) is in the blog write-up; this file is the dry reference.

`render.py` is the clean, self-contained implementation of everything below. `sdocx_extractor.py` is the fuller extractor that dumps all metadata to JSON.

## Container

`.sdocx` is a ZIP:

```
note.note         note metadata (title, dimensions, timestamps)
pageIdInfo.dat    page UUID list
<uuid>.page       one per page: layers, objects, strokes
media/            mediaInfo.dat + thumbnails
end_tag.bin       archive terminator
```

All integers are little-endian. Strings are a `int16` length prefix followed by the text (UTF-16LE in the page reader, UTF-8 for object UUIDs).

## The `.page` reader

The layout was recovered by decompiling the Android app (jadx) and following the readers: a page reads its layers, a layer reads its objects, and each object reads itself out of a header. Strokes are a subclass of the base object. The class names in the decompile are single obfuscated letters and are specific to the build that was analysed (APK 4.4.37.13); they change on every release, so the structures below are the durable part, not the names.

### Object header

Read in order at the start of each object's binary blob:

```
int32    total size
int16    data type        (0)
int32    offset to variable data
byte     flag length
int16    flags             (+ (flag length - 2) more bytes)
byte     field length
int32    field flags
int32    format version
int16    UUID length       (+ UUID bytes, UTF-8)
int64    modified time
f64 x4   bounding box      (left, top, right, bottom)
int32    timestamp
byte     resizable
...      more object attributes
```

The bounding box is a real stored field (an Android `RectF`, named `rect` in the class's own debug dump), independent of the stroke geometry. It is the basis for the correctness check below. The "offset to variable data" field points past the remaining attributes to the stroke payload.

## Stroke payload

The payload has two variants, distinguished by whether bytes 16 to 31 are all zero:

```
                       standard      padded (16 zero bytes prepended)
point count  (uint32)  offset 34     offset 50
delta stream           offset 60     offset 76
```

The payload also carries the stroke's start point (two `f64`) that the native decoder seeds the first point from; the extractor here ignores it and anchors to the bounding box instead (see below), which gives the same result.

The delta stream is `(dx, dy)` pairs, one 16-bit word each, 4 bytes per point. The last two points are a terminator (a large jump) and are trimmed.

## Delta encoding

Each coordinate is a 16-bit word:

```
bit 15      sign (1 = negative)
bits 5-14   integer part (10 bits)
bits 0-4    fractional part (/ 32)

magnitude = (word & 0x7FFF) / 32
value     = -magnitude if (word & 0x8000) else magnitude
```

Points are deltas; accumulate them from the stroke's start.

This was read out of `libSPenModel.so` (the SPen SDK's native model library, which kept its C++ symbols). The exported deserializer is `SPen::ObjectStrokeBinaryHandler::sm_RestoreStroke`; the per-point decode is inline in its loop, in ARM NEON. The integer field is the whole run of bits 5 to 14, not five bits. The disassembly clears only the sign:

```asm
MOVI  V0.2S, #0x1F           ; fraction mask
MOVI  V1.2S, #0x3D, LSL#24   ; 0x3D000000 = 1/32
AND   V3.8B, V2.8B, V0.8B    ; frac = word & 0x1F
USHR  V4.2S, V2.2S, #5       ; word >> 5
BIC   V4.2S, #4, LSL#8       ; clear bit 10 only (the sign, after the shift)
FMUL  V3.2S, V3.2S, V1.2S    ; frac *= 1/32
FADD  V3.2S, V3.2S, V4.2S    ; magnitude = integer + frac
```

(There is also a scalar helper, `sm_ShortToFloatDelta`, that decodes a different 3.12 fixed-point split. It is reached through a vtable, not from `sm_RestoreStroke`, and is not the coordinate path.)

## Other channels

In the same loop, the pressure word decodes as 3.12 fixed-point: `(word & 0xFFF) / 4096 + ((word >> 12) & 7)`, sign in bit 15. The trailing per-point channels (pressure, tilt, etc.) and per-stroke color/width are present but only the geometry is decoded here.

## Checking against the box

The bounding box is measured independently of the deltas, so it makes an honest correctness check. Decode a stroke from `(0, 0)`, shift its top-left corner onto the box, and never scale it, so its size comes only from the decoded deltas. A stroke that fills its box decoded correctly.

Across 86 strokes in five notes the fill is a median of 100%, worst 96.7%.
