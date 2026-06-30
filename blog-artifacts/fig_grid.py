"""Validation grid: every stroke in a note, each scaled into a uniform cell and
drawn inside its own stored box. The decoded path fills the box. Translate-only
alignment, never scaled to fit.

Usage: python3 fig_grid.py "<file>.sdocx" out_name.svg
"""
import math
import sys
import lib

src = sys.argv[1] if len(sys.argv) > 1 else "sdocxFiles/Eg walker O(n^2) case_250527_190920.sdocx"
out = sys.argv[2] if len(sys.argv) > 2 else "walker_grid.svg"

strokes = lib.decode_strokes(src)
n = len(strokes)
COLS = 8
ROWS = math.ceil(n / COLS)
CELL, PADC, MARGIN, LABELH = 74, 10, 16, 48
W = MARGIN * 2 + COLS * CELL
H = MARGIN + ROWS * CELL + LABELH

covs = [lib.coverage(s["points"], s["bbox"]) for s in strokes]
worst = min(covs)
med = sorted(covs)[len(covs) // 2]

S = lib.svg_open(W, H)
for i, s in enumerate(strokes):
    r, c = divmod(i, COLS)
    cx0, cy0 = MARGIN + c * CELL, MARGIN + r * CELL
    L, T, Rr, Bb = s["bbox"]
    bw, bh = Rr - L, Bb - T
    sc = (CELL - 2 * PADC) / max(bw, bh, 1e-6)
    dw, dh = bw * sc, bh * sc
    ox, oy = cx0 + (CELL - dw) / 2, cy0 + (CELL - dh) / 2
    S.append(f'<rect x="{ox:.1f}" y="{oy:.1f}" width="{dw:.1f}" height="{dh:.1f}" '
             f'fill="none" stroke="#000" stroke-width="0.7"/>')
    d = "M " + " L ".join(f"{ox+(x-L)*sc:.1f},{oy+(y-T)*sc:.1f}" for x, y in s["points"])
    S.append(f'<path d="{d}" fill="none" stroke="#000" stroke-width="1.1" '
             f'stroke-linecap="round" stroke-linejoin="round"/>')

cy = MARGIN + ROWS * CELL + 14
S.append(lib.text(MARGIN, cy, f"{n} strokes from one note, each decoded and drawn in its stored box."))
S.append(lib.text(MARGIN, cy + 14, f"median fill {med:.0f}%, worst {worst:.1f}%. position is anchored, span is never scaled to fit."))
print(lib.write(S, out), f"{n} strokes, median {med:.1f}%, worst {worst:.1f}%")
