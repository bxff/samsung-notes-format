#!/usr/bin/env python3
"""
Generate SVG visualization of extracted strokes from Samsung Notes .sdocx file.

Usage:
    python3 plot_strokes.py [sdocx_file]

If no file is provided, uses the default test file.
"""

import json
import subprocess
import sys
import os


def extract_strokes(sdocx_path: str) -> dict:
    """Run sdocx_extractor.py and return parsed JSON."""
    result = subprocess.run(
        ["python3", "sdocx_extractor.py", sdocx_path],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
    )
    if result.returncode != 0:
        print(f"Error extracting: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def iter_objects(objects: list):
    """Recursively iterate through objects including container children."""
    for obj in objects:
        yield obj
        if obj.get("children"):
            yield from iter_objects(obj["children"])


def generate_svg(data: dict, output_path: str = "output_strokes.svg") -> bool:
    """Generate SVG from extracted stroke data. Returns True on success."""
    if not data.get("pages"):
        print("Error: No pages found in SDOCX file", file=sys.stderr)
        return False

    page = data["pages"][0]
    width = page["width"]
    height = page["height"]

    svg_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        '  <rect fill="white" width="100%" height="100%"/>',
        f'  <rect fill="none" stroke="#ccc" stroke-width="1" x="0" y="0" width="{width}" height="{height}"/>',
    ]

    colors = ["#0066cc", "#cc0066", "#00cc66", "#cc6600", "#6600cc", "#00cccc"]
    stroke_idx = 0

    for layer in page["layers"]:
        for obj in iter_objects(layer["objects"]):
            if obj["object_type"] in [1, 15] and obj.get("stroke_points"):
                points = obj["stroke_points"]
                color = colors[stroke_idx % len(colors)]

                # Create path from points
                if len(points) >= 2:
                    path_data = f"M {points[0][0]:.2f},{points[0][1]:.2f}"
                    for p in points[1:]:
                        path_data += f" L {p[0]:.2f},{p[1]:.2f}"

                    svg_lines.append(
                        f'  <path d="{path_data}" fill="none" stroke="{color}" '
                        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
                    )

                # Add bounding box overlay (dashed)
                bbox = obj["bounding_rect"]
                bw = bbox["right"] - bbox["left"]
                bh = bbox["bottom"] - bbox["top"]
                svg_lines.append(
                    f'  <rect x="{bbox["left"]:.2f}" y="{bbox["top"]:.2f}" '
                    f'width="{bw:.2f}" height="{bh:.2f}" '
                    f'fill="none" stroke="{color}" stroke-width="0.5" '
                    f'stroke-dasharray="4" opacity="0.3"/>'
                )

                stroke_idx += 1

    svg_lines.append("</svg>")

    with open(output_path, "w") as f:
        f.write("\n".join(svg_lines))

    print(f"SVG written to: {output_path}")
    print(f"Page size: {width} x {height}")
    print(f"Strokes extracted: {stroke_idx}")
    return True


def generate_png(data: dict, output_path: str = "stroke_points_plot.png") -> bool:
    """Generate PNG using matplotlib (if available). Returns True on success."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches
    except ImportError:
        print("matplotlib not available, skipping PNG generation")
        return True  # Not a failure, just skipped

    if not data.get("pages"):
        print("Error: No pages found in SDOCX file", file=sys.stderr)
        return False

    page = data["pages"][0]
    width = page["width"]
    height = page["height"]

    fig, ax = plt.subplots(1, 1, figsize=(10, 12))

    colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD"]
    stroke_idx = 0

    for layer in page["layers"]:
        for obj in iter_objects(layer["objects"]):
            if obj["object_type"] in [1, 15] and obj.get("stroke_points"):
                points = obj["stroke_points"]
                color = colors[stroke_idx % len(colors)]

                # Plot stroke path
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                ax.plot(xs, ys, color=color, linewidth=2, alpha=0.8)

                # Plot bounding box
                bbox = obj["bounding_rect"]
                rect = patches.Rectangle(
                    (bbox["left"], bbox["top"]),
                    bbox["right"] - bbox["left"],
                    bbox["bottom"] - bbox["top"],
                    linewidth=1,
                    edgecolor=color,
                    facecolor="none",
                    linestyle="--",
                    alpha=0.5,
                )
                ax.add_patch(rect)

                # Label
                ax.text(
                    bbox["left"],
                    bbox["top"] - 10,
                    f"Stroke {stroke_idx + 1}",
                    fontsize=8,
                    color=color,
                )

                stroke_idx += 1

    ax.set_xlim(0, width)
    ax.set_ylim(height, 0)  # Flip Y axis
    ax.set_xlabel("X Position (pixels)")
    ax.set_ylabel("Y Position (pixels)")
    ax.set_title(f"Extracted Strokes ({stroke_idx} strokes)")
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.set_aspect("equal")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"PNG written to: {output_path}")
    return True


def main():
    # Default test file
    default_file = "sdocxFiles/ThisIsTheTitle_251009_042302.sdocx"

    if len(sys.argv) > 1:
        sdocx_path = sys.argv[1]
    else:
        sdocx_path = default_file

    if not os.path.exists(sdocx_path):
        print(f"Error: File not found: {sdocx_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting strokes from: {sdocx_path}")
    data = extract_strokes(sdocx_path)

    # Generate outputs
    svg_ok = generate_svg(data)
    png_ok = generate_png(data)

    if not svg_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
