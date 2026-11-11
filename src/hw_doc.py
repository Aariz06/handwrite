#!/usr/bin/env python3
"""hw_doc.py - write a document out by hand with a font made by hw_font.py.
  hw_doc.py FONT.ttf SPEC.json OUT.pdf
  hw_doc.py --preview FONT.ttf OUT.pdf        specimen page for checking a new font
SPEC.json = {"page": {...}, "style": {...}, "blocks": [...]}   (every key optional except blocks)
 page : size "letter"|"a4" · columns 1 · margin 36 · font_size 13 or "fit" · pages 1 (target page count when font_size is "fit")
 style: tool "pencil"|"pen"|"marker" · ink "#1b2a5c" (pen colour) · smudges false · divider false (dotted line between columns)
        ruled false (notebook lines) · jitter 1.0 (0 = rigid, 1.5 = messy) · dpi 450 (pencil only) · darkness 1.0 (pencil only)
 blocks: {"h1": text} page title · {"h2": text} underlined section · {"h3": text} plain sub-heading · {"p": text} · {"note": text} smaller
        {"list": [text,..], "ordered": false} · {"table": [[cell,..],..], "widths": [fractions], "header": true, "box": false}
        {"space": lines} · {"break": "column"|"page"}
 text markup: _{subscript} ^{superscript}, "\\n" forces a new line, x̄ p̂ etc. via combining marks, any character the font has.
 a table row with fewer cells than columns lets its last cell span the remaining columns.
Needs: reportlab fonttools numpy opencv-python-headless pillow, and for pencil pdftoppm (poppler-utils) or pypdfium2"""
import sys, os, math, random, json, tempfile, subprocess, unicodedata, shutil
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont as RLFont
from reportlab.lib.colors import HexColor
from fontTools.ttLib import TTFont
COMB = '̄̂̃́̀̈'; SS = 0.68; SIZES = {'letter': (612, 792), 'a4': (595.28, 841.89)}

class Hand:
    def __init__(self, ttf):
        t = TTFont(ttf); order = set(t.getGlyphOrder()); self.nv = 1 + max([int(g.rsplit('.alt', 1)[1]) for g in order if '.alt' in g] or [0])
        self.tmp = tempfile.mkdtemp(); self.W = []; self.id = 'HW%d_' % (abs(hash(os.path.abspath(ttf))) % 99999)
        for k in range(self.nv):
            t = TTFont(ttf)
            for tb in t['cmap'].tables:
                for cp, g in list(tb.cmap.items()):
                    if k and f'{g}.alt{k}' in order: tb.cmap[cp] = f'{g}.alt{k}'
            if 'GSUB' in t: del t['GSUB']
            for n in t['name'].names:
                if n.nameID in (1, 3, 4, 6): n.string = f'{self.id}{k}'
            p = f'{self.tmp}/v{k}.ttf'; t.save(p); pdfmetrics.registerFont(RLFont(f'{self.id}{k}', p))
            cm = t.getBestCmap(); hm = t['hmtx']; self.W.append({chr(cp): hm[g][0] / 1000 for cp, g in cm.items()})
        self.missing = set()
    def has(self, ch): return ch in self.W[0]

