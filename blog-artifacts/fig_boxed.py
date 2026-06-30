"""Every stroke in a note, drawn with its stored bounding box.

Drawing each decoded stroke inside its own box is the check that caught a real
anchoring bug: a couple of strokes sat outside their boxes because the alignment
min was taken over the (discarded) terminator point. They fit now.

Usage: python3 fig_boxed.py "<file>.sdocx" out_name.svg
"""
import sys
import lib

src = sys.argv[1] if len(sys.argv) > 1 else "sdocxFiles/Mako OT N problem still exists_251002_005645 (1).sdocx"
out = sys.argv[2] if len(sys.argv) > 2 else "mako_boxed.svg"

strokes = lib.decode_strokes(src)
allp = [p for s in strokes for p in s["points"]]
xs = [p[0] for p in allp]
ys = [p[1] for p in allp]
minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
PAD, SC = 24, 2.2
W = (maxx - minx) * SC + 2 * PAD
H = (maxy - miny) * SC + 2 * PAD


def X(x):
    return PAD + (x - minx) * SC


def Y(y):
    return PAD + (y - miny) * SC


S = lib.svg_open(W, H)
outside = 0
for s in strokes:
    L, T, R, B = s["bbox"]
    S.append(f'<rect x="{X(L):.1f}" y="{Y(T):.1f}" width="{(R-L)*SC:.1f}" '
             f'height="{(B-T)*SC:.1f}" fill="none" stroke="#000" stroke-width="0.6"/>')
    d = " ".join((("M" if k == 0 else "L") + f"{X(x):.1f},{Y(y):.1f}")
                 for k, (x, y) in enumerate(s["points"]))
    S.append(f'<path d="{d}" fill="none" stroke="#000" stroke-width="1.3" '
             f'stroke-linecap="round" stroke-linejoin="round"/>')
    for x, y in s["points"]:
        if x < L - 1 or x > R + 1 or y < T - 1 or y > B + 1:
            outside += 1
            break

print(lib.write(S, out), f"{len(strokes)} strokes, {outside} outside their box")
