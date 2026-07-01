"""The object record inside a .page file, as a byte-layout diagram (ret2 style).

This is the structure the decompiled Java reader (j0.b) walks: a fixed header of
typed fields, then (at the variable-data offset) the stroke payload the rest of
the post decodes. The object carries more attribute fields between the two, but
the reader reaches the payload through the offset field, so the figure follows
that jump rather than listing attributes that differ between format variants.
"""
import lib

# (type label, field label). Order matches the j0.b read sequence.
HEADER = [
    ("int32", "total size"),
    ("int16", "data type  (0)"),
    ("int32", "offset to variable data"),
    ("byte", "flag length"),
    ("int16", "flags"),
    ("byte", "field length"),
    ("int32", "field flags"),
    ("int32", "format version"),
    ("string", "UUID  (length + UTF-8)"),
    ("int64", "modified time"),
    ("f64 x4", "bounding box  (left, top, right, bottom)"),
    ("int32", "timestamp"),
    ("byte", "resizable"),
]
# the stroke payload, found by following the variable-data offset above
PAYLOAD = [
    ("int32", "point count"),
    ("f64 x2", "start point  (x, y)"),
]
DELTA = ("u16 x2 x N", "delta stream:  (dx, dy) per point")

RH = 27          # row height
LW = 96          # left (type) column width
RW = 332         # right (field) column width
X0, Y0 = 24, 52
GAP = 46         # space the offset arrow spans, between header and payload
MONO = lib.MONO

W = X0 + LW + RW + 26
S = lib.svg_open(W, 200)

S.append(lib.text(X0, 24, "one object in a .page file", size=12))
S.append(lib.text(X0, 40, "fields in the order the Java reader pulls them", size=11))


def row(y, t, f, weight=0.8):
    S.append(f'<rect x="{X0}" y="{y}" width="{LW}" height="{RH}" fill="none" stroke="#000" stroke-width="{weight}"/>')
    S.append(f'<rect x="{X0+LW}" y="{y}" width="{RW}" height="{RH}" fill="none" stroke="#000" stroke-width="{weight}"/>')
    S.append(lib.text(X0 + 10, y + RH / 2 + 4, t, size=11))
    S.append(lib.text(X0 + LW + 12, y + RH / 2 + 4, f, size=11))


y = Y0
offset_row_y = None
for t, f in HEADER:
    row(y, t, f)
    if f.startswith("offset to variable data"):
        offset_row_y = y + RH / 2
    y += RH

header_bottom = y
payload_top = y + GAP

# arrow from the "offset to variable data" field down to the payload group,
# tracing how the reader jumps past the in-between attributes
ax = X0 + LW + RW + 12
S.append(f'<line x1="{X0+LW+RW}" y1="{offset_row_y:.0f}" x2="{ax}" y2="{offset_row_y:.0f}" stroke="#000" stroke-width="0.7"/>')
S.append(f'<line x1="{ax}" y1="{offset_row_y:.0f}" x2="{ax}" y2="{payload_top+RH/2:.0f}" stroke="#000" stroke-width="0.7"/>')
S.append(f'<line x1="{ax}" y1="{payload_top+RH/2:.0f}" x2="{X0+LW+RW+3}" y2="{payload_top+RH/2:.0f}" stroke="#000" stroke-width="0.7"/>')
# arrowhead
S.append(f'<path d="M {X0+LW+RW+3} {payload_top+RH/2:.0f} l 6 -3 l 0 6 z" fill="#000"/>')

S.append(lib.text(X0, payload_top - 8, "stroke payload", size=11))
y = payload_top
for t, f in PAYLOAD:
    row(y, t, f)
    y += RH
row(y, DELTA[0], DELTA[1], weight=1.4)
y += RH

cap_y = y + 26
S.append(lib.text(X0, cap_y, "the header comes straight off the decompiled Java; the offset field jumps"))
S.append(lib.text(X0, cap_y + 14, "past the object's attributes to the delta stream the rest of this post decodes."))

H = cap_y + 22
S[0] = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H:.0f}" '
        f'width="{W}" height="{H:.0f}" fill="none">')
print(lib.write(S, "object.svg"), f"({W}x{H:.0f})")
