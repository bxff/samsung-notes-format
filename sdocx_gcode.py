#!/usr/bin/env python3
"""Samsung Notes extracted JSON / .sdocx → GRBL G-code (plotter, Z pen lift)."""

from __future__ import annotations

import json
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plot_strokes import iter_objects

# After fitting the ruled grid, scale pitch (>1 = taller rows, wider SVG bands, fewer Y splits).
RULED_LINE_ROW_HEIGHT_SCALE = 1.1


@dataclass(frozen=True)
class StrokeOrderTuning:
    """Tunable ordering heuristics (defaults match historical hard-coded behavior)."""

    # Horizontal band split: gap_thresh = max(3 px, x_gap_med_h_factor * med_h).
    x_gap_med_h_factor: float = 0.48
    # Greedy chain: penalize vertical / backward-X pen-up moves.
    chain_y_weight: float = 1.35
    chain_back_x_weight: float = 4.5
    # intra_line_y_slack = max(intra_line_y_slack_min_px, intra_line_y_slack_factor * med_h).
    intra_line_y_slack_factor: float = 1.10
    intra_line_y_slack_min_px: float = 20.0
    # New row: target start Y ≈ prev_row_bottom + carriage_y_extra_lines * slack.
    carriage_y_extra_lines: float = 1.5


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


def pen_up_travel_xy_mm(
    strokes: list[list[tuple[float, float]]],
) -> tuple[float, int]:
    """Sum of Euclidean XY jumps between stroke end and next stroke start (pen-up travel).

    Matches the travel implied by ``_emit_strokes`` between consecutive polylines.
    Returns ``(total_mm, n_jumps)``; ``n_jumps`` is ``max(0, len(strokes) - 1)``.
    """
    if len(strokes) < 2:
        return 0.0, 0
    total = 0.0
    n = len(strokes)
    for i in range(n - 1):
        x0, y0 = strokes[i][-1]
        x1, y1 = strokes[i + 1][0]
        dx, dy = x1 - x0, y1 - y0
        total += (dx * dx + dy * dy) ** 0.5
    return total, n - 1


