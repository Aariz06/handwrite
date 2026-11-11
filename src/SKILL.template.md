---
name: handwrite
description: Turn a sample of the user's handwriting into a font, then write documents out in that handwriting as print-ready PDFs. Use for /handwrite or requests for a handwriting font or handwritten document.
---

# Handwrite

Builds a font from the user's own handwriting (7 rotating versions of every character, so repeats never look identical), then writes any document in it: a described document or an uploaded one. Two bundled scripts do the work; your job is the conversation, labelling, converting content, and checking results by eye.

Only for the user's own handwriting (or handwriting they have permission to use). Do not reproduce signatures, and do not help pass writing off as another person's.

## 0. Set up (once per session)

Write the two scripts at the bottom of this file to the working directory. Do not retype them: extract them from this file (its folder is the "Base directory" shown when the skill loads).

```bash
pip install --break-system-packages opencv-python-headless numpy scikit-image fonttools reportlab Hershey-Fonts pillow pypdfium2 2>&1 | tail -1
python3 - "<base directory>/SKILL.md" <<'EOF'
import re,sys
t=open(sys.argv[1],encoding='utf-8').read()
for name,body in re.findall(r'<!-- file: (\S+) -->\n```python\n(.*?)\n```', t, re.S):
    open(name,'w',encoding='utf-8').write(body+'\n'); print('wrote',name,len(body))
EOF
python3 -m py_compile hw_font.py hw_doc.py && echo OK
```

If the file cannot be read from disk, write both scripts out by hand exactly as shown, then run `py_compile`; fix any typo it reports.

## 1. Get the handwriting

Ask what they have. Three routes:

- **They already have a font from this skill** (a `.ttf` from an earlier run): skip to step 3.
- **Template (best quality, recommended):** run `python3 hw_font.py template handwriting-template.pdf` and send them the PDF. They print both pages at 100%, write each character three times in the boxes (sitting on the lower guide line), and send back a photo or scan of each page. All four black corner squares must be visible; order and rotation do not matter.
- **Any photo of their handwriting:** a page of notes works. More writing means more real characters; isolated, unjoined letters work best.

Offer the template, but start with whatever they send. Never block on it.

## 2. Build the font

Name the font file after something neutral or what the user asks for, e.g. `MyHandwriting.ttf`. Building takes 1 to 2 minutes.

**From template photos**

```bash
python3 hw_font.py from-template MyHandwriting.ttf page1.jpg page2.jpg
```

If it reports that the corner squares were not found, ask for a flatter, better-lit photo with the whole page in frame.

**From any photo**

```bash
python3 hw_font.py segment sample.jpg work1      # makes work1/sheet0.png, sheet1.png, ...
```

Look at every `sheet*.png`. Each cell is one cut-out piece with its number underneath, in reading order, so you can follow along with the text of the page. Then write `work1/labels.json`:

```json
{"labels":  {"a": [51, 190], "x": [22, 108], "λ": [61], "(": [110]},
 "largest": {"e": [202]},
 "splits":  {"370": "ch", "246": "C_"}}
```

- `labels`: piece numbers that show exactly one clean character, best sample first. Up to 7 per character are used.
- `largest`: pieces where only the biggest blob is the character (a letter with a stray mark attached).
- `splits`: a piece containing several joined letters, cut into those letters at the thinnest points. Use `_` for a part you want to discard.

Labelling rules: read the page text first so you know what each piece should be. Skip pieces that are blobs, fragments, table lines, or several letters fused beyond a clean cut. Be careful with look-alikes (l / 1 / I / |, o / O / 0, s / S, x / X): use the surrounding text and size to decide, and skip when unsure. A wrong label is worse than a missing one, because missing characters are drawn automatically in a matching weight. Then:

```bash
python3 hw_font.py from-labels MyHandwriting.ttf work1          # several work folders may be listed
```

If the user later sends more samples, segment each into its own folder, label it, and rebuild with all folders listed.

**Check it.** The build prints how many real samples each character has and which basic characters had to be drawn. Then:

