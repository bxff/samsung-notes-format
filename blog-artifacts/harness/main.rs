// Comparison harness: dumps the points twangodev/sdocx decodes for a given
// stroke, using their *real, unmodified* published crate. This is what the blog
// figures label "twangodev/sdocx" — not a reimplementation of their decoder.
//
// Reproduce:
//   git clone https://github.com/twangodev/sdocx /tmp/sdocx-repo
//   (point the path dependency below at /tmp/sdocx-repo/crates/sdocx)
//   cargo run --release -- "<file>.sdocx" <stroke_index>
fn main() {
    let path = std::env::args().nth(1).expect("pass sdocx path");
    let stroke_idx: usize = std::env::args().nth(2).unwrap_or("0".into()).parse().unwrap();
    let doc = sdocx::parse(&path).unwrap();
    let stroke = &doc.pages[0].strokes[stroke_idx];
    println!(
        "SDOCX stroke {}: {} points, pen_width={}, color={:?}",
        stroke_idx, stroke.points.len(), stroke.pen_width, stroke.color
    );
    for (i, p) in stroke.points.iter().enumerate() {
        let pressure = stroke.pressures.get(i).copied().unwrap_or(-1.0);
        println!("  ({:.2}, {:.2})  p={:.4}", p.x, p.y, pressure);
    }
}
