#!/usr/bin/env python3
"""
Generate SVG visualization of extracted strokes from Samsung Notes .sdocx files.

Usage:
    python3 plot_strokes.py [options] [sdocx_file...]

Options:
    --all           Process all .sdocx files in sdocxFiles/ directory
    --output-dir    Output directory for generated files (default: current dir)
    --no-bbox       Don't draw bounding boxes
    --show-rows     Overlay ruled-line row bands (debug; same grid as G-code stroke reordering)
    --stroke-width  Stroke width in pixels (default: 2)

Examples:
    python3 plot_strokes.py                                    # Process default test file
    python3 plot_strokes.py --all                              # Process all files in sdocxFiles/
    python3 plot_strokes.py file1.sdocx file2.sdocx            # Process specific files
    python3 plot_strokes.py --output-dir=output/ --all         # Output to specific directory
"""

import sys
import os
import argparse
from pathlib import Path


from typing import Optional


def extract_strokes(sdocx_path: str) -> Optional[dict]:
    """Parse .sdocx and return extracted data dict."""
    try:
        from sdocx_extractor import extract_to_dict

        return extract_to_dict(sdocx_path)
    except Exception as e:
        print(f"Error extracting {sdocx_path}: {e}", file=sys.stderr)
        return None


def iter_objects(objects: list):
    """Recursively iterate through objects including container children."""
    for obj in objects:
        yield obj
        if obj.get("children"):
            yield from iter_objects(obj["children"])


def _append_row_debug_overlay(
    svg_lines: list[str],
    page: dict,
    width: float,
    height: float,
    *,
    row_height_scale: float | None = None,
) -> None:
    """Draw bands + dashed lines for ruled-line row clusters (see ``row_cluster_indices_for_page``)."""
    try:
        from sdocx_gcode import (
            collect_stroke_polys_and_bboxes_px_for_page,
            row_cluster_indices_for_page,
            uniform_row_pitch_px_for_page,
        )
    except ImportError as e:
        print(f"Warning: row overlay needs sdocx_gcode: {e}", file=sys.stderr)
        return

    clusters = row_cluster_indices_for_page(
        page, row_height_scale=row_height_scale
    )
    _, boxes = collect_stroke_polys_and_bboxes_px_for_page(page)
    if not clusters:
        return
    pitch = uniform_row_pitch_px_for_page(
        page, row_height_scale=row_height_scale
    )
    colors = [
        "#ff4d00",
        "#00a86b",
        "#6b2cff",
        "#c200c2",
        "#0088cc",
        "#cc5500",
        "#b38f00",
        "#006ecd",
    ]
    svg_lines.append(
        '  <g id="writing-order-rows" pointer-events="none" shape-rendering="crispEdges">'
    )
    for ri, idxs in enumerate(clusters):
        yc = sum(0.5 * (boxes[i][1] + boxes[i][3]) for i in idxs) / len(idxs)
        y0 = yc - 0.5 * pitch
        c = colors[ri % len(colors)]
        svg_lines.append(
            f'    <rect x="0" y="{y0:.2f}" width="{width}" height="{pitch:.2f}" '
            f'fill="{c}" opacity="0.08"/>'
        )
        svg_lines.append(
            f'    <line x1="0" y1="{yc:.2f}" x2="{width}" y2="{yc:.2f}" '
            f'stroke="{c}" stroke-width="1.25" stroke-dasharray="12 6" opacity="0.92"/>'
        )
        label_y = min(yc + 4.0, height - 4.0, y0 + pitch - 2.0)
        svg_lines.append(
            f'    <text x="8" y="{label_y:.2f}" font-size="11" '
            f'font-family="Helvetica,Arial,sans-serif" fill="{c}" stroke="white" '
            f'stroke-width="0.35" paint-order="stroke">r{ri} ({len(idxs)})</text>'
        )
    svg_lines.append("  </g>")


def generate_svg(
    data: Optional[dict],
    output_path: str,
    show_bbox: bool = True,
    stroke_width: float = 2.0,
    stroke_color: Optional[str] = None,
    show_rows: bool = False,
    row_height_scale: float | None = None,
) -> bool:
    """Generate SVG from extracted stroke data. Returns True on success."""
    if not data or not data.get("pages"):
        print("Error: No pages found in SDOCX file", file=sys.stderr)
        return False

    page = data["pages"][0]
    width = page["width"]
    height = page["height"]
    title = data.get("metadata", {}).get("title", "Untitled")

    svg_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}">',
        f"  <!-- Title: {title} -->",
        f"  <!-- Generated from Samsung Notes .sdocx file -->",
        '  <rect fill="white" width="100%" height="100%"/>',
    ]

    if show_rows:
        _append_row_debug_overlay(
            svg_lines,
            page,
            float(width),
            float(height),
            row_height_scale=row_height_scale,
        )

    # Use single color if specified, otherwise cycle through palette
    colors = (
        ["#222222"]
        if stroke_color
        else [
            "#0066cc",
            "#cc0066",
            "#00cc66",
            "#cc6600",
            "#6600cc",
            "#00cccc",
            "#336699",
            "#993366",
            "#669933",
            "#996633",
            "#663399",
            "#339999",
        ]
    )
    stroke_idx = 0

    for layer in page["layers"]:
        for obj in iter_objects(layer["objects"]):
            if obj["object_type"] in [1, 15] and obj.get("stroke_points"):
                points = obj["stroke_points"]
                color = stroke_color or colors[stroke_idx % len(colors)]

                # Create path from points
                if len(points) >= 2:
                    path_data = f"M {points[0][0]:.2f},{points[0][1]:.2f}"
                    for p in points[1:]:
                        path_data += f" L {p[0]:.2f},{p[1]:.2f}"

                    svg_lines.append(
                        f'  <path d="{path_data}" fill="none" stroke="{color}" '
                        f'stroke-width="{stroke_width}" stroke-linecap="round" '
                        f'stroke-linejoin="round"/>'
                    )

                # Add bounding box overlay (dashed)
                if show_bbox:
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

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w") as f:
        f.write("\n".join(svg_lines))

    return True


