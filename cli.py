#!/usr/bin/env python3
"""Unified CLI: extract, gcode, inbox."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from sdocx_extractor import extract_to_dict
from sdocx_gcode import (
    default_profile_path,
    load_extracted_json,
    write_gcode_outputs,
)
from plot_strokes import generate_svg, get_output_path


def cmd_extract(args: argparse.Namespace) -> int:
    if not Path(args.sdocx).is_file():
        print(f"Error: not a file: {args.sdocx}", file=sys.stderr)
        return 1
    try:
        data = extract_to_dict(args.sdocx)
        text = json.dumps(data, indent=2, ensure_ascii=False)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        else:
            print(text)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1
    return 0


def _load_gcode_input(args: argparse.Namespace) -> dict:
    if args.from_json:
        jp = Path(args.from_json)
        if not jp.is_file():
            raise SystemExit(f"Not a file: {jp}")
        return load_extracted_json(jp)
    if not args.sdocx:
        raise SystemExit("Provide a .sdocx path or --from-json")
    if not Path(args.sdocx).is_file():
        raise SystemExit(f"Not a file: {args.sdocx}")
    return extract_to_dict(args.sdocx)


def cmd_gcode(args: argparse.Namespace) -> int:
    try:
        data = _load_gcode_input(args)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 1

    profile = Path(args.profile) if args.profile else default_profile_path()
    if not profile.is_file():
        print(f"Error: profile not found: {profile}", file=sys.stderr)
        return 1

    out = Path(args.out)
    try:
        paths = write_gcode_outputs(
            data,
            profile,
            out,
            width_mm=args.width_mm,
            flip_y=args.flip_y,
            offset_x_mm=args.offset_x,
            offset_y_mm=args.offset_y,
            page_pause_m0=not args.no_page_pause,
            one_file_per_page=args.one_file_per_page,
            writing_order=args.writing_order,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1

    for p in paths:
        print(p)
    return 0


def cmd_inbox(args: argparse.Namespace) -> int:
    inbox_dir = Path(args.inbox_dir)
    outbox_dir = Path(args.outbox_dir)
    err_dir = outbox_dir / "errors"
    outbox_dir.mkdir(parents=True, exist_ok=True)
    err_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(inbox_dir.glob("*.sdocx"))
    if not files:
        print(f"No .sdocx files in {inbox_dir}", file=sys.stderr)
        return 1

    profile = Path(args.profile) if args.profile else default_profile_path()
    ok = 0
    for sdocx in files:
        stem = sdocx.stem
        log_lines: list[str] = []
        try:
            data = extract_to_dict(str(sdocx))
            out_g = outbox_dir / f"{stem}.gcode"
            paths = write_gcode_outputs(
                data,
                profile,
                out_g,
                width_mm=args.width_mm,
                flip_y=args.flip_y,
                offset_x_mm=args.offset_x,
                offset_y_mm=args.offset_y,
                page_pause_m0=not args.no_page_pause,
                one_file_per_page=args.one_file_per_page,
                writing_order=args.writing_order,
            )
            log_lines.append("OK gcode -> " + ", ".join(str(p) for p in paths))
            if args.also_svg:
                svg_path = get_output_path(str(sdocx), str(outbox_dir), ".svg")
                if generate_svg(
                    data,
                    svg_path,
                    show_bbox=not args.no_bbox,
                    show_rows=args.also_svg_rows,
                ):
                    log_lines.append(f"OK svg -> {svg_path}")
                else:
                    log_lines.append("WARN: svg generation failed")
            ok += 1
        except Exception as e:
            log_lines.append(f"FAIL: {e}")
            traceback.print_exc()
            (err_dir / f"{stem}.log").write_text(
                "\n".join(log_lines) + "\n\n" + traceback.format_exc(),
                encoding="utf-8",
            )
            continue
        (outbox_dir / f"{stem}.log").write_text(
            "\n".join(log_lines) + "\n", encoding="utf-8"
        )

    print(f"Processed {ok}/{len(files)} file(s) into {outbox_dir}")
    return 0 if ok == len(files) else 1


def _add_gcode_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Machine profile TOML (default: bundled grbl_plotter_z.toml)",
    )
    p.add_argument(
        "--width-mm",
        type=float,
        default=120.0,
        help="Target drawing width in mm (height scales, default 120)",
    )
    p.add_argument(
        "--flip-y",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Mirror page Y when converting to mm (default: on; use --no-flip-y if the plot is upside down)",
    )
    p.add_argument("--offset-x", type=float, default=0.0, help="X offset in mm")
    p.add_argument("--offset-y", type=float, default=0.0, help="Y offset in mm")
    p.add_argument(
        "--no-page-pause",
        action="store_true",
        help="Do not insert M0 between pages (combined file only)",
    )
    p.add_argument(
        "--one-file-per-page",
        action="store_true",
        help="Write stem_p01.gcode, stem_p02.gcode, ...",
    )
    p.add_argument(
        "--writing-order",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reorder strokes for the plotter (default: on). Use --no-writing-order for JSON order.",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="samsung-notes",
        description="Samsung Notes .sdocx: extract JSON, GRBL G-code, inbox batch",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ex = sub.add_parser("extract", help="Extract .sdocx to JSON")
    p_ex.add_argument("sdocx", help="Path to .sdocx")
    p_ex.add_argument("-o", "--output", help="Write JSON to file instead of stdout")
    p_ex.set_defaults(func=cmd_extract)

    p_gc = sub.add_parser("gcode", help="Generate GRBL G-code from .sdocx or JSON")
    p_gc.add_argument(
        "sdocx",
        nargs="?",
        default=None,
        help="Path to .sdocx (omit if using --from-json)",
    )
    p_gc.add_argument(
        "--from-json",
        metavar="FILE",
        help="Use extracted JSON instead of parsing .sdocx",
    )
    p_gc.add_argument(
        "-o",
        "--out",
        required=True,
        help="Output .gcode path (or basename when --one-file-per-page)",
    )
    _add_gcode_flags(p_gc)
    p_gc.set_defaults(func=cmd_gcode)

    p_in = sub.add_parser(
        "inbox",
        help="Convert all inbox/*.sdocx to outbox/*.gcode",
    )
    p_in.add_argument(
        "--inbox-dir",
        default="inbox",
        help="Directory containing .sdocx (default: inbox)",
    )
    p_in.add_argument(
        "--outbox-dir",
        default="outbox",
        help="Output directory (default: outbox)",
    )
    p_in.add_argument(
        "--also-svg",
        action="store_true",
        help="Also write preview SVG per file",
    )
    p_in.add_argument(
        "--no-bbox",
        action="store_true",
        help="With --also-svg: do not draw bounding boxes",
    )
    p_in.add_argument(
        "--also-svg-rows",
        action="store_true",
        help="With --also-svg: overlay writing-order row bands (debug)",
    )
    _add_gcode_flags(p_in)
    p_in.set_defaults(func=cmd_inbox)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
