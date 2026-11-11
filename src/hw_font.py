#!/usr/bin/env python3
"""hw_font.py - build a handwriting font (7 rotating variants per character) from a sample.
  template OUT.pdf                      printable 2-page sheet to fill in
  from-template FONT.ttf SCAN [SCAN..]  build the font from photos/scans of the filled sheet
  segment IMAGE WORKDIR                 any handwriting photo -> numbered contact sheets to label
  from-labels FONT.ttf WORKDIR [WORKDIR..]   build from WORKDIR/labels.json written after `segment`
Needs: opencv-python-headless numpy scikit-image fonttools reportlab Hershey-Fonts"""
import cv2, numpy as np, pickle, math, sys, json, os
PX = 0.5; XH = 470; CH = 700; NV = 7          # canvas px per font unit, x-height, cap height, variants
TCHARS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,;:!?'\"()-+=/%&@#$*<>[]") + list("±×÷√∑∫∞≤≥≠≈→πθλμσαβΔΣΦ")
DPI = 300; K = DPI / 72.0                     # template geometry is in points, top-left origin
GW, LW, CW_, RH, GX, GY, ROWS, BASE, XHPT = 135, 15, 40, 48, 36, 62, 14, 15, 11.5
FID = [(24, 24), (572, 24), (24, 752), (572, 752)]; FS = 16
U_PER_PX = XH / (XHPT * K)                    # font units per template pixel

def norm_gray(g):
    """ink map independent of lighting: gray divided by local paper brightness (0..200)"""
    k = max(15, int(min(g.shape) / 40) | 1)
    bg = cv2.GaussianBlur(cv2.morphologyEx(g, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))), (0, 0), k / 2)
    return np.clip(g.astype(np.float32) / np.maximum(bg, 1) * 200, 0, 255).astype(np.uint8)

def trim(a):
    ys, xs = np.where(a)
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

# ------------------------------------------------------------------ template
def cell_rect(i, s):
    """rect (x,y,w,h) in points for char index i (0..55 on a page), sample s (0..2)"""
    r, q = divmod(i, 4)
    return GX + q * GW + LW + s * CW_, GY + r * RH, CW_, RH

