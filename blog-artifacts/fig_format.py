"""The 16-bit X/Y delta word as a plain bit-field, for the decoder section.
Magnitude = (word & 0x7FFF) / 32: five fractional bits, ten integer, sign in
bit 15. No comparison here; the low-byte misread lives in fig_bitlayout.
"""
import lib

WORD = 0x180          # +12 px example: integer 12 (bits 8 and 7), fraction 0
bits = [(WORD >> (15 - i)) & 1 for i in range(16)]

CW, CH = 34, 42
X0, Y0 = 28, 74
MONO = lib.MONO
W = X0 + 16 * CW + 40
S = lib.svg_open(W, 300)


def cell_x(b):
    return X0 + (15 - b) * CW


def bracket(b_hi, b_lo, y, label, sub=None):
    x1, x2 = cell_x(b_hi), cell_x(b_lo) + CW
    S.append(f'<line x1="{x1}" y1="{y}" x2="{x1}" y2="{y-6}" stroke="#000" stroke-width="1"/>')
    S.append(f'<line x1="{x2}" y1="{y}" x2="{x2}" y2="{y-6}" stroke="#000" stroke-width="1"/>')
    S.append(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="#000" stroke-width="1"/>')
    S.append(lib.text(x1, y + 16, label, size=12))
    if sub:
        S.append(lib.text(x1, y + 31, sub, size=12))


S.append(lib.text(X0, 26, "16-bit X/Y delta word", size=13))
S.append(lib.text(X0, 42, "example: a +12 px step, word = 0x0180", size=11))

for i in range(16):
    b = 15 - i
    x = X0 + i * CW
    S.append(lib.text(x + CW / 2 - 4, Y0 - 8, str(b), size=11))
    S.append(f'<rect x="{x}" y="{Y0}" width="{CW}" height="{CH}" fill="none" stroke="#000" stroke-width="1"/>')
    val = bits[i]
    weight = "700" if val else "400"
    S.append(f'<text x="{x+CW/2:.0f}" y="{Y0+CH/2+7:.0f}" font-family="{MONO}" font-size="19" '
             f'font-weight="{weight}" text-anchor="middle" fill="#000">{val}</text>')

fy = Y0 + CH + 22
bracket(15, 15, fy, "sign")
bracket(14, 5, fy, "integer (10 bits)")
bracket(4, 0, fy, "fraction")

ry = fy + 64
bracket(14, 0, ry, "magnitude = low 15 bits", "(word & 0x7FFF) / 32  =  384 / 32  =  12.00 px")

ny = ry + 56
S.append(lib.text(X0, ny, "five fractional bits and ten integer, so a coordinate delta is"))
S.append(lib.text(X0, ny + 15, "integer + fraction/32, with bit 15 as the sign."))

H = ny + 28
S[0] = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" fill="none">')
print(lib.write(S, "format.svg"), f"({W}x{H})")