class R:   # one rendering run
    def __init__(s, hand, spec):
        s.h = hand; pg = spec.get('page', {}); st = spec.get('style', {}); s.blocks = spec['blocks']
        s.PW, s.PH = SIZES.get(str(pg.get('size', 'letter')).lower(), SIZES['letter']); s.M = pg.get('margin', 36); s.ncol = max(1, int(pg.get('columns', 1)))
        s.GAP = 14; s.CW = (s.PW - 2 * s.M - (s.ncol - 1) * s.GAP) / s.ncol; s.fs_req = pg.get('font_size', 13); s.pages_req = int(pg.get('pages', 1))
        s.tool = st.get('tool', 'pencil'); s.J = float(st.get('jitter', 1.0)); s.ruled = bool(st.get('ruled')); s.divider = bool(st.get('divider')); s.smudges = bool(st.get('smudges'))
        s.dpi = int(st.get('dpi', 450)); s.dark = float(st.get('darkness', 1.0))
        s.ink = HexColor('#000000') if s.tool == 'pencil' else HexColor(st.get('ink', '#1b2a5c' if s.tool == 'pen' else '#121212'))
    # ---- text
    def parse(s, txt):
        out = []; mode = 0; i = 0; txt = str(txt).replace('\t', ' ').replace('**', '')
        while i < len(txt):
            if txt.startswith('_{', i): mode = -1; i += 2; continue
            if txt.startswith('^{', i): mode = 1; i += 2; continue
            if txt[i] == '}' and mode: mode = 0; i += 1; continue
            ch = txt[i]; i += 1
            if ch == '\n': out.append(dict(ch='\n', mode=0, k=0, acc=None)); continue
            if ch in '²³' and not mode: out.append(dict(ch={'²': '2', '³': '3'}[ch], mode=1, k=s.n % s.h.nv, acc=None)); s.n += 1; continue
            seq = ch
            if not s.h.has(ch) or unicodedata.category(ch)[0] == 'L':
                d = unicodedata.normalize('NFD', ch)
                if len(d) > 1 and s.h.has(d[0]) and all(m in COMB and s.h.has(m) for m in d[1:]): seq = d
                elif len(d) > 1 and s.h.has(d[0]) and not s.h.has(ch): s.h.missing.add(ch); seq = d[0]
            for ch in seq:
                if ch in COMB and out and out[-1]['ch'] != '\n': out[-1]['acc'] = (ch, s.n % s.h.nv); continue
                if not s.h.has(ch): s.h.missing.add(ch); ch = '?'
                out.append(dict(ch=ch, mode=mode, k=s.n % s.h.nv, acc=None)); s.n += 1
        return out
    def iw(s, it, fs): return s.h.W[it['k']][it['ch']] * fs * (SS if it['mode'] else 1)
    def wrap(s, items, fs, width):
        width *= 0.985; sp = 0.27 * fs; lines = []; cur = []; cw = 0; words = [[]]
        for it in items:
            if it['ch'] == '\n': words += [None, []]
            elif it['ch'] == ' ' and it['mode'] == 0: words.append([])
            else: words[-1].append(it)
        for w in words:
            if w is None: lines.append(cur); cur = []; cw = 0; continue
            if not w: continue
            ww = sum(s.iw(it, fs) for it in w)
            if cur and cw + sp + ww > width: lines.append(cur); cur = []; cw = 0
            if ww > width:
                s.hard += 1
                for it in w:
                    x = s.iw(it, fs)
                    if cur and cw + x > width: lines.append(cur); cur = []; cw = 0
                    cur.append(it); cw += x
                cur.append(None); cw += sp; continue
            if cur: cur.append(None); cw += sp
            cur += w; cw += ww
        if cur: lines.append(cur)
        return lines or [[]]
    def words(s, items):
        out = [[]]
        for it in items:
            if it['ch'] in ' \n' and not it['mode']: out.append([])
            else: out[-1].append(it)
        return [w for w in out if w]
    def natural(s, items, fs): return sum(0.27 * fs if (it['ch'] == ' ' and not it['mode']) else s.iw(it, fs) for it in items if it['ch'] != '\n')
    def text(s, items, x, y, fs):
        """draw one line with its baseline at y; returns end x"""
        c = s.c; RJ = s.RJ; J = s.J; sp = 0.27 * fs
        x += RJ.uniform(-0.05, 0.38) * fs * J; y += RJ.gauss(0, 0.045 * fs) * J
        slope = RJ.gauss(0, 0.0075) * J; lsz = 1 + RJ.gauss(0, 0.025) * J; wy = RJ.gauss(0, 0.02 * fs) * J; x0 = x
        for it in items:
            if it is None: x += sp * (1 + (RJ.uniform(0.75, 1.4) - 1) * J); wy = wy * 0.6 + RJ.gauss(0, 0.03 * fs) * J; continue
            wy = wy * 0.85 + RJ.gauss(0, 0.016 * fs) * J
            size = fs * (SS if it['mode'] else 1) * lsz * (1 + RJ.gauss(0, 0.035) * J); rise = {0: 0, 1: 0.36 * fs, -1: -0.2 * fs}[it['mode']]
            yy = y + rise + wy + slope * (x - x0) + RJ.gauss(0, 0.012 * fs) * J
            if c:
                c.saveState(); c.translate(x, yy); c.rotate(RJ.gauss(0, 2.2) * J); c.setFont(f"{s.h.id}{it['k']}", size); c.setFillColor(s.ink)
                if s.tool == 'pen': c.setFillAlpha(RJ.uniform(0.86, 1.0))
                if s.tool == 'marker': c.setStrokeColor(s.ink); c.setLineWidth(size * 0.03); c.drawString(0, 0, it['ch'], mode=2)
                else: c.drawString(0, 0, it['ch'])
                c.restoreState()
            w = s.h.W[it['k']][it['ch']] * size
            if it['acc'] and c:
                a, k = it['acc']; up = 0 if it['ch'] in 'xpacemnorsuvwz' else 0.235 * size
                c.setFillColor(s.ink); c.setFont(f'{s.h.id}{k}', size); c.drawString(x + w / 2 + 0.245 * size, yy + up, a)
            x += w + RJ.gauss(0, 0.012 * fs) * J
        return x
    # ---- hand-drawn strokes
    def wob(s, x0, y0, x1, y1, amp, over=1.2):
        r = s.rnd; L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-6: return [(x0, y0)]
        ux, uy = (x1 - x0) / L, (y1 - y0) / L; nx, ny = -uy, ux; a = r.uniform(0, over); b = r.uniform(0, over)
        x0 -= ux * a; y0 -= uy * a; L += a + b; n = max(2, int(L / 14)); offs = [r.gauss(0, amp)]
        for i in range(n): offs.append(offs[-1] * 0.55 + r.gauss(0, amp * 0.8))
        tilt = r.uniform(-1, 1) * min(1.0, L / 60) * s.J
        return [(x0 + ux * L * i / n + nx * (offs[i] + tilt * (i / n - 0.5)), y0 + uy * L * i / n + ny * (offs[i] + tilt * (i / n - 0.5))) for i in range(n + 1)]
    def line(s, x0, y0, x1, y1, w=0.75, amp=0.42):
        c = s.c; r = s.rnd
        if not c: return
        base = s.wob(x0, y0, x1, y1, amp * s.J); L = math.hypot(x1 - x0, y1 - y0) or 1; nx, ny = -(y1 - y0) / L, (x1 - x0) / L
        c.setStrokeColor(s.ink); c.setLineCap(1); c.setLineJoin(1)
        if s.tool != 'pencil':                                   # pen / marker: one continuous stroke
            c.setStrokeAlpha(1); c.setLineWidth(w * r.uniform(0.8, 1.15) * (2.1 if s.tool == 'marker' else 0.85)); p = c.beginPath(); p.moveTo(*base[0])
            for q in base[1:]: p.lineTo(*q)
            c.drawPath(p, stroke=1, fill=0); return
        w *= min(1.9, max(0.5, r.lognormvariate(0, 0.33))); tw = r.uniform(0.7, 1.3); tph = r.uniform(0, 6.28); tfr = r.uniform(0.02, 0.07)
        for ps in range(4):                                      # pencil: overlapping passes with changing pressure and width
            off = r.gauss(0, 0.16 * w / 0.75); pts = [(px + nx * (off + r.gauss(0, 0.05)), py + ny * (off + r.gauss(0, 0.05))) for px, py in base]; d = []
            for a, b in zip(pts[:-1], pts[1:]):
                n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 3)); d += [(a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n) for t in range(n)]
            d.append(pts[-1]); k = 0; press = r.uniform(0.3, 0.6); nd = max(1, len(d) - 1)
            while k < len(d) - 1:
                e = min(len(d) - 1, k + r.randint(1, 4)); press = min(0.72, max(0.14, press + r.gauss(0, 0.13)))
                if r.random() < 0.06: k = e; continue
                tw = min(1.7, max(0.5, tw + r.gauss(0, 0.10))); taper = 0.75 + 0.25 * math.sin(math.pi * min(1, k / nd))
                c.setStrokeAlpha(min(0.8, press * (0.8 + 0.25 * tw))); c.setLineWidth(w * r.uniform(0.45, 0.75) * tw * taper * (1 + 0.25 * math.sin(tph + k * 3 * tfr)))
                p = c.beginPath(); p.moveTo(*d[k])
                for q in d[k + 1:e + 1]: p.lineTo(*q)
                c.drawPath(p, stroke=1, fill=0); k = e
        c.setStrokeAlpha(1)
    def dashes(s, x0, x1, y):
        xx = x0
        while xx < x1 - 4: s.line(xx, y, min(xx + 7, x1), y, 0.8); xx += 11.5
    # ---- flow
    def start_page(s):
        s.col = 0; s.top = s.PH - s.M; s.y = s.top
        if s.c and s.ruled and s.tool != 'pencil':
            s.c.setStrokeColor(HexColor('#a9c4e6')); s.c.setLineWidth(0.5)
            for yy in s.rules(): s.c.line(0, yy, s.PW, yy)
    def end_page(s):
        if s.c and s.divider and s.ncol > 1:
            for j in range(1, s.ncol):
                xm = s.M + j * (s.CW + s.GAP) - s.GAP / 2; yy = s.top; dr = 0
                while yy > s.M + 2:
                    dr = dr * 0.8 + s.rnd.gauss(0, 0.12); L = s.rnd.uniform(0.9, 1.7); s.line(xm + dr, yy, xm + dr + s.rnd.gauss(0, 0.1), yy - L, 1.15, 0.05); yy -= L + s.rnd.uniform(3.0, 4.2)
        if s.c: s.c.showPage()
    def rules(s):
        out = []; yy = s.PH - s.M - s.lead * 0.8
        while yy > s.M * 0.6: out.append(yy); yy -= s.lead
        return out
    def newcol(s, page=False):
        s.col += 1
        if page or s.col >= s.ncol:
            s.end_page(); s.page += 1; s.start_page()
        s.y = s.top
    def need(s, h):
        if s.y - h < s.M - 0.5 and s.y < s.top - 0.5: s.newcol(); return True
        return False
    def X(s): return s.M + s.col * (s.CW + s.GAP)
    def Q(s, h): return math.ceil(h / s.lead - 0.02) * s.lead if s.ruled else h
    def G(s, h): return 0 if s.ruled else h
    def para(s, items, fs, indent=0, first_prefix=None):
        lead = s.lead if s.ruled else max(s.lead * fs / s.fs, fs * 1.17)
        for i, l in enumerate(s.wrap(items, fs, s.CW - indent)):
            s.need(lead)
            if i == 0 and first_prefix: s.text(first_prefix, s.X(), s.y - lead * 0.735, fs)
            s.text(l, s.X() + indent, s.y - lead * 0.735, fs); s.y -= lead
    def table(s, b):
        fs = s.fs; lead = s.lead; padx = fs * 0.33; pady = s.G(fs * 0.2); rows = [[s.parse(cell) for cell in r] for r in b['table']]; nc = max(len(r) for r in rows)
        fr = b.get('widths')
        if not fr or len(fr) != nc:
            full = [r for r in rows if len(r) == nc] or rows; word = lambda cell: max([s.natural(w, fs) for w in s.words(cell)] or [fs])
            lo = [max(word(r[j]) for r in full if j < len(r)) + 2 * padx + fs * 0.6 for j in range(nc)]; nat = [max(s.natural(r[j], fs) for r in full if j < len(r)) + 2 * padx + fs * 0.6 for j in range(nc)]
            spare = s.CW - sum(lo); want = [max(0.0, n - l) for n, l in zip(nat, lo)]
            fr = [l + (spare * w / sum(want) if spare > 0 and sum(want) > 0 else 0) for l, w in zip(lo, want)] if sum(nat) > s.CW else nat
        seg = []                                                   # rows drawn in the current column: (ytop, h, ncells)
        def flush():
            if not seg: return
            x = s.X(); xs = [x]
            for f in fr: xs.append(xs[-1] + s.CW * f / sum(fr))
            ys = [seg[0][0]] + [t - h for t, h, *_ in seg]
            for i, yy in enumerate(ys):
                if 0 < i < len(ys) - 1 or b.get('box'): s.line(x, yy, xs[-1], yy, 1.05 if (i == 1 and seg[0][3]) else 0.75)
            for j in range(len(xs)):
                edge = j in (0, len(xs) - 1); i = 0
                while i < len(seg):
                    ok = lambda r: (b.get('box') if edge else j < seg[r][2])
                    if ok(i):
                        e = i
                        while e + 1 < len(seg) and ok(e + 1): e += 1
                        s.line(xs[j], ys[i] - 0.5, xs[j], ys[e + 1] + 0.8, 0.9); i = e + 1
                    else: i += 1
            seg.clear()
        for ri, r in enumerate(rows):
            xs = [0]
            for f in fr: xs.append(xs[-1] + s.CW * f / sum(fr))
            cl = [s.wrap(cell, fs, (xs[j + 1] if j < len(r) - 1 else xs[-1]) - xs[j] - 2 * padx) for j, cell in enumerate(r)]
            h = max(len(l) for l in cl) * lead + 2 * pady
            if s.y - h < s.M - 0.5 and s.y < s.top - 0.5: flush(); s.newcol()
            for j, ls in enumerate(cl):
                for li, l in enumerate(ls): s.text(l, s.X() + xs[j] + padx, s.y - pady - lead * 0.735 - li * lead, fs)
            seg.append((s.y, h, len(r), ri == 0 and b.get('header', True))); s.y -= h
        flush(); s.y -= s.G(fs * 0.42)
    def layout(s, fs, c=None):
        s.c = c; s.fs = fs; s.lead = fs * 1.17; s.n = 3; s.RJ = random.Random(11); s.rnd = random.Random(5); s.page = 0; s.hard = 0
        s.start_page(); lead = s.lead
        for bi, b in enumerate(s.blocks):
            if 'h1' in b:
                z = fs * 1.42; h = s.Q(z * 1.5); s.need(h + lead); full = s.col == 0 and s.y > s.top - 0.5   # a title at the top of a page spans all columns
                for l in s.wrap(s.parse(b['h1']), z, (s.PW - 2 * s.M) if full else s.CW):
                    e = s.text(l, s.X(), s.y - h + z * 0.42, z); s.line(s.X(), s.y - h + z * 0.12, e, s.y - h + z * 0.12, 1.0); s.y -= h
                s.y -= s.G(fs * 0.3)
                if full: s.top = s.y
            elif 'h2' in b:
                z = fs * 1.22; h = s.Q(z * 1.5); attop = s.y > s.top - 0.5
                if not attop and s.need(h + fs * 0.45 + 3 * lead): attop = True
                if not attop:
                    if s.ruled: s.y -= lead
                    else: s.y -= fs * 0.25; s.dashes(s.X(), s.X() + s.CW, s.y); s.y -= fs * 0.2
                e = s.text(s.parse(b['h2']), s.X() + 1, s.y - h + z * 0.52, z); s.line(s.X(), s.y - h + z * 0.25, e + 1, s.y - h + z * 0.25, 1.0); s.y -= h
            elif 'h3' in b:
                h = s.Q(fs * 1.3); s.need(h + 2 * lead); s.text(s.parse(b['h3']), s.X(), s.y - h + fs * 0.35, fs * 1.04); s.y -= h
            elif 'p' in b: s.para(s.parse(b['p']), fs); s.y -= s.G(fs * 0.35)
            elif 'note' in b: s.para(s.parse(b['note']), fs * 0.92); s.y -= s.G(fs * 0.1)
            elif 'list' in b:
                for i, it in enumerate(b['list']): s.para(s.parse(it), fs, indent=fs * (1.5 if b.get('ordered') else 1.0), first_prefix=s.parse(f'{i+1})' if b.get('ordered') else '•'))
                s.y -= s.G(fs * 0.35)
            elif 'table' in b: s.table(b)
            elif 'space' in b: s.y -= lead * float(b['space'])
            elif 'break' in b: s.newcol(page=(b['break'] == 'page'))
        s.end_page()
        return s.page + 1
    def run(s, out):
        fs = s.fs_req
        if fs == 'fit':
            for strict in (True, False):                         # first try: no word may be broken mid-word
                lo, hi = 4.0, 16.0
                for _ in range(13):
                    mid = (lo + hi) / 2
                    if s.layout(mid) <= s.pages_req and not (strict and s.hard): lo = mid
                    else: hi = mid
                if lo > 5.5: break
            fs = round(lo - 0.02, 2)
        n = s.layout(fs); print(f'font size {fs} pt, {n} page(s), tool {s.tool}')
        vec = out if s.tool != 'pencil' else os.path.join(s.h.tmp, 'vec.pdf')
        c = canvas.Canvas(vec, pagesize=(s.PW, s.PH)); c.setTitle(os.path.splitext(os.path.basename(out))[0]); s.layout(fs, c); c.save()
        if s.tool == 'pencil': s.graphite(vec, out, n)
        if s.h.missing: print('WARNING: not in the font, written as "?" or without their accent:', ' '.join(sorted(s.h.missing)))
        print('wrote', out)
    # ---- pencil: rasterise and add graphite texture
    def graphite(s, vec, out, n):
        import numpy as np, cv2
        from PIL import Image
        pre = os.path.join(s.h.tmp, 'pg')
        if shutil.which('pdftoppm'):
            subprocess.run(['pdftoppm', '-r', str(s.dpi), '-gray', '-png', vec, pre], check=True)
            files = sorted((f for f in os.listdir(s.h.tmp) if f.startswith('pg') and f.endswith('.png')), key=lambda f: int(f[3:-4])); grays = [cv2.imread(os.path.join(s.h.tmp, f), 0) for f in files]
        else:
            import pypdfium2; grays = [np.array(p.render(scale=s.dpi / 72, grayscale=True).to_pil()) for p in pypdfium2.PdfDocument(vec)]
        k = s.dpi / 600.0; pages = []
        for i, g in enumerate(grays):
            rs = np.random.RandomState(3 + i); d = cv2.GaussianBlur(1 - g.astype(np.float32) / 255, (0, 0), 1.0 * k); H, W = d.shape
            def noise(sig, small=1):
                z = cv2.GaussianBlur(rs.randn(H // small + 1, W // small + 1).astype(np.float32), (0, 0), max(0.4, sig)); z = (z - z.mean()) / z.std()
                return cv2.resize(z, (W, H), interpolation=cv2.INTER_CUBIC) if small > 1 else z[:H, :W]
            press = np.clip(0.86 + 0.10 * noise(6, 16) + 0.07 * noise(4, 6), 0.6, 1.0); tooth = noise(1.5 * k)
            grain = np.clip(0.80 + 0.17 * tooth + 0.08 * noise(0.7 * k), 0.35, 1.0); skip = cv2.GaussianBlur((noise(2.2 * k) > 1.75).astype(np.float32), (0, 0), 1.0 * k)
            ink = d * press * grain * (1 - 0.55 * skip)
            ink = np.clip(ink + 0.045 * cv2.GaussianBlur(d, (0, 0), 9 * k) * np.clip(0.6 + 0.5 * noise(10, 20), 0, 1.3), 0, 1)
            if s.smudges:
                sm = np.random.RandomState(40 + i); marks = []; Rr = int(420 * k)
                for _ in range(6):
                    for _t in range(60):
                        cx = sm.randint(Rr + 20, W - Rr - 20); cy = sm.randint(Rr + 20, H - Rr - 20)
                        if d[cy - Rr // 3:cy + Rr // 3, cx - Rr // 3:cx + Rr // 3].mean() > 0.06 and all(abs(cx - mx) + abs(cy - my) > 2 * Rr for mx, my in marks): break
                    else: continue
                    marks.append((cx, cy)); dd = d[cy - Rr:cy + Rr, cx - Rr:cx + Rr]; ang = sm.uniform(-35, 35) + (180 if sm.rand() < 0.5 else 0); L = max(8, int(sm.uniform(70, 130) * k))
                    ker = np.zeros((2 * L + 1, 2 * L + 1), np.float32)
                    for t in range(L): ker[int(round(L + math.sin(math.radians(ang)) * t)), int(round(L + math.cos(math.radians(ang)) * t))] += 1 - t / L
                    smear = cv2.GaussianBlur(cv2.filter2D(dd, -1, ker / ker.sum()), (0, 0), 5 * k)
                    yy, xx = np.mgrid[-Rr:Rr, -Rr:Rr].astype(np.float32); a2 = math.radians(sm.uniform(0, 180)); u = xx * math.cos(a2) + yy * math.sin(a2); v = -xx * math.sin(a2) + yy * math.cos(a2)
                    mask = np.exp(-(u * u / (2 * (sm.uniform(130, 210) * k) ** 2) + v * v / (2 * (sm.uniform(70, 120) * k) ** 2))) * (Rr * Rr > xx * xx + yy * yy)
                    ink[cy - Rr:cy + Rr, cx - Rr:cx + Rr] = np.clip(ink[cy - Rr:cy + Rr, cx - Rr:cx + Rr] * (1 - 0.10 * mask) + sm.uniform(0.75, 1.1) * mask * smear * (0.85 + 0.15 * tooth[cy - Rr:cy + Rr, cx - Rr:cx + Rr]), 0, 1)
            ink = np.clip(ink * s.dark, 0, 1); gr = 58.0
            if s.ruled:
                paper = np.full((H, W, 3), 255, np.float32); t = max(1, int(round(s.dpi / 300)))
                for yy in s.rules(): r0 = int((s.PH - yy) * s.dpi / 72); paper[r0:r0 + t] = (176, 201, 232)
                img = paper * (1 - ink[..., None]) + gr * ink[..., None]; pages.append(Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), 'RGB'))
            else:
                o = np.clip(255 - ink * (255 - gr), 0, 255).astype(np.uint8); o[o > 250] = 255; pages.append(Image.fromarray(o))
        pages[0].save(out, 'PDF', resolution=s.dpi, save_all=True, append_images=pages[1:], quality=88)

PREVIEW = {"page": {"font_size": 20, "margin": 40}, "style": {"tool": "marker", "jitter": 0.4}, "blocks": [
    {"h2": "Font check"}, {"p": "The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor jugs!"},
    {"p": "ABCDEFGHIJKLMNOPQRSTUVWXYZ\nabcdefghijklmnopqrstuvwxyz\n0123456789  . , ; : ! ? ' \" ( ) [ ] - + = / % & @ # $ *"},
    {"p": "eeeeeee aaaaaaa ttttttt ooooooo nnnnnnn sssssss 1111111"},
    {"p": "x̄ ± 1.96·s/√n,  P(a<X<b) = Φ(z_{b}) − Φ(z_{a}),  e^{−λx},  ∑ x_{i}² ≤ ∫ f(x) dx ≠ ∞,  α β γ θ λ μ π σ Δ Σ Ω"},
    {"table": [["What", "Formula", "Note"], ["Mean", "E(X) = 1/λ", "given a mean? λ = 1/mean"], ["Variance", "V = 1/λ²", "σ = 1/λ"]]}]}

if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) == 3 and a[0] == '--preview': R(Hand(a[1]), PREVIEW).run(a[2])
    elif len(a) == 3: R(Hand(a[0]), json.load(open(a[1], encoding='utf-8'))).run(a[2])
    else: sys.exit(__doc__)
