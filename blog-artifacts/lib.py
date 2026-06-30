"""Shared helpers for the blog figures.

Style follows musaab.io: black and white only, system + mono fonts, hairline
rules, no fills or decoration. Every figure is a standalone SVG.
"""
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONO = "ui-monospace,SFMono-Regular,Menlo,monospace"


def decode_strokes(sdocx_path):
    """Decode every stroke in a file with our extractor. Returns a list of
    {bbox, points}. `bbox` is (left, top, right, bottom)."""
    out = subprocess.run(
        ["python3", os.path.join(ROOT, "sdocx_extractor.py"), sdocx_path],
        capture_output=True, text=True, cwd=ROOT,
    )
    data = json.loads(out.stdout)
    strokes = []
    for page in data["pages"]:
        for layer in page["layers"]:
            for obj in layer["objects"]:
                pts = obj.get("stroke_points") or []
                if len(pts) < 2:
                    continue
                bb = obj["bounding_rect"]
                strokes.append({
                    "bbox": (bb["left"], bb["top"], bb["right"], bb["bottom"]),
                    "points": pts,
                })
    return strokes


def load_json(name):
    with open(os.path.join(os.path.dirname(__file__), "data", name)) as f:
        return json.load(f)


def coverage(points, bbox):
    """Worst-axis box fill: decoded span / stored box span, as a percentage."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    cx = (max(xs) - min(xs)) / bw * 100 if bw > 1 else 100.0
    cy = (max(ys) - min(ys)) / bh * 100 if bh > 1 else 100.0
    return min(cx, cy)


def svg_open(w, h):
    # Transparent background. Ink is currentColor; the style below sets that color
    # and flips it under prefers-color-scheme: dark, so the figure stays visible in
    # both light and dark mode even when loaded via <img> (which would otherwise
    # not inherit the page color).
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" '
        f'width="{w:.0f}" height="{h:.0f}" fill="none">',
        '<style>svg{color:#000}@media (prefers-color-scheme: dark){svg{color:#fff}}</style>',
    ]


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=11):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{MONO}" '
            f'font-size="{size}" fill="currentColor">{esc(s)}</text>')


def bbox_tuple(bb):
    """Accept a bbox as a (l,t,r,b) tuple/list or {left,top,right,bottom} dict."""
    if isinstance(bb, dict):
        return (bb["left"], bb["top"], bb["right"], bb["bottom"])
    return tuple(bb)


def write(svg, out_name):
    svg.append("</svg>")
    # all ink is currentColor so the figure follows the page in light/dark mode
    body = ("\n".join(svg)
            .replace('stroke="#000"', 'stroke="currentColor"')
            .replace('fill="#000"', 'fill="currentColor"'))
    path = os.path.join(os.path.dirname(__file__), "out", out_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(body)
    return path
