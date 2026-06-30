"""Validation grid across every test note: each stroke decoded and drawn in its
own stored box. Same idea as fig_grid, but pooled over all the sample files so
it matches the "86 strokes across five notes" number in the post.
"""
import glob
import math
import os
import lib

# skip a couple of walker strokes whose shape reads badly out of context
SKIP = {("Eg walker O(n^2) case_250527_190920.sdocx", 42)}

strokes = []
files = sorted(glob.glob(os.path.join(lib.ROOT, "sdocxFiles", "*.sdocx")))
for f in files:
    base = os.path.basename(f)
    for i, s in enumerate(lib.decode_strokes(f)):
        if (base, i) in SKIP:
            continue
        strokes.append(s)

n = len(strokes)
COLS = 10
ROWS = math.ceil(n / COLS)
CELL, PADC, MARGIN, LABELH = 70, 9, 16, 48
W = MARGIN * 2 + COLS * CELL
H = MARGIN + ROWS * CELL + LABELH

covs = [lib.coverage(s["points"], s["bbox"]) for s in strokes]
worst = min(covs)
med = sorted(covs)[len(covs) // 2]

S = lib.svg_open(W, H)
for i, s in enumerate(strokes):
    r, c = divmod(i, COLS)
    cx0, cy0 = MARGIN + c * CELL, MARGIN + r * CELL
    L, T, Rr, Bb = lib.bbox_tuple(s["bbox"])
    bw, bh = Rr - L, Bb - T
    sc = (CELL - 2 * PADC) / max(bw, bh, 1e-6)
    dw, dh = bw * sc, bh * sc
    ox, oy = cx0 + (CELL - dw) / 2, cy0 + (CELL - dh) / 2
    S.append(f'<rect x="{ox:.1f}" y="{oy:.1f}" width="{dw:.1f}" height="{dh:.1f}" '
             f'fill="none" stroke="#000" stroke-width="0.7"/>')
    d = "M " + " L ".join(f"{ox+(x-L)*sc:.1f},{oy+(y-T)*sc:.1f}" for x, y in s["points"])
    S.append(f'<path d="{d}" fill="none" stroke="#000" stroke-width="1.0" '
             f'stroke-linecap="round" stroke-linejoin="round"/>')

cy = MARGIN + ROWS * CELL + 14
S.append(lib.text(MARGIN, cy, "Strokes from all five test notes, each decoded and drawn in its stored box."))
S.append(lib.text(MARGIN, cy + 14, f"median fill {med:.0f}%, worst {worst:.1f}%. position is anchored, span is never scaled to fit."))
print(lib.write(S, "stroke_grid_all.svg"), f"{n} strokes, median {med:.1f}%, worst {worst:.1f}%")
