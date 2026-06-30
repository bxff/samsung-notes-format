"""Single stroke, two decodes overlapped in its stored bounding box (portrait).

solid  = our full-word decode, low 15 bits / 32 (fills the box)
dashed = twangodev/sdocx's low-byte decode (undershoots)

The "twangodev/sdocx" path is their real published crate's output, cached in
data/. Nothing here reimplements their decoder. The post displays this at the
column width, so its on-page size is set there, not by SCALE.
"""
import lib

mine = lib.load_json("thisistitle_mine.json")[2]
theirs = lib.load_json("thisistitle_twangodev.json")[2]
bb = lib.bbox_tuple(mine["bbox"])
L, T, R, B = bb
SCALE, PADX, HEAD = 0.42, 26, 40

bw, bh = (R - L) * SCALE, (B - T) * SCALE
box_x, box_y = PADX, HEAD


def path_d(pts):
    return "M " + " L ".join(f"{(x-L)*SCALE+box_x:.1f},{(y-T)*SCALE+box_y:.1f}" for x, y in pts)


cm = lib.coverage(mine["points"], bb)
ct = lib.coverage(theirs["points"], bb)

# trim the low-byte path where it stalls (it piles up repeated points at the end)
tp = theirs["points"]
term_i = max(range(len(tp)), key=lambda i: tp[i][1])
theirs_trim = tp[:term_i + 1]
dash_y = box_y + (tp[term_i][1] - T) * SCALE

col_x = box_x + bw + 30
W, H = col_x + 200, box_y + bh + 18
S = lib.svg_open(W, H)

S.append(lib.text(box_x, 16, "bounding box, stored in the file"))
S.append(lib.text(box_x, 30, "a faithful decode lands inside it"))
S.append(f'<rect x="{box_x:.1f}" y="{box_y:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
         f'fill="none" stroke="#000" stroke-width="1"/>')

# hatch the region the low-byte decode never reaches
gap_top, gap_bot = dash_y, box_y + bh
x_lo, x_hi = box_x, box_x + bw
def clip(c):
    pts = []
    for x in (x_lo, x_hi):
        y = x + c
        if gap_top <= y <= gap_bot:
            pts.append((x, y))
    for y in (gap_top, gap_bot):
        x = y - c
        if x_lo <= x <= x_hi:
            pts.append((x, y))
    pts = sorted(set((round(a, 2), round(b, 2)) for a, b in pts))
    return (pts[0], pts[-1]) if len(pts) >= 2 else None
c = gap_top - x_hi
while c <= gap_bot - x_lo:
    seg = clip(c)
    if seg:
        (x1, y1), (x2, y2) = seg
        S.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#000" stroke-width="0.3"/>')
    c += 9

S.append(f'<path d="{path_d(mine["points"])}" fill="none" stroke="#000" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>')
S.append(f'<path d="{path_d(theirs_trim)}" fill="none" stroke="#000" stroke-width="1.7" stroke-dasharray="4 3" stroke-linecap="round" stroke-linejoin="round"/>')
S.append(f'<line x1="{box_x:.1f}" y1="{dash_y:.1f}" x2="{box_x+bw:.1f}" y2="{dash_y:.1f}" stroke="#000" stroke-width="0.7" stroke-dasharray="2 3"/>')


def key(y, dashed, lines):
    style = 'stroke-dasharray="4 3"' if dashed else ''
    S.append(f'<line x1="{col_x}" y1="{y-4:.1f}" x2="{col_x+20}" y2="{y-4:.1f}" stroke="#000" stroke-width="1.7" {style}/>')
    S.append(lib.text(col_x + 28, y, lines[0], size=12))
    for i, ln in enumerate(lines[1:], 1):
        S.append(lib.text(col_x + 28, y + 14 * i, ln))


key(box_y + 30, False, ["full word", "low 15 bits / 32", f"fills the box ({cm:.1f}%)"])
key(dash_y - 8, True, ["low byte only", "low 8 bits / 32", f"dies at {ct:.0f}%", "(twangodev/sdocx)"])

# caption baked in at the bottom
cap = ["One real stroke, decoded both ways in its box.",
       "The full word fills it; the low byte stalls at 76%."]
cap_y = box_y + bh + 24
for i, ln in enumerate(cap):
    S.append(lib.text(box_x, cap_y + i * 14, ln))
W = max(W, int(box_x + max(len(l) for l in cap) * 6.7 + box_x))
H = cap_y + (len(cap) - 1) * 14 + 8
S[0] = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H:.0f}" '
        f'width="{W}" height="{H:.0f}" fill="none">')

print(lib.write(S, "coverage.svg"), f"full={cm:.1f}% lowbyte={ct:.1f}%  ({W}x{H:.0f})")
