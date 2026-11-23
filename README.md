# samsung-notes-format

Reverse-engineered reader for the handwriting in Samsung Notes `.sdocx` files. Decodes the on-disk pen-stroke format and renders the strokes back out.

This is a research repo, focused on the stroke geometry. For a more complete library that also decodes pressure, tilt, and color and renders full ink, see [twangodev/sdocx](https://github.com/twangodev/sdocx).

<img src="example.png" width="340" alt="A Samsung Notes page decoded by render.py: the handwriting, with each stroke drawn inside its stored bounding box" />

- Write-up (how and why): https://musaab.io/posts/2026/reverse-engineering-samsung-notes/
- Format reference: [RESEARCH.md](RESEARCH.md)

## Usage

```
python3 render.py note.sdocx [out.svg]
```

Parses the note, decodes every stroke, and writes an SVG with each stroke drawn inside its stored bounding box. The whole pipeline is one self-contained file, ~190 lines.

## Used by

These projects cite the format notes or use the sample files:

- [Obsidian Importer](https://github.com/obsidianmd/obsidian-importer/blob/3.2.0/src/formats/samsung-notes/parse.ts#L1-L9): Obsidian's official importer cites the format notes for its `.sdocx` parser. It imports handwriting as SVG.
- [Abel Notes](https://github.com/abelnotes/abelnotes/blob/v0.38.1/lib/features/import/README.md#samsung-notes-sdocx): cross-checked its Samsung Notes importer against the format notes.
- [Adv Notes](https://github.com/moondotgz/adv-notes/blob/a875a19a056ff38b138d0df6163101009b425b06/README.md#third-party-code): cites the format notes for editable handwriting import and uses two sample notes in its tests.
- [NoteKonverter](https://github.com/volkanozdamar/NoteKonverter/blob/v1.0.0/README.md#acknowledgements): credits the sample files in its converter for Samsung Notes, Boox Notes, and Saber.
- [ResendeGHF/notes](https://github.com/ResendeGHF/notes/blob/V1.2.0/lib/data/samsung_notes/sdocx_parser.dart#L10-L16): cites the stroke coordinate decoding in its Samsung Notes parser.
- [mNotes](https://github.com/Marcin942/mNotes/blob/0f9cc6d3e9273a12205e851f7a50bdc60bc5cff1/app/src/main/java/com/mdev/mnotes/core/samsung/SdocxReader.kt#L7-L12): cites the format notes in its stroke reader.

## Other files

Older research files, kept for reference rather than as the canonical implementation. `render.py` is the clean, correct one; treat the rest as the trail it was built from.

- `sdocx_extractor.py`: fuller extractor that dumps all metadata to JSON. Its delta decode is a slight simplification (5 integer bits instead of the full 10); the output is identical on real handwriting, but `render.py` has the exact decode.
- `plot_strokes.py`: earlier SVG renderer.
- `artifacts/debugging/`: scratch scripts from working the format out; they try several wrong encodings before the right one.
- `sdocxFiles/`, `extracted_sdocx/`: sample notes.
- `blog-artifacts/`: figures and the comparison harness for the write-up.
- `*.png`, `Screenshot_*.jpg`: leftover render and comparison artifacts from the research, kept as a rough record of progress rather than cleaned out (`example.png` is the one used above).

## Notes

Independent implementation for interoperability and research. The repo contains no Samsung binaries or decompiled code, only original code and the documented format. Samsung Notes is a trademark of Samsung Electronics. The code here is MIT-licensed (see [LICENSE](LICENSE)).
