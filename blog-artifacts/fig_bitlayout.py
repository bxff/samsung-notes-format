"""The 16-bit coordinate-delta word as a bit-field diagram, ret2-style.

Same bytes, two readings: the full word uses the low 15 bits (/32); twangodev/
sdocx reads only the low byte and drops the integer bits 8-14. Worked on a real
value: a 12px delta (word 0x180) decodes to 12.0 vs 4.0.
"""
import lib

WORD = 0x180          # a +12px delta: integer 12 (bits 8 and 7), fraction 0
bits = [(WORD >> (15 - i)) & 1 for i in range(16)]  # left = bit 15

CW, CH = 34, 42       # cell size
X0, Y0 = 28, 74       # top-left of the cell row (clears the two title lines)
MONO = lib.MONO

W = X0 + 16 * CW + 40
S = lib.svg_open(W, 320)  # height set at the end via viewBox patch below


def cell_x(bit):  # bit number (0..15) -> x of its cell (bit 15 leftmost)
    return X0 + (15 - bit) * CW


def bracket(b_hi, b_lo, y, label, sub=None):
    x1 = cell_x(b_hi)
    x2 = cell_x(b_lo) + CW
    S.append(f'<line x1="{x1}" y1="{y}" x2="{x1}" y2="{y-6}" stroke="#000" stroke-width="1"/>')
    S.append(f'<line x1="{x2}" y1="{y}" x2="{x2}" y2="{y-6}" stroke="#000" stroke-width="1"/>')
    S.append(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="#000" stroke-width="1"/>')
    S.append(lib.text(x1, y + 16, label, size=12))
    if sub:
        S.append(lib.text(x1, y + 31, sub, size=12))


# title
S.append(lib.text(X0, 26, "16-bit X/Y delta word", size=13))
S.append(lib.text(X0, 42, "example: a +12 px step, word = 0x0180", size=11))

# bit-number labels + cells
for i in range(16):
    b = 15 - i
    x = X0 + i * CW
    S.append(lib.text(x + CW / 2 - 4, Y0 - 8, str(b), size=11))
    # mark the integer bits the low-byte read throws away (bits 8-14)
    if 8 <= b <= 14:
        for h in range(3, CH, 5):
            S.append(f'<line x1="{x}" y1="{Y0+h}" x2="{x+min(h,CW)}" y2="{Y0}" stroke="#000" stroke-width="0.5"/>')
    S.append(f'<rect x="{x}" y="{Y0}" width="{CW}" height="{CH}" fill="none" stroke="#000" stroke-width="1"/>')
    val = bits[i]
    weight = "700" if val else "400"
    S.append(f'<text x="{x+CW/2:.0f}" y="{Y0+CH/2+7:.0f}" font-family="{MONO}" font-size="19" '
             f'font-weight="{weight}" text-anchor="middle" fill="#000">{val}</text>')

# field labels under the cells
fy = Y0 + CH + 22
bracket(15, 15, fy, "sign")
bracket(14, 5, fy, "integer (10 bits)")
bracket(4, 0, fy, "fraction")

# the two readings, well separated
ry = fy + 70
bracket(14, 0, ry, "full word: low 15 bits / 32", "bits 0-14 = 384 / 32 = 12.00 px")
ry2 = ry + 64
bracket(7, 0, ry2, "low byte only (twangodev/sdocx)", "low byte = 128 / 32 = 4.00 px")

# close note
ny = ry2 + 56
S.append(lib.text(X0, ny, "the hatched bits 8-14 are the ones the low byte drops: any step >= 8 px", size=11))
S.append(lib.text(X0, ny + 15, "sets one of them, so a fast stroke (12 px here) wraps and reads short (4 px).", size=11))

# patch height
H = ny + 28
S[0] = S[0].replace('height="320"', f'height="{H}"').replace('viewBox="0 0 %d 320"' % W, f'viewBox="0 0 {W} {H}"')
# (viewBox uses the H passed to svg_open; rewrite it directly)
S[0] = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" fill="none">')

print(lib.write(S, "bitlayout.svg"))