def get_output_path(input_path: str, output_dir: str, extension: str) -> str:
    """Generate output path based on input filename."""
    base_name = Path(input_path).stem
    # Sanitize filename
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in base_name)
    return os.path.join(output_dir, f"{safe_name}{extension}")


def process_file(
    sdocx_path: str,
    output_dir: str,
    show_bbox: bool = True,
    stroke_width: float = 2.0,
    show_rows: bool = False,
    row_height_scale: float | None = None,
) -> bool:
    """Process a single SDOCX file and generate SVG."""
    print(f"\nProcessing: {sdocx_path}")

    data = extract_strokes(sdocx_path)
    if not data:
        return False

    title = data.get("metadata", {}).get("title", "Untitled")
    stroke_count = data.get("summary", {}).get("stroke_count", 0)
    page = data["pages"][0] if data.get("pages") else None

    if not page:
        print(f"  Error: No pages found", file=sys.stderr)
        return False

    print(f"  Title: {title}")
    print(f"  Size: {page['width']} x {page['height']}")
    print(f"  Strokes: {stroke_count}")

    # Generate SVG
    svg_path = get_output_path(sdocx_path, output_dir, ".svg")
    if generate_svg(
        data,
        svg_path,
        show_bbox=show_bbox,
        stroke_width=stroke_width,
        show_rows=show_rows,
        row_height_scale=row_height_scale,
    ):
        print(f"  SVG: {svg_path}")
        return True
    return False


def find_sdocx_files(directory: str) -> list:
    """Find all .sdocx files in directory."""
    files = []
    for f in os.listdir(directory):
        if f.endswith(".sdocx"):
            files.append(os.path.join(directory, f))
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(
        description="Generate SVG visualizations from Samsung Notes .sdocx files"
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="SDOCX files to process",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all .sdocx files in sdocxFiles/ directory",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Output directory for generated files (default: current directory)",
    )
    parser.add_argument(
        "--no-bbox",
        action="store_true",
        help="Don't draw bounding boxes",
    )
    parser.add_argument(
        "--stroke-width",
        type=float,
        default=2.0,
        help="Stroke width in pixels (default: 2)",
    )
    parser.add_argument(
        "--show-rows",
        action="store_true",
        help="Overlay ruled-line row bands (same grid as G-code stroke reordering)",
    )
    parser.add_argument(
        "--row-height-scale",
        type=float,
        default=None,
        metavar="S",
        help="Ruled row pitch multiplier for --show-rows (default: sdocx_gcode.RULED_LINE_ROW_HEIGHT_SCALE)",
    )

    args = parser.parse_args()

    # Determine which files to process
    files_to_process = []

    if args.all:
        sdocx_dir = os.path.join(os.path.dirname(__file__) or ".", "sdocxFiles")
        if os.path.isdir(sdocx_dir):
            files_to_process = find_sdocx_files(sdocx_dir)
        else:
            print(f"Error: Directory not found: {sdocx_dir}", file=sys.stderr)
            sys.exit(1)
    elif args.files:
        files_to_process = args.files
    else:
        # Default: process the test file
        default_file = os.path.join(
            os.path.dirname(__file__) or ".",
            "sdocxFiles",
            "ThisIsTheTitle_251009_042302.sdocx",
        )
        if os.path.exists(default_file):
            files_to_process = [default_file]
        else:
            print(
                "Error: No files specified and default file not found", file=sys.stderr
            )
            print("Usage: python3 plot_strokes.py [--all] [file1.sdocx ...]")
            sys.exit(1)

    if not files_to_process:
        print("No .sdocx files found to process", file=sys.stderr)
        sys.exit(1)

    print(f"Processing {len(files_to_process)} file(s)...")

    # Process each file
    success_count = 0
    for sdocx_path in files_to_process:
        if not os.path.exists(sdocx_path):
            print(f"Error: File not found: {sdocx_path}", file=sys.stderr)
            continue

        if process_file(
            sdocx_path,
            args.output_dir,
            show_bbox=not args.no_bbox,
            stroke_width=args.stroke_width,
            show_rows=args.show_rows,
            row_height_scale=args.row_height_scale,
        ):
            success_count += 1

    print(
        f"\nCompleted: {success_count}/{len(files_to_process)} files processed successfully"
    )

    if success_count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
