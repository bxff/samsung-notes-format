#!/usr/bin/env python3
"""Unified CLI: extract, gcode, inbox."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import replace
from pathlib import Path

from sdocx_extractor import extract_to_dict
from sdocx_gcode import (
    RULED_LINE_ROW_HEIGHT_SCALE,
    StrokeOrderTuning,
    collect_stroke_polys_and_bboxes_px_for_page,
    collect_strokes_mm_for_page,
    default_profile_path,
    load_extracted_json,
    pen_up_travel_xy_mm,
    row_cluster_indices_for_page,
    uniform_row_pitch_px_for_page,
    write_gcode_outputs,
)
from plot_strokes import generate_svg, get_output_path

# Default: sequential grid from MIN to MAX inclusive, step STEP (pen-up vs row_height_scale).
_DEFAULT_OPTIMIZE_RANGE = "0.8:2.5:0.1"

_DEFAULT_SWEEP_X_GAP = "0.35:0.65:0.05"
_DEFAULT_SWEEP_CHAIN_Y = "1.0:1.8:0.1"
_DEFAULT_SWEEP_CHAIN_BACK_X = "3.0:6.5:0.5"
_DEFAULT_SWEEP_INTRA_LINE = "0.95:1.30:0.05"
_DEFAULT_SWEEP_CARRIAGE = "1.0:2.2:0.1"


def _parse_optimize_range(spec: str) -> tuple[float, float, float]:
    parts = spec.strip().split(":")
    if len(parts) != 3:
        raise ValueError("expected MIN:MAX:STEP (e.g. 0.8:2.5:0.1)")
    lo, hi, step = float(parts[0]), float(parts[1]), float(parts[2])
    if step <= 0 or lo > hi:
        raise ValueError("need STEP > 0 and MIN <= MAX")
    return lo, hi, step


def _linear_scales(lo: float, hi: float, step: float) -> list[float]:
    scales: list[float] = []
    i = 0
    eps = max(1e-9, abs(step) * 1e-6)
    while True:
        v = lo + i * step
        if v > hi + eps:
            break
        scales.append(round(v, 6))
        i += 1
    return scales


def _total_pen_up_mm(
    pages: list[dict],
    *,
    width_mm: float,
    flip_y: bool,
    ox: float,
    oy: float,
    writing_order: bool,
    row_height_scale: float | None,
    stroke_order_tuning: StrokeOrderTuning | None = None,
) -> float:
    total = 0.0
    for page in pages:
        strokes = collect_strokes_mm_for_page(
            page,
            width_mm,
            flip_y,
            ox,
            oy,
            writing_order=writing_order,
            row_height_scale=row_height_scale,
            stroke_order_tuning=stroke_order_tuning,
        )
        travel, _ = pen_up_travel_xy_mm(strokes)
        total += travel
    return total


def _run_order_param_sweep(
    pages: list[dict],
    args: argparse.Namespace,
    *,
    field: str,
    title: str,
    lo: float,
    hi: float,
    step: float,
) -> None:
    candidates = _linear_scales(lo, hi, step)
    if not candidates:
        return
    base = StrokeOrderTuning()
    print(
        f"\n# sweep {title}  (pages={len(pages)}  sequential {lo:g}..{hi:g}  "
        f"step {step:g}  n={len(candidates)}; row_height_scale="
        f"{args.row_height_scale!r} other tuning=defaults)"
    )
    print(f"# {field:24}  total_pen_up_mm")
    results: list[tuple[float, float]] = []
    for v in candidates:
        t = replace(base, **{field: v})
        tot = _total_pen_up_mm(
            pages,
            width_mm=args.width_mm,
            flip_y=args.flip_y,
            ox=args.offset_x,
            oy=args.offset_y,
            writing_order=args.writing_order,
            row_height_scale=args.row_height_scale,
            stroke_order_tuning=t,
        )
        results.append((v, tot))
        print(f"  {v:22.6g}  {tot:10.2f}")
    best_v, best_tot = min(results, key=lambda x: (x[1], x[0]))
    print(f"\nbest {field} = {best_v:g}  total_pen_up_mm = {best_tot:.2f}")


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
            row_height_scale=args.row_height_scale,
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
                row_height_scale=args.row_height_scale,
            )
            log_lines.append("OK gcode -> " + ", ".join(str(p) for p in paths))
            if args.also_svg:
                svg_path = get_output_path(str(sdocx), str(outbox_dir), ".svg")
                if generate_svg(
                    data,
                    svg_path,
                    show_bbox=not args.no_bbox,
                    show_rows=args.also_svg_rows,
                    row_height_scale=args.row_height_scale,
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
    p.add_argument(
        "--row-height-scale",
        type=float,
        default=None,
        metavar="S",
        help=(
            "Ruled-line row pitch multiplier for clustering / G-code / SVG rows "
            f"(default: {RULED_LINE_ROW_HEIGHT_SCALE} from sdocx_gcode)"
        ),
    )


def cmd_metrics(args: argparse.Namespace) -> int:
    try:
        data = _load_gcode_input(args)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 1
    pages = data.get("pages") or []
    if not pages:
        print("No pages in document", file=sys.stderr)
        return 1

    ran_optimize = False
    if getattr(args, "optimize_row_scale", None) is not None:
        ran_optimize = True
        try:
            lo, hi, step = _parse_optimize_range(str(args.optimize_row_scale))
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        candidates = _linear_scales(lo, hi, step)
        if not candidates:
            print("Error: empty scale range", file=sys.stderr)
            return 2
        if not args.writing_order:
            print(
                "Warning: --no-writing-order ignores row clustering; "
                "all scales give the same travel.",
                file=sys.stderr,
            )
        print(
            f"\n# optimize total pen_up_mm  (pages={len(pages)}  "
            f"sequential {lo:g}..{hi:g}  step {step:g}  n={len(candidates)})"
        )
        print("# scale  total_pen_up_mm  (increasing scale — dependency curve)")
        results: list[tuple[float, float]] = []
        for sc in candidates:
            tot = _total_pen_up_mm(
                pages,
                width_mm=args.width_mm,
                flip_y=args.flip_y,
                ox=args.offset_x,
                oy=args.offset_y,
                writing_order=args.writing_order,
                row_height_scale=sc,
                stroke_order_tuning=None,
            )
            results.append((sc, tot))
            print(f"  {sc:6.4g}  {tot:10.2f}")
        best_s, best_total = min(results, key=lambda t: (t[1], t[0]))
        print(f"\nbest row_height_scale = {best_s:g}")
        print(f"total_pen_up_mm       = {best_total:.2f}")
        print(
            f"\n# gcode: samsung-notes gcode NOTE.sdocx -o out.gcode "
            f"--row-height-scale {best_s:g}"
        )

    _ORDER_SWEEPS: list[tuple[str, str, str]] = [
        ("optimize_x_gap_factor", "x_gap_med_h_factor", "x_gap_med_h_factor"),
        ("optimize_chain_y_weight", "chain_y_weight", "chain_y_weight"),
        ("optimize_chain_back_x_weight", "chain_back_x_weight", "chain_back_x_weight"),
        (
            "optimize_intra_line_y_factor",
            "intra_line_y_slack_factor",
            "intra_line_y_slack_factor",
        ),
        (
            "optimize_carriage_y_lines",
            "carriage_y_extra_lines",
            "carriage_y_extra_lines",
        ),
    ]
    for arg_attr, field, title in _ORDER_SWEEPS:
        spec = getattr(args, arg_attr, None)
        if spec is None:
            continue
        if not args.writing_order:
            print(
                f"Warning: --no-writing-order skips stroke reordering; "
                f"{title} sweep is meaningless.",
                file=sys.stderr,
            )
            continue
        ran_optimize = True
        try:
            lo, hi, step = _parse_optimize_range(str(spec))
        except ValueError as e:
            print(f"Error ({arg_attr}): {e}", file=sys.stderr)
            return 2
        _run_order_param_sweep(
            pages,
            args,
            field=field,
            title=title,
            lo=lo,
            hi=hi,
            step=step,
        )

    if ran_optimize:
        return 0

    if getattr(args, "sweep_row_scale", None):
        scales: list[float | None] = [float(s) for s in args.sweep_row_scale]
    elif args.row_height_scale is not None:
        scales = [args.row_height_scale]
    else:
        scales = [None]

    grand_travel = 0.0
    single_scale = len(scales) == 1

    for pi, page in enumerate(pages):
        polys, _ = collect_stroke_polys_and_bboxes_px_for_page(page)
        n_strokes = len(polys)
        mode = "reordered" if args.writing_order else "json-order"
        print(f"\n# page {pi + 1}/{len(pages)}  strokes={n_strokes}  {mode}")
        print(
            f"{'scale':>10} {'rows':>5} {'pitch_px':>10} {'pen_up_mm':>12} {'jumps':>6}"
        )
        for sc in scales:
            eff = float(RULED_LINE_ROW_HEIGHT_SCALE if sc is None else sc)
            strokes_s = collect_strokes_mm_for_page(
                page,
                args.width_mm,
                args.flip_y,
                args.offset_x,
                args.offset_y,
                writing_order=args.writing_order,
                row_height_scale=sc,
                stroke_order_tuning=None,
            )
            travel, jumps = pen_up_travel_xy_mm(strokes_s)
            if args.writing_order:
                rows = len(row_cluster_indices_for_page(page, row_height_scale=sc))
                pitch = uniform_row_pitch_px_for_page(page, row_height_scale=sc)
            else:
                rows = 0
                pitch = 0.0
            row_s = f"{rows:5d}" if args.writing_order else "    —"
            pitch_s = f"{pitch:10.2f}" if args.writing_order else "         —"
            lbl = "default" if sc is None else f"{eff:.4g}"
            print(f"{lbl:>10} {row_s} {pitch_s} {travel:12.2f} {jumps:6d}")
            if single_scale:
                grand_travel += travel

    if len(pages) > 1 and single_scale:
        print(f"\n# total pen_up_mm (all pages): {grand_travel:.2f}")
    return 0


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

    p_me = sub.add_parser(
        "metrics",
        help="Pen-up XY travel: row-scale and/or StrokeOrderTuning sweeps, or per-page tables",
    )
    p_me.add_argument(
        "sdocx",
        nargs="?",
        default=None,
        help="Path to .sdocx (omit if using --from-json)",
    )
    p_me.add_argument(
        "--from-json",
        metavar="FILE",
        help="Use extracted JSON instead of parsing .sdocx",
    )
    me_x = p_me.add_mutually_exclusive_group()
    me_x.add_argument(
        "--sweep-row-scale",
        nargs="+",
        type=float,
        metavar="S",
        help="Print a table for each listed scale (overrides a single --row-height-scale)",
    )
    me_x.add_argument(
        "--optimize-row-scale",
        nargs="?",
        const=_DEFAULT_OPTIMIZE_RANGE,
        default=None,
        metavar="MIN:MAX:STEP",
        help=(
            "Walk row-height-scale from MIN to MAX by STEP; print total pen-up mm per "
            "value (increasing scale), then the minimum. Default if flag alone: "
            f"{_DEFAULT_OPTIMIZE_RANGE}"
        ),
    )
    _add_gcode_flags(p_me)
    p_me.add_argument(
        "--optimize-x-gap-factor",
        nargs="?",
        const=_DEFAULT_SWEEP_X_GAP,
        default=None,
        metavar="MIN:MAX:STEP",
        help=(
            "Sweep x_gap_med_h_factor (word bands); default range if flag alone: "
            f"{_DEFAULT_SWEEP_X_GAP}"
        ),
    )
    p_me.add_argument(
        "--optimize-chain-y-weight",
        nargs="?",
        const=_DEFAULT_SWEEP_CHAIN_Y,
        default=None,
        metavar="MIN:MAX:STEP",
        help=(
            "Sweep chain_y_weight; default range if flag alone: "
            f"{_DEFAULT_SWEEP_CHAIN_Y}"
        ),
    )
    p_me.add_argument(
        "--optimize-chain-back-x-weight",
        nargs="?",
        const=_DEFAULT_SWEEP_CHAIN_BACK_X,
        default=None,
        metavar="MIN:MAX:STEP",
        help=(
            "Sweep chain_back_x_weight; default range if flag alone: "
            f"{_DEFAULT_SWEEP_CHAIN_BACK_X}"
        ),
    )
    p_me.add_argument(
        "--optimize-intra-line-y-factor",
        nargs="?",
        const=_DEFAULT_SWEEP_INTRA_LINE,
        default=None,
        metavar="MIN:MAX:STEP",
        help=(
            "Sweep intra_line_y_slack_factor; default range if flag alone: "
            f"{_DEFAULT_SWEEP_INTRA_LINE}"
        ),
    )
    p_me.add_argument(
        "--optimize-carriage-y-lines",
        nargs="?",
        const=_DEFAULT_SWEEP_CARRIAGE,
        default=None,
        metavar="MIN:MAX:STEP",
        help=(
            "Sweep carriage_y_extra_lines; default range if flag alone: "
            f"{_DEFAULT_SWEEP_CARRIAGE}"
        ),
    )
    p_me.set_defaults(func=cmd_metrics)

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