```bash
python3 hw_doc.py --preview MyHandwriting.ttf preview.pdf && pdftoppm -r 70 -png preview.pdf preview
```

Look at the preview image. If a character is clearly wrong (mislabelled, upside down, a blob), fix `labels.json` and rebuild. Send the user the `.ttf` and the preview, and tell them plainly: which characters came from their writing, which were drawn to match, and which rest on a single weak sample. Tell them to keep the `.ttf` so they can skip this step next time. In Word, repeated letters vary once "Use Contextual Alternates" is ticked under Font > Advanced.

## 3. Find out what to write

Ask (in one go, with a question tool if there is one):

1. **What to write:** describe a document, or upload one (PDF, Word, text, image).
2. **Writing tool:** pencil (default), pen, or marker.
3. **Extras:** a few smudges (pencil only), ruled notebook lines, a dotted divider between columns.

If they already said any of this, do not ask again.

## 4. Turn the content into a spec

Write `spec.json` for `hw_doc.py` (run it with no arguments to see the full format):

```json
{"page":  {"size": "letter", "columns": 1, "margin": 36, "font_size": 13},
 "style": {"tool": "pencil", "smudges": true, "divider": false, "ruled": false},
 "blocks": [
   {"h1": "Page title"},
   {"h2": "Underlined section heading"},
   {"h3": "Plain sub-heading"},
   {"p": "A paragraph. Subscripts H_{2}O, superscripts e^{-λx}, symbols typed directly: ≤ ≠ √ ∑ ∫ α β π."},
   {"list": ["first point", "second point"], "ordered": false},
   {"table": [["Header A", "Header B"], ["cell", "cell"], ["a row with fewer cells spans the rest"]], "widths": [0.3, 0.7], "header": true},
   {"note": "smaller text"}, {"space": 1}, {"break": "column"}
 ]}
```

- **Described document:** write the content yourself as you normally would, then express it in blocks.
- **Uploaded document:** read it fully and transcribe it faithfully. Do not summarise, drop or reword anything. **Match the original layout:** same number of columns, the same tables with the same column proportions (`widths`), the same order, and the same page count by setting `"font_size": "fit"` and `"pages"` to the original's page count. Tight sources may need `"margin": 20` to 24.
- Decorative formatting does not carry over (colour, bold, shading); headings become `h1`/`h2`/`h3`.
- Maths: use `_{}` and `^{}` and Unicode symbols. Bars and hats are a letter followed by a combining mark (x + U+0304, p + U+0302). There are no stacked fractions; write a/b.
- Natural handwriting is about 12 to 14 pt. Sizes under 9 pt read as tiny, very neat writing; say so if the layout forces that.

## 5. Render and check

```bash
python3 hw_doc.py MyHandwriting.ttf spec.json Handwritten.pdf
pdftoppm -r 60 -png Handwritten.pdf check        # then look at every page
```

Read the script's output: it reports the font size, the page count, and any characters the font lacks (written as "?" or without their accent). Replace or respell those and rerun. Look at each page image for text running outside its cell, awkward table widths (set `widths` yourself), or a page count that differs from the original. For a pencil render also zoom into one area (`pdftoppm -r 200 -x .. -y .. -W 1200 -H 800`) to confirm it is legible.

Style notes:
- **pencil** produces an image-based PDF (grey graphite, grain, uneven pressure; text is not selectable; about 1 to 3 MB per page at the default 450 dpi). `"darkness": 1.2` prints darker.
- **pen** and **marker** produce crisp vector PDFs. `"ink": "#1b2a5c"` sets the pen colour.
- `"jitter"` controls messiness: 0.5 neat, 1.0 natural, 1.5 loose.
- `"ruled": true` snaps every line of writing onto notebook rules.

Send the PDF with one or two lines: page count, text size, tool, and anything the user should know (drawn or weak characters that appear a lot, characters that were substituted). Tell them to print at 100% / actual size. Then offer changes: darker, neater, different tool, extras on or off.

## Scripts

<!-- file: hw_font.py -->
```python
@@FONT@@
```

<!-- file: hw_doc.py -->
```python
@@DOC@@
```
