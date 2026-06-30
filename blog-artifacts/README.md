# blog-artifacts

Figures and the comparison harness for the write-up, kept here so the post is reproducible. None of this is part of the extractor; it only consumes it.

## Figures

Black/white SVGs (matching the blog), written to `out/`. They draw with `currentColor` on a transparent background, so they follow light and dark mode.

```
python3 fig_bitlayout.py                        # the 16-bit delta word: full word vs sdocx's low byte
python3 fig_coverage.py                         # one stroke, full-word vs low-byte decode, in its box
python3 fig_grid.py  "<file>.sdocx" grid.svg    # grid of strokes, each filling its box
python3 fig_boxed.py "<file>.sdocx" boxed.svg   # full page, every stroke drawn in its box
```

`lib.py` holds the shared helpers; `data/` holds decoded points so the figures build without re-running anything.

## The twangodev/sdocx comparison

The figures that show twangodev/sdocx undershooting run their real published crate, not a reimplementation. `harness/main.rs` calls `sdocx::parse()` and dumps the points it returns:

```
git clone https://github.com/twangodev/sdocx /tmp/sdocx-repo
# point harness/Cargo.toml's path dependency at /tmp/sdocx-repo/crates/sdocx
cd harness && cargo run --release -- "<file>.sdocx" <stroke_index>
```

The captured output lives in `data/thisistitle_twangodev.json`; our own points come from `sdocx_extractor.py` in the repo root.

## What the figures show

- Coordinate deltas decode as magnitude `(word & 0x7FFF) / 32`: five fractional bits, ten integer, sign in bit 15. twangodev/sdocx reads only the low byte, so any delta over 8px loses its high bits and reads short.
- The stored bounding box is independent of the delta stream, so drawing each decoded stroke in its box is an honest check: position is anchored, span is never scaled to fit. Median fill is 100%, worst 96.7%.
