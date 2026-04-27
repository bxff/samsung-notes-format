#!/usr/bin/env python3
"""Samsung Notes extracted JSON / .sdocx → GRBL G-code (plotter, Z pen lift)."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from plot_strokes import iter_objects


def default_profile_path() -> Path:
    import importlib.resources as ir

    return Path(str(ir.files("samsung_notes_profiles") / "grbl_plotter_z.toml"))


def _nonempty_lines(block: str) -> list[str]:
    lines: list[str] = []
    for line in (block or "").splitlines():
        s = line.strip()
        if s:
            lines.append(s)
    return lines


def load_profile(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        raw = tomllib.load(f)
    travel = float(raw["travel_feed"])
    return {
        "preamble_lines": _nonempty_lines(str(raw.get("preamble", ""))),
        "postamble_lines": _nonempty_lines(str(raw.get("postamble", ""))),
        "pen_up_z": float(raw["pen_up_z"]),
        "pen_down_z": float(raw["pen_down_z"]),
        "travel_feed": travel,
        "draw_feed": float(raw["draw_feed"]),
        "z_feed": float(raw.get("z_feed", travel)),
    }


def load_extracted_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _px_to_mm(
    x_px: float,
    y_px: float,
    page_w: int,
    page_h: int,
    width_mm: float,
    flip_y: bool,
    offset_x_mm: float,
    offset_y_mm: float,
) -> tuple[float, float]:
    scale = width_mm / max(1, page_w)
    x_mm = offset_x_mm + x_px * scale
    if flip_y:
        y_mm = offset_y_mm + (page_h - y_px) * scale
    else:
        y_mm = offset_y_mm + y_px * scale
    return x_mm, y_mm


def collect_strokes_mm_for_page(
    page: dict[str, Any],
    width_mm: float,
    flip_y: bool,
    offset_x_mm: float,
    offset_y_mm: float,
) -> list[list[tuple[float, float]]]:
    pw = max(1, int(page.get("width") or 1))
    ph = max(1, int(page.get("height") or 1))
    out: list[list[tuple[float, float]]] = []
    for layer in page.get("layers") or []:
        for obj in iter_objects(layer.get("objects") or []):
            if obj.get("object_type") not in (1, 15):
                continue
            pts = obj.get("stroke_points") or []
            if len(pts) < 2:
                continue
            poly: list[tuple[float, float]] = []
            for p in pts:
                poly.append(
                    _px_to_mm(
                        float(p[0]),
                        float(p[1]),
                        pw,
                        ph,
                        width_mm,
                        flip_y,
                        offset_x_mm,
                        offset_y_mm,
                    )
                )
            out.append(poly)
    return out


def _emit_strokes(
    strokes: list[list[tuple[float, float]]], profile: dict[str, Any]
) -> list[str]:
    z_up = profile["pen_up_z"]
    z_down = profile["pen_down_z"]
    f_travel = profile["travel_feed"]
    f_draw = profile["draw_feed"]
    f_z = profile["z_feed"]
    lines: list[str] = []

    for poly in strokes:
        x0, y0 = poly[0]
        lines.append(f"G0 Z{z_up:.3f} F{f_z:.0f}")
        lines.append(f"G0 X{x0:.3f} Y{y0:.3f} F{f_travel:.0f}")
        lines.append(f"G1 Z{z_down:.3f} F{f_z:.0f}")
        for x, y in poly[1:]:
            lines.append(f"G1 X{x:.3f} Y{y:.3f} F{f_draw:.0f}")

    lines.append(f"G0 Z{z_up:.3f} F{f_z:.0f}")
    return lines


def build_page_gcode(
    page: dict[str, Any],
    page_index: int,
    page_count: int,
    profile: dict[str, Any],
    width_mm: float,
    flip_y: bool,
    offset_x_mm: float,
    offset_y_mm: float,
    include_preamble: bool,
    include_postamble: bool,
) -> str:
    pw = max(1, int(page.get("width") or 1))
    ph = max(1, int(page.get("height") or 1))
    strokes = collect_strokes_mm_for_page(
        page, width_mm, flip_y, offset_x_mm, offset_y_mm
    )
    chunks: list[str] = []
    chunks.append(f"( page {page_index + 1} / {page_count} )")
    chunks.append(f"( page pixels {pw} x {ph}, target width {width_mm:.3f} mm )")
    chunks.append(f"( strokes {len(strokes)} )")

    body_lines: list[str] = []
    if include_preamble:
        body_lines.extend(profile["preamble_lines"])
    body_lines.extend(_emit_strokes(strokes, profile))
    if include_postamble:
        body_lines.extend(profile["postamble_lines"])

    return "\n".join(chunks) + "\n" + "\n".join(body_lines) + "\n"


def build_combined_gcode(
    data: dict[str, Any],
    profile: dict[str, Any],
    width_mm: float,
    flip_y: bool,
    offset_x_mm: float,
    offset_y_mm: float,
    page_pause_m0: bool,
) -> str:
    pages = data.get("pages") or []
    if not pages:
        return ""

    n = len(pages)
    parts: list[str] = []
    parts.extend(profile["preamble_lines"])
    parts.append("")

    for i, page in enumerate(pages):
        pw = max(1, int(page.get("width") or 1))
        ph = max(1, int(page.get("height") or 1))
        strokes = collect_strokes_mm_for_page(
            page, width_mm, flip_y, offset_x_mm, offset_y_mm
        )
        parts.append(f"( page {i + 1} / {n} )")
        parts.append(f"( page pixels {pw} x {ph}, target width {width_mm:.3f} mm )")
        parts.append(f"( strokes {len(strokes)} )")
        parts.append("")
        parts.extend(_emit_strokes(strokes, profile))
        parts.append("")
        if page_pause_m0 and i < n - 1:
            parts.append("M0 ( pause — next page; resume in sender )")
            parts.append("")

    parts.extend(profile["postamble_lines"])
    return "\n".join(parts) + "\n"


def write_gcode_outputs(
    data: dict[str, Any],
    profile_path: Path,
    out_path: Path,
    *,
    width_mm: float,
    flip_y: bool,
    offset_x_mm: float,
    offset_y_mm: float,
    page_pause_m0: bool,
    one_file_per_page: bool,
) -> list[Path]:
    profile = load_profile(profile_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    if one_file_per_page:
        pages = data.get("pages") or []
        n = len(pages)
        stem = out_path.stem
        parent = out_path.parent
        suffix = out_path.suffix or ".gcode"
        for i, _page in enumerate(pages):
            chunk_path = parent / f"{stem}_p{i + 1:02d}{suffix}"
            text = build_page_gcode(
                pages[i],
                i,
                n,
                profile,
                width_mm,
                flip_y,
                offset_x_mm,
                offset_y_mm,
                include_preamble=True,
                include_postamble=True,
            )
            chunk_path.write_text(text, encoding="utf-8")
            written.append(chunk_path)
    else:
        text = build_combined_gcode(
            data,
            profile,
            width_mm,
            flip_y,
            offset_x_mm,
            offset_y_mm,
            page_pause_m0,
        )
        out_path.write_text(text, encoding="utf-8")
        written.append(out_path)
    return written