def _bbox_px(poly: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _orient_poly_left_to_right(
    poly: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Prefer stroke start left of end; nearly vertical → top-to-bottom in page px."""
    if len(poly) < 2:
        return poly
    x0, y0 = poly[0]
    x1, y1 = poly[-1]
    eps = 1e-6
    if abs(x1 - x0) > eps:
        if x1 < x0:
            return list(reversed(poly))
        return poly
    if y1 < y0:
        return list(reversed(poly))
    return poly


class _DSU:
    __slots__ = ("p",)

    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, x: int) -> int:
        p = self.p
        while p[x] != x:
            p[x] = p[p[x]]
            x = p[x]
        return x

    def union(self, a: int, b: int) -> None:
        pa, pb = self.find(a), self.find(b)
        if pa != pb:
            self.p[pa] = pb


def _vertical_overlap_px(
    ymin_a: float, ymax_a: float, ymin_b: float, ymax_b: float
) -> float:
    return max(0.0, min(ymax_a, ymax_b) - max(ymin_a, ymin_b))


def _shrink_y_interval(ymin: float, ymax: float, shrink: float) -> tuple[float, float]:
    """Trim top and bottom of a bbox by ``shrink × height`` (for overlap tests only).

    Long ascenders/descenders stay in the full rect for ``cy`` and weak links, but
    core overlap ignores thin tails so two tight text lines merge less often.
    """
    h = max(1e-3, ymax - ymin)
    d = shrink * h
    return ymin + d, ymax - d


def _max_gap_split_on_cy(
    items: list[tuple[int, float]],
    *,
    med_h: float,
) -> tuple[list[int], list[int]] | None:
    """Split at the largest gap between consecutive bbox mid-Y values (sorted).

    Tight double lines often show a **clear step** in mid-heights between rows; k-means
    on cy can mis-assign strokes whose centers sit between the two modes.

    Rejects splits where one side still spans a tall band of mid-Y (ascenders vs body
    vs descenders on the **same** ruled line would otherwise become two rows).
    """
    if len(items) < 4:
        return None
    sorted_items = sorted(items, key=lambda t: t[1])
    vals = [c for _, c in sorted_items]
    lo, hi = vals[0], vals[-1]
    span = hi - lo
    if span < 0.42 * med_h or span > 1.18 * med_h:
        return None
    gaps = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    k = max(range(len(gaps)), key=lambda i: gaps[i])
    max_gap = gaps[k]
    # Below ~0.22*med_h we skip (avoids splitting one line where letter mid-Ys drift).
    if max_gap < 0.22 * med_h:
        return None
    left = [sorted_items[i][0] for i in range(k + 1)]
    right = [sorted_items[i][0] for i in range(k + 1, len(sorted_items))]
    if len(left) < 2 or len(right) < 2:
        return None
    left_vals = [sorted_items[i][1] for i in range(k + 1)]
    right_vals = [sorted_items[i][1] for i in range(k + 1, len(sorted_items))]
    span_left = max(left_vals) - min(left_vals)
    span_right = max(right_vals) - min(right_vals)
    # Real adjacent rows: each side is a thin strip in cy. One handwriting line split
    # into asc/body leaves a "fat" group — do not cut.
    max_sub = 0.55 * med_h
    if span_left > max_sub or span_right > max_sub:
        return None
    return left, right


def _is_debris_stroke(bb: tuple[float, float, float, float], med_h: float) -> bool:
    """Small punctuation / dots: defer to end of row and chain by nearest start.

    Wide but short strokes (underlines) stay primary so they sort L→R with text.
    """
    lf, tp, rt, bt = bb
    w = max(1e-3, rt - lf)
    h = max(1e-3, bt - tp)
    if h >= 0.26 * med_h:
        return False
    if w >= 0.52 * med_h:
        return False
    return w < 0.42 * med_h and h < 0.26 * med_h


def _dist2_travel_weighted(
    px: float, py: float, sx: float, sy: float, *, y_weight: float
) -> float:
    dx, dy = sx - px, sy - py
    return dx * dx + (y_weight * dy) * (y_weight * dy)


def _travel_step_cost(
    px: float,
    py: float,
    sx: float,
    sy: float,
    *,
    y_weight: float,
    back_x_weight: float,
) -> float:
    """Cost from current pen-up ``(px,py)`` to next pen-down ``(sx,sy)``.

    ``back_x_weight`` penalizes moving left (wasted X on a plotter) while still
    allowing small backtracks for cursive.
    """
    base = _dist2_travel_weighted(px, py, sx, sy, y_weight=y_weight)
    back = max(0.0, px - sx)
    return base + back_x_weight * back * back


def _greedy_chain_pick_next(
    pool: set[int],
    oriented: list[list[tuple[float, float]]],
    px: float,
    py: float,
    *,
    y_weight: float,
    back_x_weight: float,
) -> int:
    def key_i(i: int) -> tuple[float, float, float]:
        sx, sy = oriented[i][0][0], oriented[i][0][1]
        c = _travel_step_cost(
            px, py, sx, sy, y_weight=y_weight, back_x_weight=back_x_weight
        )
        return (c, sx, sy)

    return min(pool, key=key_i)


def _chain_path_length(
    order: list[int],
    oriented: list[list[tuple[float, float]]],
    *,
    y_weight: float,
    back_x_weight: float,
) -> float:
    if len(order) <= 1:
        return 0.0
    tot = 0.0
    px, py = oriented[order[0]][-1]
    for i in order[1:]:
        sx, sy = oriented[i][0][0], oriented[i][0][1]
        tot += _travel_step_cost(
            px, py, sx, sy, y_weight=y_weight, back_x_weight=back_x_weight
        )
        px, py = oriented[i][-1]
    return tot


def _greedy_chain_best_of_seeds(
    indices: list[int],
    oriented: list[list[tuple[float, float]]],
    bboxes_px: list[tuple[float, float, float, float]],
    med_h: float,
    *,
    y_weight: float,
    back_x_weight: float,
    max_seed_trials: int = 5,
    prefer_start_y: float | None = None,
) -> list[int]:
    """Among strokes whose pen-down sits on the left margin, try a few starts; keep lowest travel cost.

    If ``prefer_start_y`` is set (e.g. after carriage return), seeds are ranked closer in Y first
    for equal X — mimicking dropping the pen on the next ruled line.
    """
    if len(indices) <= 1:
        return list(indices)
    min_x = min(oriented[i][0][0] for i in indices)
    margin = max(3.5, 0.14 * med_h)

    def _seed_sort_key(i: int) -> tuple[float, ...]:
        sx, sy = oriented[i][0][0], oriented[i][0][1]
        if prefer_start_y is not None:
            return (sx, abs(sy - prefer_start_y), sy, bboxes_px[i][0])
        return (sx, sy, bboxes_px[i][0])

    seeds = sorted(
        [i for i in indices if oriented[i][0][0] <= min_x + margin],
        key=_seed_sort_key,
    )[:max_seed_trials]
    best_order: list[int] | None = None
    best_len = float("inf")
    for seed in seeds:
        pool = set(indices)
        pool.remove(seed)
        px, py = oriented[seed][-1]
        tail: list[int] = []
        while pool:
            nxt = _greedy_chain_pick_next(
                pool, oriented, px, py,
                y_weight=y_weight, back_x_weight=back_x_weight,
            )
            tail.append(nxt)
            pool.remove(nxt)
            px, py = oriented[nxt][-1]
        cand = [seed] + tail
        ln = _chain_path_length(cand, oriented, y_weight=y_weight, back_x_weight=back_x_weight)
        if ln < best_len:
            best_len, best_order = ln, cand
    assert best_order is not None
    return best_order


def _order_row_indices_minimize_travel(
    idxs: list[int],
    oriented: list[list[tuple[float, float]]],
    bboxes_px: list[tuple[float, float, float, float]],
    med_h: float,
    *,
    chain_y_weight: float = 1.35,
    chain_back_x_weight: float = 4.5,
) -> list[int]:
    """Primary strokes: greedy travel chain with back-X penalty; try several left seeds.

    Tiny debris still follows via NN from the last primary endpoint.
    """
    if len(idxs) <= 1:
        return list(idxs)
    primary = [i for i in idxs if not _is_debris_stroke(bboxes_px[i], med_h)]
    debris = [i for i in idxs if _is_debris_stroke(bboxes_px[i], med_h)]
    if not primary:
        primary = list(idxs)
        debris = []
    y_w = chain_y_weight
    back_w = chain_back_x_weight
    out = _greedy_chain_best_of_seeds(
        primary,
        oriented,
        bboxes_px,
        med_h,
        y_weight=y_w,
        back_x_weight=back_w,
        max_seed_trials=5,
        prefer_start_y=None,
    )
    if not debris:
        return out
    px, py = oriented[out[-1]][-1]
    pool = set(debris)
    while pool:
        best = _greedy_chain_pick_next(
            pool, oriented, px, py, y_weight=y_w, back_x_weight=back_w,
        )
        out.append(best)
        pool.remove(best)
        px, py = oriented[best][-1]
    return out


def _cluster_row_primaries_by_x_gap(
    primary_idxs: list[int],
    bboxes_px: list[tuple[float, float, float, float]],
    med_h: float,
    *,
    gap_med_h_factor: float = 0.48,
) -> list[list[int]]:
    """Split primary strokes into left-to-right bands (word-ish) by bbox gaps on X."""
    if not primary_idxs:
        return []
    gap_thresh = max(3.0, gap_med_h_factor * med_h)
    sorted_i = sorted(primary_idxs, key=lambda i: (bboxes_px[i][0], bboxes_px[i][2]))
    groups: list[list[int]] = []
    cur = [sorted_i[0]]
    cur_r = bboxes_px[sorted_i[0]][2]
    for i in sorted_i[1:]:
        lf, _, rt, _ = bboxes_px[i]
        if lf - cur_r <= gap_thresh:
            cur.append(i)
            cur_r = max(cur_r, rt)
        else:
            groups.append(cur)
            cur = [i]
            cur_r = rt
    groups.append(cur)
    return groups


def _group_x_span(
    g: list[int], bboxes_px: list[tuple[float, float, float, float]]
) -> tuple[float, float]:
    lf = min(bboxes_px[i][0] for i in g)
    rt = max(bboxes_px[i][2] for i in g)
    return lf, rt


def _assign_debris_to_x_groups(
    debris: list[int],
    groups: list[list[int]],
    bboxes_px: list[tuple[float, float, float, float]],
) -> dict[int, list[int]]:
    """Map each X-group index to debris whose center-x sits closest to that group's span."""
    if not debris or not groups:
        return {}
    spans = [_group_x_span(g, bboxes_px) for g in groups]
    by_g: dict[int, list[int]] = {j: [] for j in range(len(groups))}

    def dist_to_span(cx: float, j: int) -> float:
        lo, hi = spans[j]
        if cx < lo:
            return lo - cx
        if cx > hi:
            return cx - hi
        return 0.0

    for d in debris:
        lf, _, rt, _ = bboxes_px[d]
        cx = 0.5 * (lf + rt)
        best_j = 0
        best_d = float("inf")
        for j in range(len(groups)):
            dd = dist_to_span(cx, j)
            if dd < best_d or (dd == best_d and j < best_j):
                best_d, best_j = dd, j
        by_g[best_j].append(d)
    for j in by_g:
        by_g[j].sort(key=lambda i: (bboxes_px[i][0], bboxes_px[i][1]))
    return by_g


def _chain_debris_from_last_index(
    debris: list[int],
    oriented: list[list[tuple[float, float]]],
    last_idx: int,
    *,
    y_weight: float,
    back_x_weight: float,
) -> list[int]:
    if not debris:
        return []
    px, py = oriented[last_idx][-1]
    pool = set(debris)
    out: list[int] = []
    while pool:
        best = _greedy_chain_pick_next(
            pool,
            oriented,
            px,
            py,
            y_weight=y_weight,
            back_x_weight=back_x_weight,
        )
        out.append(best)
        pool.remove(best)
        px, py = oriented[best][-1]
    return out


def _refine_row_clusters_by_cy(
    clusters: list[list[int]],
    cy: list[float],
    med_h: float,
) -> list[list[int]]:
    """Split clusters where sorted bbox mid-heights show a dominant vertical gap."""
    out: list[list[int]] = []
    for idxs in clusters:
        items = [(i, cy[i]) for i in idxs]
        split = _max_gap_split_on_cy(items, med_h=med_h)
        if split is None:
            out.append(idxs)
        else:
            a, b = split
            out.append(a)
            out.append(b)
    return out


def collect_stroke_polys_and_bboxes_px_for_page(
    page: dict[str, Any],
) -> tuple[list[list[tuple[float, float]]], list[tuple[float, float, float, float]]]:
    """Stroke polylines and axis-aligned bboxes (same rects as SVG when present)."""
    polys: list[list[tuple[float, float]]] = []
    boxes: list[tuple[float, float, float, float]] = []
    for layer in page.get("layers") or []:
        for obj in iter_objects(layer.get("objects") or []):
            if obj.get("object_type") not in (1, 15):
                continue
            pts = obj.get("stroke_points") or []
            if len(pts) < 2:
                continue
            poly = [(float(p[0]), float(p[1])) for p in pts]
            br = obj.get("bounding_rect") or {}
            lf = float(br.get("left", 0.0))
            tp = float(br.get("top", 0.0))
            rt = float(br.get("right", 0.0))
            bt = float(br.get("bottom", 0.0))
            if rt <= lf or bt <= tp:
                bb = _bbox_px(poly)
                lf, tp, rt, bt = bb[0], bb[1], bb[2], bb[3]
            polys.append(poly)
            boxes.append((lf, tp, rt, bt))
    return polys, boxes


def collect_strokes_px_for_page(page: dict[str, Any]) -> list[list[tuple[float, float]]]:
    """Stroke polylines in page pixel coordinates (same as JSON stroke_points)."""
    polys, _ = collect_stroke_polys_and_bboxes_px_for_page(page)
    return polys


def uniform_row_pitch_px_for_page(
    page: dict[str, Any],
    *,
    row_height_scale: float | None = None,
) -> float:
    """Ruled line spacing (px) for debug bands: same grid as stroke reordering."""
    _, boxes = collect_stroke_polys_and_bboxes_px_for_page(page)
    if not boxes:
        return 28.0
    heights = [max(1e-3, bb[3] - bb[1]) for bb in boxes]
    med_h = sorted(heights)[len(heights) // 2]
    y_mid = [_stroke_y_center_bbox_px(bb) for bb in boxes]
    pitch, _ = _ruled_pitch_offset_with_row_height_scale(
        y_mid, med_h, row_height_scale=row_height_scale
    )
    return float(pitch)


def ruled_line_grid_meta_for_page(
    page: dict[str, Any],
    *,
    row_height_scale: float | None = None,
) -> tuple[float, float, int, int] | None:
    """Pitch, offset, min_row_index, max_row_index (inclusive), including empty ruled rows.

    Row centers are ``offset + k * pitch``. Only defined when the page has strokes.
    """
    _, boxes = collect_stroke_polys_and_bboxes_px_for_page(page)
    if not boxes:
        return None
    heights = [max(1e-3, bb[3] - bb[1]) for bb in boxes]
    med_h = sorted(heights)[len(heights) // 2]
    y_mid = [_stroke_y_center_bbox_px(bb) for bb in boxes]
    pitch, off = _ruled_pitch_offset_with_row_height_scale(
        y_mid, med_h, row_height_scale=row_height_scale
    )
    inv = 1.0 / max(pitch, 1e-6)
    rids = [int(round((y - off) * inv)) for y in y_mid]
    return float(pitch), float(off), min(rids), max(rids)


def _stroke_y_center_bbox_px(bb: tuple[float, float, float, float]) -> float:
    """Vertical anchor: center of the stroke's axis-aligned bounding box (page px)."""
    top, bottom = bb[1], bb[3]
    return 0.5 * (top + bottom)


def _grid_alignment_mse(y_mid: list[float], pitch: float, off: float) -> float:
    """Mean squared residual to nearest ruled line ``off + k * pitch`` (unnormalized sum)."""
    if pitch <= 1e-9:
        return float("inf")
    inv = 1.0 / pitch
    s = 0.0
    for y in y_mid:
        k = round((y - off) * inv)
        d = y - (off + k * pitch)
        s += d * d
    return s


def _candidate_ruled_pitches_px(sorted_y: list[float], med_h: float) -> list[float]:
    """Pitch candidates from body-height ladders, gap distribution, and span / #jumps."""
    # Ruled notebook: spacing not much smaller than one line of writing.
    lo = max(22.0, 1.05 * med_h)
    hi = min(520.0, 4.2 * med_h)
    cand: set[float] = set()
    for m in (1.05, 1.08, 1.10, 1.12, 1.15, 1.18, 1.22, 1.28, 1.32, 1.38):
        p = med_h * m
        if lo <= p <= hi:
            cand.add(float(p))
    lg: list[float] = []
    n = len(sorted_y)
    if n >= 2:
        gaps = [sorted_y[i + 1] - sorted_y[i] for i in range(n - 1)]
        sep = 0.38 * med_h
        lg = sorted([g for g in gaps if g > sep])
        for g in lg:
            if lo <= g <= hi:
                cand.add(float(g))
        if len(lg) >= 2:
            cand.add(float(lg[len(lg) // 2]))
            cand.add(float(lg[len(lg) * 3 // 4]))
            cand.add(float(lg[len(lg) // 4]))
        if lg:
            base = lg[len(lg) // 2]
            for scale in (0.92, 0.94, 0.97, 1.0, 1.03, 1.06, 1.09, 1.12):
                p = base * scale
                if lo <= p <= hi:
                    cand.add(float(p))
    seed = _estimate_ruled_line_pitch_px(sorted_y, med_h)
    cand.add(seed)
    for scale in (0.88, 0.91, 0.94, 0.97, 1.0, 1.03, 1.06, 1.10, 1.14):
        p = seed * scale
        if lo <= p <= hi:
            cand.add(float(p))
    if n >= 3 and lg:
        span = sorted_y[-1] - sorted_y[0]
        for extra in (-1, 0, 1, 2):
            denom = max(1, len(lg) + extra)
            p = span / float(denom)
            if lo <= p <= hi:
                cand.add(float(p))
    return sorted(cand)


def _best_ruled_pitch_and_offset_px(
    y_mid: list[float],
    med_h: float,
    *,
    off_steps: int = 96,
) -> tuple[float, float]:
    """Pick ``(pitch, off)`` that best snaps all bbox centers to one ruled grid (page-wide).

    Tries many pitch hypotheses (dense where handwriting repeats line spacing), fits
    ``off`` for each, minimizes sum of squared snap residuals, then refines pitch
    locally around the winner.
    """
    if not y_mid:
        return 28.0, 0.0
    if len(y_mid) == 1:
        return _estimate_ruled_line_pitch_px(y_mid, med_h), 0.0
    sy = sorted(y_mid)
    candidates = _candidate_ruled_pitches_px(sy, med_h)
    best_p = _estimate_ruled_line_pitch_px(sy, med_h)
    best_o = _best_ruled_grid_offset_px(y_mid, best_p, steps=off_steps)
    best_c = _grid_alignment_mse(y_mid, best_p, best_o)
    for pitch in candidates:
        off = _best_ruled_grid_offset_px(y_mid, pitch, steps=off_steps)
        c = _grid_alignment_mse(y_mid, pitch, off)
        if c < best_c - 1e-6:
            best_c, best_p, best_o = c, pitch, off
        elif abs(c - best_c) <= 1e-6 and pitch > best_p:
            # Tie: prefer slightly larger pitch → fewer phantom row splits.
            best_p, best_o = pitch, off
    ref_lo = best_p * 0.92
    ref_hi = best_p * 1.08
    for _ in range(3):
        floor_p = max(22.0, 1.05 * med_h)
        cap_p = min(520.0, 4.5 * med_h)
        for i in range(25):
            pitch = ref_lo + (ref_hi - ref_lo) * (i / 24.0) if ref_hi > ref_lo else best_p
            if pitch < floor_p or pitch > cap_p:
                continue
            off = _best_ruled_grid_offset_px(y_mid, pitch, steps=off_steps)
            c = _grid_alignment_mse(y_mid, pitch, off)
            if c < best_c - 1e-6:
                best_c, best_p, best_o = c, pitch, off
            elif abs(c - best_c) <= 1e-6 and pitch > best_p:
                best_p, best_o = pitch, off
        ref_lo = best_p * 0.985
        ref_hi = best_p * 1.015
    floor_p = max(22.0, 1.08 * med_h)
    if best_p < floor_p:
        best_p = floor_p
        best_o = _best_ruled_grid_offset_px(y_mid, best_p, steps=off_steps)
    return best_p, best_o


def _ruled_pitch_offset_with_row_height_scale(
    y_mid: list[float],
    med_h: float,
    *,
    off_steps: int = 96,
    row_height_scale: float | None = None,
) -> tuple[float, float]:
    """Pitch/offset used for clustering, G-code order, and SVG row bands (scaled row height)."""
    pitch, off = _best_ruled_pitch_and_offset_px(y_mid, med_h, off_steps=off_steps)
    s = float(RULED_LINE_ROW_HEIGHT_SCALE if row_height_scale is None else row_height_scale)
    if s <= 1.0 or not y_mid:
        return pitch, off
    pitch = float(pitch * s)
    lo = max(22.0, 1.08 * med_h)
    hi = min(520.0, 4.5 * med_h)
    pitch = min(max(pitch, lo), hi)
    off = _best_ruled_grid_offset_px(y_mid, pitch, steps=off_steps)
    return pitch, off


def _estimate_ruled_line_pitch_px(sorted_y_centers: list[float], med_h: float) -> float:
    """Ruled line spacing from sorted bbox **vertical centers**.

    On one ruled line, many centers lie close on Y → in sorted order they form a **dense
    run** (small gaps). The next run is the line below; **large** gaps between consecutive
    sorted centers estimate between-line steps; their median is **pitch**.
    """
    if len(sorted_y_centers) < 2:
        return float(max(22.0, med_h * 1.22))
    gaps = [
        sorted_y_centers[i + 1] - sorted_y_centers[i]
        for i in range(len(sorted_y_centers) - 1)
    ]
    # Ignore tiny steps (same ruled line); keep strokes that sit on different rows.
    sep = 0.40 * med_h
    line_gaps = [g for g in gaps if g > sep]
    if len(line_gaps) >= 2:
        pitch = sorted(line_gaps)[len(line_gaps) // 2]
    elif len(line_gaps) == 1:
        pitch = line_gaps[0]
    else:
        pitch = max(22.0, med_h * 1.22)
    pitch = max(float(pitch), 0.78 * med_h)
    # Ruled spacing is not smaller than ~one text line of body height (tetradь).
    pitch = max(float(pitch), 1.10 * med_h)
    pitch = min(float(pitch), 4.2 * med_h)
    return float(pitch)


def _best_ruled_grid_offset_px(y_mid: list[float], pitch: float, *, steps: int = 96) -> float:
    """``off`` in ``[0, pitch)`` minimizing ``sum_i (y_i - (off + round((y_i-off)/pitch)*pitch))^2``."""
    if not y_mid or pitch <= 1e-6:
        return 0.0
    inv = 1.0 / pitch
    best_o = 0.0
    best_c = float("inf")
    for s in range(steps):
        o = (s / steps) * pitch
        c = 0.0
        for y in y_mid:
            k = round((y - o) * inv)
            d = y - (o + k * pitch)
            c += d * d
        if c < best_c:
            best_c = c
            best_o = o
    return best_o


def _indices_by_ruled_row_id(y_mid: list[float], pitch: float, off: float) -> list[list[int]]:
    inv = 1.0 / pitch
    by_row: defaultdict[int, list[int]] = defaultdict(list)
    for i, y in enumerate(y_mid):
        rid = int(round((y - off) * inv))
        by_row[rid].append(i)
    order = sorted(by_row.keys())
    return [by_row[k] for k in order]


def _merge_row_clusters_if_centroids_close(
    clusters: list[list[int]],
    y_mid: list[float],
    pitch: float,
    med_h: float,
) -> list[list[int]]:
    """Join row buckets whose bbox centers sit in the same ruled band (grid seam fix)."""
    if len(clusters) < 2:
        return clusters
    # One ruled band can span ~1× body height between bbox centers (tall / multi-piece line).
    thresh = max(12.0, 0.40 * pitch, 0.64 * med_h, 0.90 * med_h, 1.05 * med_h)

    def centroid(idxs: list[int]) -> float:
        return sum(y_mid[i] for i in idxs) / len(idxs)

    ordered = sorted(clusters, key=centroid)
    out: list[list[int]] = []
    cur = list(ordered[0])
    cur_c = centroid(cur)
    for nxt in ordered[1:]:
        nc = centroid(nxt)
        if nc - cur_c <= thresh:
            cur.extend(nxt)
            cur_c = centroid(cur)
        else:
            out.append(cur)
            cur = list(nxt)
            cur_c = nc
    out.append(cur)
    return out


def _prepare_row_clusters_overlap(
    n: int,
    y_spans: list[tuple[float, float, float]],
    cy: list[float],
    med_h: float,
) -> list[list[int]]:
    """Legacy row grouping: DSU on core overlap + mid-Y bands + gap refinement."""
    overlap_ratio = 0.38
    center_band_overlap = 0.82
    center_band_gap = 0.46
    core_shrink = 0.11
    dsu = _DSU(n)
    for i in range(n):
        ymin_i, ymax_i, hi = y_spans[i]
        ci_lo, ci_hi = _shrink_y_interval(ymin_i, ymax_i, core_shrink)
        for j in range(i + 1, n):
            ymin_j, ymax_j, hj = y_spans[j]
            cj_lo, cj_hi = _shrink_y_interval(ymin_j, ymax_j, core_shrink)
            dy = abs(cy[i] - cy[j])
            ov = _vertical_overlap_px(ci_lo, ci_hi, cj_lo, cj_hi)
            if ov >= overlap_ratio * min(hi, hj):
                if dy <= center_band_overlap * med_h:
                    dsu.union(i, j)
            else:
                gap = max(ymin_i, ymin_j) - min(ymax_i, ymax_j)
                if (
                    gap > 0
                    and gap <= 0.38 * med_h
                    and dy <= center_band_gap * med_h
                ):
                    dsu.union(i, j)

    groups: defaultdict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[dsu.find(i)].append(i)

    clusters = list(groups.values())
    for _ in range(4):
        new_c = _refine_row_clusters_by_cy(clusters, cy, med_h)
        if len(new_c) == len(clusters):
            break
        clusters = new_c
    return clusters


def _prepare_row_clusters(
    polys_px: list[list[tuple[float, float]]],
    bboxes_px: list[tuple[float, float, float, float]],
    *,
    row_height_scale: float | None = None,
) -> tuple[
    list[list[tuple[float, float]]],
    list[tuple[float, float, float]],
    float,
    list[tuple[float, float, float, float]],
    list[list[int]],
]:
    """Build oriented polylines, ``y_spans``, ``med_h``, and sorted row clusters.

    Rows follow a **uniform ruled-line grid** in page Y when possible; used by
    ``order_strokes`` and debug row overlays.
    """
    n = len(polys_px)
    y_spans: list[tuple[float, float, float]] = []
    oriented: list[list[tuple[float, float]]] = []
    for p, bb in zip(polys_px, bboxes_px):
        o = _orient_poly_left_to_right(list(p))
        oriented.append(o)
        ymin, ymax = bb[1], bb[3]
        h = max(1e-3, ymax - ymin)
        y_spans.append((ymin, ymax, h))

    heights = [t[2] for t in y_spans]
    med_h = sorted(heights)[len(heights) // 2]
    cy_bbox = [0.5 * (t[0] + t[1]) for t in y_spans]
    y_mid = cy_bbox

    if n < 2:
        clusters = [list(range(n))]
    else:
        pitch, off = _ruled_pitch_offset_with_row_height_scale(
            y_mid, med_h, row_height_scale=row_height_scale
        )
        clusters = _indices_by_ruled_row_id(y_mid, pitch, off)
        clusters = _merge_row_clusters_if_centroids_close(clusters, y_mid, pitch, med_h)
        span_y = max(y_mid) - min(y_mid)
        too_merged = len(clusters) == 1 and span_y > 1.88 * pitch and n >= 8
        too_split = len(clusters) >= max(28, int(0.52 * n)) and n >= 14
        bad_pitch = pitch < 0.72 * med_h or pitch > 4.0 * med_h
        if bad_pitch or too_merged or too_split:
            clusters = _prepare_row_clusters_overlap(n, y_spans, cy_bbox, med_h)

    clusters.sort(key=lambda idxs: min(y_spans[i][0] for i in idxs))
    return oriented, y_spans, med_h, bboxes_px, clusters


def row_cluster_indices_for_page(
    page: dict[str, Any],
    *,
    row_height_scale: float | None = None,
) -> list[list[int]]:
    """Row groups used for stroke ordering and debug SVG (indices into page stroke list).

    Rows are top-to-bottom (smaller page Y first).
    """
    polys, boxes = collect_stroke_polys_and_bboxes_px_for_page(page)
    if not polys:
        return []
    *_, clusters = _prepare_row_clusters(
        polys, boxes, row_height_scale=row_height_scale
    )
    return clusters


def order_strokes(
    polys_px: list[list[tuple[float, float]]],
    *,
    bboxes_px: list[tuple[float, float, float, float]] | None = None,
    row_height_scale: float | None = None,
    stroke_order_tuning: StrokeOrderTuning | None = None,
) -> list[list[tuple[float, float]]]:
    """Handwriting-like order: **ruled rows** top-to-bottom, never interleaving rows.

    Inside each row: cluster **primary** strokes into left-to-right **X-bands** (word-sized
    gaps), chain each band with a left-seed greedy NN (penalty on pen-up moves left), then
    attach **debris** (dots, tiny marks) to the nearest band by center-X and chain them from
    the last stroke of that band — closer to “finish the word, then dot the i”.

    After each full row, the first stroke of the next row prefers a pen-down near
    **~1.5× intra-line slack** below the previous row’s bottom (carriage return).
    """
    if not polys_px:
        return []
    n = len(polys_px)
    if bboxes_px is None:
        bboxes_px = []
        for p in polys_px:
            o = _orient_poly_left_to_right(list(p))
            bboxes_px.append(_bbox_px(o))
    elif len(bboxes_px) != n:
        raise ValueError("bboxes_px must match polys_px length")

    oriented, _y_spans, med_h, bboxes_px, clusters = _prepare_row_clusters(
        polys_px, bboxes_px, row_height_scale=row_height_scale
    )
    tun = stroke_order_tuning or StrokeOrderTuning()
    intra_line_y_slack = max(
        tun.intra_line_y_slack_min_px,
        tun.intra_line_y_slack_factor * med_h,
    )
    y_w = tun.chain_y_weight
    back_w = tun.chain_back_x_weight

    order_idx: list[int] = []
    prev_row_bottom: float | None = None

    for row_i, idxs in enumerate(clusters):
        if not idxs:
            continue
        primary = [i for i in idxs if not _is_debris_stroke(bboxes_px[i], med_h)]
        debris = [i for i in idxs if _is_debris_stroke(bboxes_px[i], med_h)]
        row_bottom = max(bboxes_px[i][3] for i in idxs)

        if not primary:
            tail = _order_row_indices_minimize_travel(
                idxs,
                oriented,
                bboxes_px,
                med_h,
                chain_y_weight=y_w,
                chain_back_x_weight=back_w,
            )
            order_idx.extend(tail)
            prev_row_bottom = row_bottom
            continue

        groups = _cluster_row_primaries_by_x_gap(
            primary,
            bboxes_px,
            med_h,
            gap_med_h_factor=tun.x_gap_med_h_factor,
        )
        debris_map = _assign_debris_to_x_groups(debris, groups, bboxes_px)
        prefer_y: float | None = None
        if row_i > 0 and prev_row_bottom is not None:
            prefer_y = (
                prev_row_bottom + tun.carriage_y_extra_lines * intra_line_y_slack
            )

        for gi, g in enumerate(groups):
            use_prefer = prefer_y if gi == 0 else None
            g_ord = _greedy_chain_best_of_seeds(
                g,
                oriented,
                bboxes_px,
                med_h,
                y_weight=y_w,
                back_x_weight=back_w,
                max_seed_trials=5,
                prefer_start_y=use_prefer,
            )
            order_idx.extend(g_ord)
            dlist = debris_map.get(gi) or []
            if dlist:
                order_idx.extend(
                    _chain_debris_from_last_index(
                        dlist,
                        oriented,
                        order_idx[-1],
                        y_weight=y_w,
                        back_x_weight=back_w,
                    )
                )

        prev_row_bottom = row_bottom

    return [oriented[i] for i in order_idx]


def collect_strokes_mm_for_page(
    page: dict[str, Any],
    width_mm: float,
    flip_y: bool,
    offset_x_mm: float,
    offset_y_mm: float,
    *,
    writing_order: bool = True,
    row_height_scale: float | None = None,
    stroke_order_tuning: StrokeOrderTuning | None = None,
) -> list[list[tuple[float, float]]]:
    pw = max(1, int(page.get("width") or 1))
    ph = max(1, int(page.get("height") or 1))
    polys_px, bboxes_px = collect_stroke_polys_and_bboxes_px_for_page(page)
    if writing_order:
        polys_px = order_strokes(
            polys_px,
            bboxes_px=bboxes_px,
            row_height_scale=row_height_scale,
            stroke_order_tuning=stroke_order_tuning,
        )
    out: list[list[tuple[float, float]]] = []
    for poly in polys_px:
        out.append(
            [
                _px_to_mm(
                    x_px,
                    y_px,
                    pw,
                    ph,
                    width_mm,
                    flip_y,
                    offset_x_mm,
                    offset_y_mm,
                )
                for x_px, y_px in poly
            ]
        )
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
    *,
    writing_order: bool = True,
    row_height_scale: float | None = None,
    stroke_order_tuning: StrokeOrderTuning | None = None,
) -> str:
    pw = max(1, int(page.get("width") or 1))
    ph = max(1, int(page.get("height") or 1))
    strokes = collect_strokes_mm_for_page(
        page,
        width_mm,
        flip_y,
        offset_x_mm,
        offset_y_mm,
        writing_order=writing_order,
        row_height_scale=row_height_scale,
        stroke_order_tuning=stroke_order_tuning,
    )
    chunks: list[str] = []
    chunks.append(f"( page {page_index + 1} / {page_count} )")
    chunks.append(f"( page pixels {pw} x {ph}, target width {width_mm:.3f} mm )")
    wo = " reordered" if writing_order else ""
    chunks.append(f"( strokes {len(strokes)}{wo} )")

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
    *,
    writing_order: bool = True,
    row_height_scale: float | None = None,
    stroke_order_tuning: StrokeOrderTuning | None = None,
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
            page,
            width_mm,
            flip_y,
            offset_x_mm,
            offset_y_mm,
            writing_order=writing_order,
            row_height_scale=row_height_scale,
            stroke_order_tuning=stroke_order_tuning,
        )
        parts.append(f"( page {i + 1} / {n} )")
        parts.append(f"( page pixels {pw} x {ph}, target width {width_mm:.3f} mm )")
        wo = " reordered" if writing_order else ""
        parts.append(f"( strokes {len(strokes)}{wo} )")
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
    writing_order: bool = True,
    row_height_scale: float | None = None,
    stroke_order_tuning: StrokeOrderTuning | None = None,
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
                writing_order=writing_order,
                row_height_scale=row_height_scale,
                stroke_order_tuning=stroke_order_tuning,
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
            writing_order=writing_order,
            row_height_scale=row_height_scale,
            stroke_order_tuning=stroke_order_tuning,
        )
        out_path.write_text(text, encoding="utf-8")
        written.append(out_path)
    return written
