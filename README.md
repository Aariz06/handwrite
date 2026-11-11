# handwrite

A Claude skill that turns a sample of your handwriting into a font, then writes documents out in that handwriting as print-ready PDFs.

- **Your handwriting, as a font.** Every character gets 7 versions that rotate as you type, so repeated letters never look stamped. Characters missing from your sample are drawn to match your stroke weight.
- **Any document, handwritten.** Describe a document or upload one (PDF, Word, text, image). Headings, paragraphs, lists, tables and maths formulas are supported, and uploaded documents keep their columns, tables and page count.
- **Looks written, not typed.** Wandering baselines, uneven letter size and spacing, hand-drawn table lines of varying thickness, and a pencil mode with graphite grain, pressure changes and optional smudges. Pen and marker modes are also included.

## Install

1. Download `handwrite-skill-v1.0.0.zip` from the [latest release](../../releases/latest), or zip the `handwrite/` folder yourself.
2. In Claude, open **Settings → Capabilities → Skills** and upload the zip.
3. Type `/handwrite` in a chat.

The skill needs a Claude session that can run code (it installs its Python dependencies on first use).

## Using it

1. **Give it your handwriting.** The skill offers a printable template (`examples/handwriting-template.pdf`): print both pages at 100%, write each character three times, and send a photo or scan of each page. Any photo of your handwriting also works, but the template gives the best result.
2. **Check the font.** You get the `.ttf` and a preview page, plus a list of which characters came from your writing and which were drawn to match. Keep the `.ttf`: uploading it next time skips this step.
3. **Ask for a document.** Describe it ("a one-page study guide on photosynthesis") or upload one, then pick pencil, pen or marker and any extras (smudges, ruled notebook lines, a dotted line between columns).
4. **Print it** at 100% / actual size.

In Microsoft Word, repeated letters vary once **Use Contextual Alternates** is ticked under Font → Advanced.

## Using the scripts without Claude

The two scripts in `src/` work on their own (Python 3.9+).

```bash
pip install -r requirements.txt
python3 src/hw_font.py template template.pdf                         # printable sample sheet
python3 src/hw_font.py from-template MyHand.ttf page1.jpg page2.jpg   # build the font from photos of it
python3 src/hw_doc.py --preview MyHand.ttf preview.pdf               # specimen page
python3 src/hw_doc.py MyHand.ttf examples/study-guide.json out.pdf   # write a document
```

Run either script with no arguments for its full options. `hw_doc.py` takes a JSON spec of blocks (`h1`, `h2`, `h3`, `p`, `list`, `table`, `note`, `space`, `break`) and page and style settings; `examples/study-guide.json` shows most of them. Pencil output needs `pdftoppm` (poppler-utils) or `pypdfium2`.

Building from an arbitrary photo (`segment` and `from-labels`) needs someone to label the cut-out characters, which is the step Claude does inside the skill.

## Repository layout

| Path | What it is |
|---|---|
| `handwrite/SKILL.md` | The skill itself, with both scripts embedded. Generated: do not edit by hand. |
| `src/hw_font.py` | Builds the font: template, template reading, photo segmentation, glyph drawing, font assembly. |
| `src/hw_doc.py` | Lays out and renders a document in the font (pencil, pen, marker). |
| `src/SKILL.template.md` | The skill's instructions, with placeholders where the scripts go. |
| `tools/build_skill.py` | Regenerates `handwrite/SKILL.md` from `src/`; `--check` verifies it is current, `--zip` builds the release zip. |
| `examples/` | The printable template and a sample document spec. |

To change the skill, edit files in `src/`, run `python3 tools/build_skill.py`, and commit both. CI fails if they drift apart.

## Limits

- Characters the font doesn't have (for example Chinese or Japanese) come out as "?", and accents the font can't draw are dropped; the skill reports both.
- The font takes its stroke weight from your sample: a pencil sample gives a thin font, a marker sample a heavy one.
- Pencil output is an image-based PDF, so its text is not selectable or searchable.
- Very dense layouts can force small text, which reads as tiny, unusually neat handwriting.

## Responsible use

Use this for your own handwriting, or handwriting you have permission to use. The skill will not reproduce signatures, and it is not meant for passing writing off as someone else's or getting around rules that require genuinely handwritten work.

## License

[MIT](LICENSE)