def make_template(out):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(out, pagesize=(612, 792)); per = ROWS * 4
    for p in range((len(TCHARS) + per - 1) // per):
        c.setFillGray(0)
        for x, y in FID: c.rect(x, 792 - y - FS, FS, FS, fill=1, stroke=0)
        c.rect(48, 792 - 24 - FS, 8, FS, fill=1, stroke=0)                 # orientation mark
        if p: c.rect(64, 792 - 24 - FS, 8, FS, fill=1, stroke=0)           # page-2 mark
        c.setFont('Helvetica', 8.5)
        c.drawString(84, 792 - 37, f"Handwriting sample {p+1}/2: write each character 3 times, sitting on the lower guide line. Small letters reach the upper line.")
        for i, ch in enumerate(TCHARS[p * per:(p + 1) * per]):
            x, y, w, h = cell_rect(i, 0)
            c.setFillGray(0); c.setFont('Helvetica', 9); c.drawCentredString(x - LW / 2, 792 - y - h + BASE + 2, '' if ch == 'Δ' else ch)
            if ch == 'Δ': c.setStrokeGray(0); c.setLineWidth(0.7); p = c.beginPath(); p.moveTo(x - LW / 2 - 3.2, 792 - y - h + BASE + 2); p.lineTo(x - LW / 2, 792 - y - h + BASE + 8.5); p.lineTo(x - LW / 2 + 3.2, 792 - y - h + BASE + 2); p.close(); c.drawPath(p)   # the built-in label fonts have no capital delta
            for s in range(3):
                x, y, w, h = cell_rect(i, s); Y = 792 - y - h
                c.setStrokeGray(0.74); c.setLineWidth(0.5); c.rect(x, Y, w, h, fill=0, stroke=1)
                c.setStrokeGray(0.84); c.setLineWidth(0.4); c.line(x, Y + BASE, x + w, Y + BASE)
                c.setDash(1.5, 2); c.line(x, Y + BASE + XHPT, x + w, Y + BASE + XHPT); c.setDash()
        c.showPage()
    c.save(); print('wrote', out)

def read_template(path):
    """-> (page_no, {char: [(bitmap, bottom_units), ...]})"""
    g = cv2.imread(path, 0); assert g is not None, path
    if max(g.shape) > 4200: g = cv2.resize(g, None, fx=4200 / max(g.shape), fy=4200 / max(g.shape), interpolation=cv2.INTER_AREA)
    n = norm_gray(g); H, W = g.shape
    f = 1200 / max(H, W); sm = cv2.GaussianBlur(cv2.resize(g, None, fx=f, fy=f, interpolation=cv2.INTER_AREA), (0, 0), 1)   # corner squares: dark vs. brightest nearby paper
    cs, _ = cv2.findContours((sm < 0.5 * cv2.dilate(sm, np.ones((121, 121), np.uint8))).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    sq = []
    for c in cs:
        a = cv2.contourArea(c); (cx, cy), (w, h), _ = cv2.minAreaRect(c)
        if a > 60 and min(w, h) > 0 and max(w, h) / min(w, h) < 1.35 and a / (w * h) > 0.8: sq.append((cx / f, cy / f, a))
    assert len(sq) >= 4, f'{path}: could not find the 4 corner squares - retake the photo flat, whole page visible'
    med = np.median([s[2] for s in sorted(sq, key=lambda s: -s[2])[:4]]); sq = [s for s in sq if 0.4 * med < s[2] < 2.5 * med]
    P = np.array([s[:2] for s in sq], np.float32)
    corners = [P[np.argmin(P[:, 0] + P[:, 1])], P[np.argmax(P[:, 0] - P[:, 1])], P[np.argmin(P[:, 0] - P[:, 1])], P[np.argmax(P[:, 0] + P[:, 1])]]
    dst = np.array([[(x + FS / 2) * K, (y + FS / 2) * K] for x, y in FID], np.float32); best = None
    for rot in ([0, 1, 2, 3], [1, 3, 0, 2], [3, 2, 1, 0], [2, 0, 3, 1]):       # find the orientation mark
        M = cv2.getPerspectiveTransform(np.array([corners[i] for i in rot], np.float32), dst)
        w = cv2.warpPerspective(n, M, (int(612 * K), int(792 * K)), borderValue=200)
        dark = w[int(26 * K):int(38 * K), int(49 * K):int(55 * K)].mean()
        if best is None or dark < best[0]: best = (dark, w)
    w = best[1]; page = 1 if w[int(26 * K):int(38 * K), int(65 * K):int(71 * K)].mean() < 110 else 0
    out = {}; per = ROWS * 4
    for i, ch in enumerate(TCHARS[page * per:(page + 1) * per]):
        for s in range(3):
            x, y, cw, h = cell_rect(i, s); m = 3.2
            x0, y0, x1, y1 = int((x + m) * K), int((y + m) * K), int((x + cw - m) * K), int((y + h - m) * K)
            ink = (w[y0:y1, x0:x1] < 128).astype(np.uint8)
            nc, lab, st, _ = cv2.connectedComponentsWithStats(ink)
            for j in range(1, nc):
                if st[j, 4] < 14: ink[lab == j] = 0
            if ink.sum() < 45: continue
            ys, xs = np.where(ink); bm = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            base_px = (y + h - BASE) * K - y0
            f = U_PER_PX * PX
            b = cv2.resize(bm.astype(np.float32), None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
            b = cv2.GaussianBlur(np.pad(b, 12), (0, 0), 0.55 * f) > 0.5
            out.setdefault(ch, []).append((b, (base_px - (ys.max() + 1)) * U_PER_PX))
    return page, out

# ------------------------------------------------------------------ free-form photo
def segment(image, wd):
    os.makedirs(wd, exist_ok=True); g = cv2.imread(image, 0); assert g is not None, image
    if max(g.shape) > 3000: g = cv2.resize(g, None, fx=3000 / max(g.shape), fy=3000 / max(g.shape), interpolation=cv2.INTER_AREA)
    bl = cv2.GaussianBlur(g, (0, 0), 8); paper = (bl > 0.6 * np.percentile(bl, 97)).astype(np.uint8)
    nl, lab, st, _ = cv2.connectedComponentsWithStats(paper)
    if nl > 1:
        paper = (lab == 1 + np.argmax(st[1:, 4])).astype(np.uint8)
        paper = cv2.erode(cv2.morphologyEx(paper, cv2.MORPH_CLOSE, np.ones((151, 151), np.uint8)), np.ones((21, 21), np.uint8))
    n = norm_gray(g); ink = ((n < 124) & (paper > 0)).astype(np.uint8)
    _, _, st0, _ = cv2.connectedComponentsWithStats(ink)
    hs = [s[3] for s in st0[1:] if s[4] > 20 and s[3] < g.shape[0] / 8]
    S = float(np.median(hs)) / 30 if hs else 1.0                    # scale relative to ~30px letters
    L = int(90 * S) | 1
    lines = cv2.dilate(cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, L), np.uint8)), np.ones((7, 3), np.uint8)) | \
            cv2.dilate(cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((L, 1), np.uint8)), np.ones((3, 7), np.uint8))
    txt = ink & (1 - lines)                                         # ruled/table lines removed
    nl, lab, st, _ = cv2.connectedComponentsWithStats(txt, connectivity=8); comps = []
    for i in range(1, nl):
        x, y, w, h, a = st[i]
        if a < 12 * S * S or w > 260 * S or h > 120 * S: continue
        comps.append(dict(ids=[i], x=int(x), y=int(y), w=int(w), h=int(h), a=int(a)))
    comps.sort(key=lambda c: c['a']); used = [False] * len(comps)
    for i, c in enumerate(comps):                                   # attach dots / stacked bars (i j = : ; ! ?)
        if c['h'] < 16 * S or c['a'] < 90 * S * S:
            best = None
            for j, d in enumerate(comps):
                if j == i or used[j]: continue
                o = min(c['x'] + c['w'], d['x'] + d['w']) - max(c['x'], d['x'])
                gap = max(d['y'] - (c['y'] + c['h']), c['y'] - (d['y'] + d['h']))
                if o >= 0.5 * min(c['w'], d['w']) and gap < 22 * S and d['h'] < 75 * S and (best is None or gap < best[0]): best = (gap, j)
            if best:
                d = comps[best[1]]; x0, y0 = min(c['x'], d['x']), min(c['y'], d['y'])
                x1, y1 = max(c['x'] + c['w'], d['x'] + d['w']), max(c['y'] + c['h'], d['y'] + d['h'])
                d.update(ids=d['ids'] + c['ids'], x=x0, y=y0, w=x1 - x0, h=y1 - y0, a=d['a'] + c['a']); used[i] = True
    comps = [c for i, c in enumerate(comps) if not used[i] and c['a'] >= 25 * S * S]
    comps.sort(key=lambda c: c['y'] + c['h'] / 2); rows = []; cur = []; prev = 0
    for c in comps:                                                 # reading order
        cy = c['y'] + c['h'] / 2
        if cur and cy - prev > 9 * S and len(cur) > 3: rows.append(cur); cur = []
        cur.append(c); prev = cy
    rows.append(cur); comps = [c for r in rows for c in sorted(r, key=lambda c: c['x'])]
    pickle.dump((comps, lab, n), open(f'{wd}/comps.pkl', 'wb'))
    C, Z = 14, 84
    for p in range(0, len(comps), C * 8):
        sheet = np.full((8 * (Z + 22), C * Z), 255, np.uint8)
        for k, c in enumerate(comps[p:p + C * 8]):
            m = np.isin(lab[c['y']:c['y'] + c['h'], c['x']:c['x'] + c['w']], c['ids']).astype(np.uint8) * 255
            s = min(1.6 / S, (Z - 10) / max(c['w'], c['h']))
            m = cv2.resize(m, (max(1, int(c['w'] * s)), max(1, int(c['h'] * s))))
            r, q = divmod(k, C); oy = r * (Z + 22) + (Z - m.shape[0]) // 2; ox = q * Z + (Z - m.shape[1]) // 2
            sheet[oy:oy + m.shape[0], ox:ox + m.shape[1]] = 255 - m
            cv2.putText(sheet, str(p + k), (q * Z + 4, r * (Z + 22) + Z + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 90, 1)
            cv2.rectangle(sheet, (q * Z, r * (Z + 22)), (q * Z + Z - 1, r * (Z + 22) + Z + 21), 200, 1)
        cv2.imwrite(f'{wd}/sheet{p // (C * 8)}.png', sheet)
    print(len(comps), 'pieces ->', f'{wd}/sheet*.png (reading order). Now write {wd}/labels.json')

def spec(ch):
    """vertical placement for free-form samples: ('fit', bottom, top) or ('w', centre_y, width)"""
    for chars, sp in (('acemnorsuvwxzσαεικνοπτυω', ('fit', 0, XH)), ('bdhklδθλ', ('fit', 0, 720)), ('t', ('fit', 0, 640)), ('f', ('fit', -60, 720)),
                      ('gpqyγηρχ', ('fit', -230, XH)), ('μ', ('fit', -40, 490)), ('βζξφψ', ('fit', -220, 720)), ('i', ('fit', 0, 670)), ('j', ('fit', -230, 670)),
                      ('()[]{}', ('fit', -150, 780)), ('/', ('fit', -60, 760)), ('∫', ('fit', -130, 770)), ('<>', ('fit', 80, 460)), ('≥≤', ('fit', 40, 520)),
                      ('±', ('fit', 0, 520)), ('+', ('fit', 60, 480)), (':', ('fit', 10, 420)), (';', ('fit', -120, 420)), ('.', ('fit', 0, 90)), (',', ('fit', -120, 80)),
                      ("'\"", ('fit', 560, 770)), ('-', ('w', 270, 300)), ('=', ('w', 270, 370)), ('→', ('w', 270, 580)), ('~', ('w', 270, 420))):
        if ch in chars: return sp
    return ('fit', 0, CH)

def read_labels(wd):
    """labels.json: {"labels": {"a": [12, 57], ...}, "largest": {"e": [202]}, "splits": {"370": "ch"}}
    labels  = piece numbers that are ONE clean character, best first
    largest = pieces where only the biggest blob is the character (e.g. e with a stray bar above it)
    splits  = a piece holding several joined letters, cut at the thinnest points into those letters"""
    comps, lab, n = pickle.load(open(f'{wd}/comps.pkl', 'rb')); J = json.load(open(f'{wd}/labels.json')); KK = 4
    def crop(c, ids=None):
        ids = ids or c['ids']; p = 4
        x0, y0, x1, y1 = max(0, c['x'] - p), max(0, c['y'] - p), c['x'] + c['w'] + p, c['y'] + c['h'] + p
        m = cv2.dilate(np.isin(lab[y0:y1, x0:x1], ids).astype(np.uint8), np.ones((5, 5), np.uint8))
        g = cv2.resize(n[y0:y1, x0:x1], None, fx=KK, fy=KK, interpolation=cv2.INTER_CUBIC)
        return trim((g < 122) & (cv2.resize(m, (g.shape[1], g.shape[0]), interpolation=cv2.INTER_NEAREST) > 0))
    def place(ch, a):
        sp = spec(ch); f = (sp[2] - sp[1]) * PX / a.shape[0] if sp[0] == 'fit' else sp[2] * PX / a.shape[1]
        b = cv2.resize(a.astype(np.float32), None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
        b = cv2.GaussianBlur(np.pad(b, 12), (0, 0), max(0.7, 0.55 * f)) > 0.5
        return b, (sp[1] if sp[0] == 'fit' else sp[1] - trim(b).shape[0] / PX / 2)
    out = {}
    for ch, ids in J.get('labels', {}).items():
        for i in ids: out.setdefault(ch, []).append(place(ch, crop(comps[i])))
    for ch, ids in J.get('largest', {}).items():
        for i in ids:
            c = comps[i]; big = [c['ids'][int(np.argmax([(lab == j).sum() for j in c['ids']]))]]
            out.setdefault(ch, []).append(place(ch, crop(c, big)))
    for i, word in J.get('splits', {}).items():
        a = crop(comps[int(i)]); prof = cv2.GaussianBlur(a.sum(0).astype(np.float32).reshape(1, -1), (0, 0), 3).ravel(); Wd = a.shape[1]; cuts = [0]
        for k in range(1, len(word)):
            c0 = int(Wd * k / len(word)); r = int(Wd / len(word) * 0.38); cuts.append(c0 - r + int(np.argmin(prof[c0 - r:c0 + r])))
        cuts.append(Wd)
        for k, ch in enumerate(word):
            if ch != '_' and a[:, cuts[k]:cuts[k + 1]].any(): out.setdefault(ch, []).append(place(ch, trim(a[:, cuts[k]:cuts[k + 1]])))
    return out

# ------------------------------------------------------------------ glyph set
def strokew(b):
    from skimage.morphology import skeletonize
    dt = cv2.distanceTransform(b.astype(np.uint8), cv2.DIST_L2, 5); v = dt[skeletonize(b > 0)]
    return 2 * float(np.median(v)) if len(v) else 0.0

def warp(b, seed, amp=3.3):
    r = np.random.RandomState(seed); b = np.pad(b.astype(np.float32), 24); h, w = b.shape
    fld = lambda: cv2.resize(r.randn(h // 45 + 3, w // 45 + 3).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC) * amp
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32); X = xx - w / 2; Y = yy - h / 2
    ang = math.radians(r.uniform(-2.5, 2.5)); sh = r.uniform(-0.06, 0.06); sx = r.uniform(0.95, 1.05); sy = r.uniform(0.97, 1.03)
    out = cv2.remap(b, (X * math.cos(ang) - Y * math.sin(ang) + sh * Y) / sx + w / 2 + fld(), (X * math.sin(ang) + Y * math.cos(ang)) / sy + h / 2 + fld(), cv2.INTER_LINEAR)
    return cv2.GaussianBlur(out, (0, 0), 0.8) > 0.5

def build_glyphs(samples):
    """samples {ch: [(bitmap, bottom_units)]} -> GL {ch: [NV x dict(bm,bottom,xoff,adv)]}, drawing whatever is missing"""
    from HersheyFonts import HersheyFonts
    samples = {ch: [(b, bt) for b, bt in v if b.any()] for ch, v in samples.items()}; samples = {c: v for c, v in samples.items() if v}
    WT = float(np.median([strokew(b) for v in samples.values() for b, _ in v])); print('stroke width', round(WT / PX), 'units;', len(samples), 'characters from the sample')
    def harmon(b):
        d = (strokew(b) - WT) / 2; r = int(round(min(abs(d) * 0.8, 3 if d > 0 else 7)))
        if r >= 1:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)); b2 = (cv2.erode if d > 0 else cv2.dilate)(b.astype(np.uint8), k) > 0
            if d < 0 or cv2.connectedComponents(b2.astype(np.uint8))[0] <= cv2.connectedComponents(b.astype(np.uint8))[0]: b = b2
        return b
    GL = {}
    for ch, v in samples.items():
        v = [(harmon(b), bt) for b, bt in v][:NV]; k = 0; n0 = len(v)
        while len(v) < NV: v.append((warp(v[k % n0][0], 1000 + ord(ch) * 7 + len(v)), v[k % n0][1])); k += 1
        GL[ch] = [dict(bm=trim(b), bottom=bt, xoff=None, adv=None) for b, bt in v]
    # ---- everything below draws characters the sample did not contain
    OX, OY = 500, 950; CWd, CHt = int(2400 * PX), int(1350 * PX); RA = 1.9 * min(1.0, max(0.35, WT / 43))
    P = lambda *p: ('p', [tuple(map(float, q)) for q in p]); C = lambda *p: ('c', [tuple(map(float, q)) for q in p])
    def O(cx, cy, rx, ry, a0=0, a1=360, n=28): return ('c', [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)])
    DOT = lambda x, y, s=1.25: ('d', [(x, y)], s)
    def dense(st, step=6):
        p = np.array(st[1], float)
        if st[0] == 'd': return p
        if st[0] == 'c' and len(p) > 2:
            p = np.vstack([p[-2], p, p[1]]) if (np.allclose(p[0], p[-1]) and len(p) > 3) else np.vstack([2 * p[0] - p[1], p, 2 * p[-1] - p[-2]]); out = []
            for i in range(1, len(p) - 2):
                p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
                for t in np.linspace(0, 1, max(2, int(np.linalg.norm(p2 - p1) / step)), endpoint=False):
                    out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
            return np.array(out + [p[-2]])
        out = [p[0]]
        for a, b in zip(p[:-1], p[1:]):
            for t in np.linspace(0, 1, max(1, int(np.linalg.norm(b - a) / step)) + 1)[1:]: out.append(a + (b - a) * t)
        return np.array(out)
    def render(strokes, seed, pen, jit):
        r = np.random.RandomState(seed % (2 ** 31)); img = np.zeros((CHt, CWd), np.uint8); pen *= 1.22; jit *= 1.8
        waves = [(r.uniform(5, 9) * jit, r.uniform(-1, 1) / r.uniform(90, 180), r.uniform(-1, 1) / r.uniform(90, 180), r.uniform(0, 6.28), r.uniform(0, 6.28)) for _ in range(3)]
        allp = np.vstack([np.array(s[1], float) for s in strokes]); cx, cy = allp[:, 0].mean(), allp[:, 1].mean()
        ang = math.radians(r.uniform(-2, 2) * jit); sh = r.uniform(-0.04, 0.05) * jit; sx = r.uniform(0.95, 1.05); sy = r.uniform(0.97, 1.03)
        for st in strokes:
            d = dense(st); off = r.uniform(-7, 7, 2) * jit; X = d[:, 0] - cx; Y = d[:, 1] - cy
            x = (X * math.cos(ang) - Y * math.sin(ang) + sh * Y) * sx + cx + off[0]; y = (X * math.sin(ang) + Y * math.cos(ang)) * sy + cy + off[1]
            for a, kx, ky, p1, p2 in waves: x = x + a * np.sin(kx * d[:, 0] + ky * d[:, 1] + p1); y = y + a * np.cos(kx * d[:, 0] - ky * d[:, 1] + p2)
            ps = st[2] if st[0] == 'd' else 1.0; ph = r.uniform(0, 6.28)
            for k in range(len(x)):
                rad = WT / 2 * pen * ps * (1 + 0.2 * math.sin(ph + k * 0.06) + 0.09 * math.sin(ph * 3 + k * 0.21))
                cv2.circle(img, (int(round((x[k] + OX) * PX)), int(round((OY - y[k]) * PX))), max(1, int(round(rad))), 1, -1)
        f = cv2.GaussianBlur(img.astype(np.float32), (0, 0), 1.3)
        f += RA * (cv2.GaussianBlur(r.randn(*img.shape).astype(np.float32), (0, 0), 2.2) * 0.84 + cv2.GaussianBlur(r.randn(*img.shape).astype(np.float32), (0, 0), 7) * 2.24)
        out = (f > 0.5) & (cv2.dilate(img, np.ones((9, 9), np.uint8)) > 0); nc, lab, st, _ = cv2.connectedComponentsWithStats(out.astype(np.uint8))
        for i in range(1, nc):
            if st[i, 4] < 60 * min(1, WT / 43) ** 2: out[lab == i] = False
        return out
    def recsyn(b, keepx=False, adv=None):
        ys, xs = np.where(b); t = b[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        return dict(bm=t, bottom=OY - (ys.max() + 1) / PX, xoff=(xs.min() / PX - OX) if keepx else None, adv=adv)
    def syn(name, strokes, pen=1.0, keepx=False, adv=None, jit=1.0):
        if name not in GL: GL[name] = [recsyn(render(strokes, sum(map(ord, name)) * 131 + 31 * k, pen, jit), keepx, adv) for k in range(NV)]
    HF = {}
    def hershey(font, c, sx=27.5, sy=33.3):
        if font not in HF: HF[font] = HersheyFonts(); HF[font].load_default_font(font)
        st = [list(s) for s in HF[font].strokes_for_text(c)]; x0 = min(p[0] for s in st for p in s); out = []
        for s in st:
            pts = [((x - x0) * sx, (9 - y) * sy) for x, y in s]; pts = pts * 2 if len(pts) == 1 else pts
            out.append(('c' if len(pts) >= 6 else 'p', pts))
        return out
    A = 270; bar = lambda y, x0=0, x1=420: P((x0, y), (x1, y)); til = lambda y, w=420: C((0, y - 30), (w * .25, y + 45), (w * .5, y), (w * .75, y - 45), (w, y + 30))
    for c in 'ABCDEFGHJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789%()/:;<=>': syn(c, hershey('futural', c))
    syn('I', [P((40, 700), (280, 700)), P((160, 700), (160, 0)), P((40, 0), (280, 0))]); syn('-', [bar(A, 0, 300)])
    syn('!', [P((70, 720), (70, 230)), DOT(70, 25)]); syn('?', [C((30, 560), (80, 690), (220, 720), (320, 620), (300, 470), (190, 360), (170, 220)), DOT(170, 25)])
    syn('"', [P((40, 770), (40, 570)), P((190, 770), (190, 570))]); syn("'", [P((40, 770), (40, 570))]); syn('.', [DOT(60, 35)]); syn(',', [C((80, 60), (90, -20), (30, -130))]); syn('`', [P((30, 770), (130, 630))])
    syn('*', [P((170, 710), (170, 430)), P((50, 640), (290, 500)), P((50, 500), (290, 640))], pen=0.85)
    syn('#', [P((170, 700), (110, 0)), P((400, 700), (340, 0)), P((20, 470), (500, 470)), P((0, 230), (480, 230))], pen=0.8)
    syn('$', hershey('futural', '$', 36, 36), pen=0.8); syn('&', hershey('futural', '&', 36, 34), pen=0.85); syn('@', hershey('futural', '@', 40, 40), pen=0.7)
    syn('+', [bar(A), P((210, 60), (210, 480))]); syn('[', [P((250, 790), (60, 790), (60, -150), (250, -150))]); syn(']', [P((0, 790), (190, 790), (190, -150), (0, -150))])
    syn('\\', [P((0, 760), (280, -60))]); syn('^', [P((20, 480), (170, 700), (320, 480))]); syn('_', [P((0, -120), (480, -120))]); syn('|', [P((60, -150), (60, 800))], jit=0.25); syn('~', [til(A)])
    syn('{', [C((280, 800), (190, 790), (160, 720), (160, 420), (140, 340), (50, 315), (140, 290), (160, 210), (160, -90), (190, -140), (280, -150))])
    syn('}', [C((0, 800), (90, 790), (120, 720), (120, 420), (140, 340), (230, 315), (140, 290), (120, 210), (120, -90), (90, -140), (0, -150))])
    syn('‘', [C((50, 570), (40, 650), (100, 760))]); syn('’', [C((90, 770), (100, 680), (40, 580))])
    syn('“', [C((50, 570), (40, 650), (100, 760)), C((210, 570), (200, 650), (260, 760))]); syn('”', [C((90, 770), (100, 680), (40, 580)), C((250, 770), (260, 680), (200, 580))])
    syn('–', [bar(A, 0, 380)]); syn('—', [bar(A, 0, 760)]); syn('…', [DOT(60, 35), DOT(280, 35), DOT(500, 35)]); syn('•', [DOT(90, A, 1.9)])
    syn('°', [O(110, 640, 75, 75)], pen=0.8); syn('′', [P((80, 790), (30, 570))]); syn('″', [P((80, 790), (30, 570)), P((230, 790), (180, 570))])
    syn('−', [bar(A)]); syn('×', [P((30, 90), (390, 450)), P((30, 450), (390, 90))]); syn('÷', [bar(A), DOT(210, 450), DOT(210, 90)]); syn('·', [DOT(70, A)]); syn('∘', [O(140, A, 95, 95)], pen=0.85)
    syn('∗', [P((170, 420), (170, 120)), P((40, 345), (300, 195)), P((40, 195), (300, 345))], pen=0.85); syn('±', [bar(330, 0, 400), P((200, 520), (200, 140)), bar(20, 0, 400)]); syn('∓', [bar(480, 0, 400), bar(190, 0, 400), P((200, 370), (200, 10))])
    syn('≠', [bar(350), bar(190), P((120, 40), (300, 500))]); syn('≈', [til(350), til(190)]); syn('≃', [til(360), bar(170)]); syn('≅', [til(500), bar(300), bar(110)], pen=0.9); syn('≡', [bar(470), bar(A), bar(70)], pen=0.9)
    syn('≤', [P((400, 540), (20, 360), (400, 180)), bar(30, 20, 400)]); syn('≥', [P((20, 540), (400, 360), (20, 180)), bar(30, 20, 400)])
    syn('≪', [P((300, 480), (0, A), (300, 60)), P((570, 480), (270, A), (570, 60))]); syn('≫', [P((0, 480), (300, A), (0, 60)), P((270, 480), (570, A), (270, 60))])
    syn('∝', [C((430, 400), (350, 410), (260, 330), (160, 180), (90, 140), (35, 190), (25, A), (40, 350), (95, 400), (160, 370), (260, 210), (350, 130), (430, 145))])
    syn('∞', [('c', [(300 + 270 * math.cos(t), A + 150 * math.sin(2 * t)) for t in np.linspace(0, 2 * math.pi, 41)])]); syn('√', [P((0, 300), (70, 340), (190, 0), (330, 790), (600, 790))])
    syn('Σ', [P((440, 640), (440, 720), (20, 720), (250, 345), (20, -30), (440, -30), (440, 50))]); syn('∏', [P((0, 720), (540, 720)), P((100, 720), (100, -30)), P((440, 720), (440, -30))])
    INT = lambda dx=0: C((330 + dx, 800), (285 + dx, 860), (225 + dx, 840), (200 + dx, 740), (170 + dx, 340), (150 + dx, -60), (120 + dx, -170), (60 + dx, -190), (10 + dx, -130))
    syn('∫', [INT()]); syn('∮', [INT(), O(172, 330, 115, 115)])
    syn('∂', [C((80, 610), (170, 710), (280, 690), (340, 580), (360, 400), (330, 180), (250, 40), (150, 0), (60, 60), (40, 180), (90, 300), (190, 350), (290, 310), (350, 215))])
    syn('∇', [P((0, 700), (480, 700), (240, 0), (0, 700))]); syn('∆', [P((0, 0), (240, 700), (480, 0), (0, 0))])
    EL = lambda: C((400, 480), (230, 480), (90, 430), (30, A), (90, 110), (230, 60), (400, 60)); ELr = lambda: C((20, 480), (190, 480), (330, 430), (390, A), (330, 110), (190, 60), (20, 60))
    syn('∈', [EL(), P((40, A), (360, A))]); syn('∉', [EL(), P((40, A), (360, A)), P((110, -20), (330, 570))]); syn('∋', [ELr(), P((60, A), (380, A))])
    SUB = lambda dy=0: C((420, 470 + dy), (220, 470 + dy), (60, 400 + dy), (30, A + dy), (60, 140 + dy), (220, 70 + dy), (420, 70 + dy)); SUP = lambda dy=0: C((0, 470 + dy), (200, 470 + dy), (360, 400 + dy), (390, A + dy), (360, 140 + dy), (200, 70 + dy), (0, 70 + dy))
    syn('⊂', [SUB()]); syn('⊃', [SUP()]); syn('⊆', [SUB(80), bar(10, 10, 420)]); syn('⊇', [SUP(80), bar(10, 0, 410)])
    syn('∪', [C((30, 530), (30, 220), (80, 80), (220, 30), (360, 80), (410, 220), (410, 530))]); syn('∩', [C((30, 20), (30, 330), (80, 470), (220, 520), (360, 470), (410, 330), (410, 20))])
    syn('∅', [O(230, 340, 200, 250), P((60, -20), (400, 700))]); syn('∖', [P((0, 640), (260, -20))])
    syn('∀', [P((0, 700), (240, 0), (480, 700)), P((85, 470), (395, 470))]); syn('∃', [P((40, 700), (420, 700), (420, 0), (40, 0)), P((90, 350), (420, 350))])
    syn('¬', [P((20, 330), (400, 330), (400, 150))]); syn('∧', [P((20, 30), (220, 520), (420, 30))]); syn('∨', [P((20, 520), (220, 30), (420, 520))])
    syn('⊕', [O(250, A, 230, 230), bar(A, 60, 440), P((250, 80), (250, 460))], pen=0.85); syn('⊗', [O(250, A, 230, 230), P((110, 130), (390, 410)), P((110, 410), (390, 130))], pen=0.85)
    syn('⊥', [bar(20, 0, 440), P((220, 20), (220, 560))]); syn('∥', [P((60, -80), (60, 740)), P((250, -80), (250, 740))], jit=0.3); syn('∣', [P((60, -80), (60, 740))], jit=0.25)
    syn('∠', [P((440, 520), (20, 20), (470, 20))]); syn('∴', [DOT(220, 460), DOT(60, 110), DOT(380, 110)]); syn('∵', [DOT(220, 110), DOT(60, 460), DOT(380, 460)])
    syn('ℓ', [C((40, 200), (180, 330), (280, 560), (250, 720), (180, 740), (130, 640), (130, 200), (160, 50), (240, 0), (330, 70))])
    syn('ℝ', [P((40, 0), (40, 700)), P((140, 0), (140, 700)), C((40, 700), (300, 700), (410, 640), (430, 540), (400, 430), (300, 380), (40, 380)), P((250, 380), (450, 0))], pen=0.7)
    syn('ℕ', [P((40, 0), (40, 700), (140, 700)), P((40, 700), (420, 0), (520, 0)), P((140, 700), (520, 0)), P((520, 0), (520, 700))], pen=0.7)
    syn('ℤ', [P((30, 700), (470, 700)), P((470, 700), (140, 0)), P((370, 700), (40, 0)), P((40, 0), (490, 0))], pen=0.7)
    syn('→', [bar(A, 0, 580), P((400, 430), (580, A), (400, 110))]); syn('←', [bar(A, 0, 580), P((180, 430), (0, A), (180, 110))]); syn('↔', [bar(A, 0, 640), P((170, 420), (0, A), (170, 120)), P((470, 420), (640, A), (470, 120))])
    syn('↑', [P((180, -20), (180, 640)), P((20, 470), (180, 640), (340, 470))]); syn('↓', [P((180, 660), (180, 0)), P((20, 170), (180, 0), (340, 170))])
    syn('⇒', [bar(345, 0, 500), bar(195, 0, 500), P((400, 490), (620, A), (400, 50))]); syn('⇐', [bar(345, 120, 620), bar(195, 120, 620), P((220, 490), (0, A), (220, 50))])
    syn('⇔', [bar(345, 120, 560), bar(195, 120, 560), P((210, 490), (0, A), (210, 50)), P((470, 490), (680, A), (470, 50))])
    syn('⌊', [P((60, 780), (60, -150), (250, -150))]); syn('⌋', [P((190, 780), (190, -150), (0, -150))]); syn('⌈', [P((60, -150), (60, 780), (250, 780))]); syn('⌉', [P((190, -150), (190, 780), (0, 780))])
    syn('⟨', [P((230, 780), (40, 315), (230, -150))]); syn('⟩', [P((0, 780), (190, 315), (0, -150))])
    for m, st in {'̄': [P((-400, 600), (-90, 600))], '̂': [P((-400, 570), (-245, 690), (-90, 570))], '̃': [C((-400, 580), (-320, 650), (-245, 610), (-170, 570), (-90, 640))],
                  '́': [P((-290, 560), (-190, 690))], '̀': [P((-300, 690), (-200, 560))], '̈': [DOT(-320, 620, 0.9), DOT(-170, 620, 0.9)]}.items(): syn(m, st, keepx=True, adv=0, pen=0.8)
    for g, c in {'α': 'a', 'β': 'b', 'χ': 'c', 'δ': 'd', 'ε': 'e', 'φ': 'f', 'γ': 'g', 'η': 'h', 'ι': 'i', 'κ': 'k', 'λ': 'l', 'μ': 'm', 'ν': 'n', 'ο': 'o', 'π': 'p', 'ϑ': 'q', 'ρ': 'r', 'σ': 's', 'τ': 't', 'υ': 'u', 'ω': 'w', 'ξ': 'x', 'ψ': 'y', 'ζ': 'z',
                 'Γ': 'G', 'Δ': 'D', 'Θ': 'Q', 'Λ': 'L', 'Ξ': 'X', 'Π': 'P', 'Φ': 'F', 'Ψ': 'Y', 'Ω': 'W'}.items(): syn(g, hershey('greek', c))
    syn('θ', [O(170, 350, 150, 350), P((25, 350), (315, 350))]); syn('ς', [C((330, 430), (230, 480), (110, 440), (50, 320), (80, 180), (230, 90), (300, 20), (280, -90), (200, -130))])
    syn('ϵ', [C((330, 430), (200, 470), (70, 400), (40, 235), (70, 80), (200, 10), (330, 50)), P((50, 240), (260, 240))]); syn('ϕ', [O(190, 235, 170, 235), P((190, 700), (190, -220))])
    def compose(name, parts):
        if name in GL: return
        out = []
        for k in range(NV):
            img = np.zeros((CHt, CWd), np.uint8)
            for src, sc, x, y in parts:
                g = GL[src][(k * 3 + 1) % NV]; b = cv2.resize(g['bm'].astype(np.float32), None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA) > 0.42
                if sc < 0.9: b = cv2.dilate(b.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
                py = max(0, min(int((OY - (y + g['bottom'] * sc)) * PX) - b.shape[0], CHt - b.shape[0])); px = int((x + OX) * PX)
                img[py:py + b.shape[0], px:px + b.shape[1]] |= b.astype(np.uint8)[:, :CWd - px]
            out.append(recsyn(img > 0))
        GL[name] = out
    for s, c in zip('⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ', '0123456789+−=()ni'): compose(s, [(c, 0.6, 0, 330 if c not in '+−=' else 300)])
    for s, c in zip('₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ᵢₙₓₐₑₒⱼₖₘ', '0123456789+−=()inxaeojkm'): compose(s, [(c, 0.6, 0, -170)])
    for f, (n, d) in {'½': '12', '⅓': '13', '¼': '14', '¾': '34', '⅔': '23'}.items(): compose(f, [(n, 0.55, 0, 330), ('/', 0.95, 170, 0), (d, 0.55, 400, -20)])
    compose('∬', [('∫', 1, 0, 0), ('∫', 1, 190, 0)]); GL.setdefault('∑', GL['Σ'])
    return GL

ALIAS = {'Α': 'A', 'Β': 'B', 'Ε': 'E', 'Ζ': 'Z', 'Η': 'H', 'Ι': 'I', 'Κ': 'K', 'Μ': 'M', 'Ν': 'N', 'Ο': 'O', 'Ρ': 'P', 'Τ': 'T', 'Υ': 'Y', 'Χ': 'X', 'µ': 'μ', '∙': '·', '⋅': '·', '∼': '~', '‖': '∥', '‐': '-', '‑': '-', '⁄': '/', '∕': '/', '∶': ':', '⟶': '→'}

def write_font(GL, out, family):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.agl import UV2AGL
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    gname = lambda ch: UV2AGL.get(ord(ch)) or 'uni%04X' % ord(ch)
    def outline(g):
        bm = np.pad(g['bm'].astype(np.uint8), 2); H = g['bm'].shape[0]; lsb = 40 if g['xoff'] is None else g['xoff']
        cs, _ = cv2.findContours(bm, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE); pen = TTGlyphPen(None)
        for c in cs:
            if cv2.contourArea(c) < 25: continue
            c = cv2.approxPolyDP(c, 1.1, True).reshape(-1, 2)
            if len(c) >= 4: pen.qCurveTo(*[(int(round((x - 2) / PX + lsb)), int(round(g['bottom'] + (H - (y - 2)) / PX))) for x, y in c], None); pen.closePath()
        return pen.glyph(), (g['adv'] if g['adv'] is not None else int(g['bm'].shape[1] / PX + lsb + 38))
    order = ['.notdef', 'space'] + [f'space.alt{i}' for i in range(1, NV)]; glyphs = {}; adv = {'.notdef': 500}; cmap = {32: 'space', 0xA0: 'space'}
    p = TTGlyphPen(None); p.moveTo((60, 0)); p.lineTo((60, 700)); p.lineTo((440, 700)); p.lineTo((440, 0)); p.closePath(); glyphs['.notdef'] = p.glyph()
    for nm, w in zip(order[1:], (270, 300, 245, 285, 255, 310, 265)): glyphs[nm] = TTGlyphPen(None).glyph(); adv[nm] = w
    CL = [['space']] + [[f'space.alt{i}'] for i in range(1, NV)]
    for ch, vs in GL.items():
        base = gname(ch); cmap[ord(ch)] = base
        for k, g in enumerate(vs):
            nm = base if k == 0 else f'{base}.alt{k}'; glyphs[nm], adv[nm] = outline(g); order.append(nm); CL[k].append(nm)
    for a, b in ALIAS.items():
        if b in GL and ord(a) not in cmap: cmap[ord(a)] = gname(b)
    fb = FontBuilder(1000, isTTF=True); fb.setupGlyphOrder(order); fb.setupCharacterMap(cmap); fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({k: (adv[k], fb.font['glyf'][k].xMin if fb.font['glyf'][k].numberOfContours else 0) for k in order}); fb.setupHorizontalHeader(ascent=950, descent=-300)
    fb.setupNameTable({'familyName': family, 'styleName': 'Regular', 'uniqueFontIdentifier': family + ' 1.0', 'fullName': family, 'psName': family.replace(' ', '') + '-Regular', 'version': 'Version 1.000'})
    fb.setupOS2(sTypoAscender=950, sTypoDescender=-300, sTypoLineGap=0, usWinAscent=1000, usWinDescent=420, sxHeight=XH, sCapHeight=CH); fb.setupPost()
    fea = "languagesystem DFLT dflt; languagesystem latn dflt; languagesystem grek dflt;\n" + ''.join(f"@v{i}=[{' '.join(cl)}];\n" for i, cl in enumerate(CL))
    fea += "feature calt { lookup rot {\n" + ''.join(f"  sub @v{i} @v0' by @v{i+1};\n" for i in range(NV - 1)) + "} rot; } calt;\n"
    addOpenTypeFeaturesFromString(fb.font, fea); fb.save(out); print('wrote', out, '-', len(GL), 'characters x', NV, 'variants')

def finish(samples, out):
    family = os.path.splitext(os.path.basename(out))[0].replace('-', ' ').replace('_', ' ')
    real = {c: len(v) for c, v in samples.items() if v}
    write_font(build_glyphs(samples), out, family)
    need = [c for c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,?!'()-" if c not in real]
    json.dump(dict(from_sample=real, drawn_not_from_sample=need), open(os.path.splitext(out)[0] + '-report.json', 'w'), ensure_ascii=False, indent=1)
    print('REAL samples per character:', ' '.join(f'{c}:{n}' for c, n in sorted(real.items())))
    print('DRAWN (not in sample) letters/digits/basic punctuation:', ''.join(need) or 'none')

if __name__ == '__main__':
    a = sys.argv[1:]
    if not a or a[0] not in ('template', 'from-template', 'segment', 'from-labels'): sys.exit(__doc__)
    if a[0] == 'template': make_template(a[1])
    elif a[0] == 'segment': segment(a[1], a[2])
    elif a[0] == 'from-template':
        S = {}
        for path in a[2:]:
            page, d = read_template(path); print(path, '-> template page', page + 1, ',', len(d), 'characters found')
            for ch, v in d.items(): S.setdefault(ch, []).extend(v)
        finish(S, a[1])
    else:
        S = {}
        for wd in a[2:]:
            for ch, v in read_labels(wd).items(): S.setdefault(ch, []).extend(v)
        finish(S, a[1])
