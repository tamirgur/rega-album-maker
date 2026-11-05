#!/usr/bin/env python3
"""Render WORK/book.json to WORK/book.html (a preview in spreads) and WORK/book.pdf (for the printer).

    python render.py --work WORK [--bleed 3] [--left-binding] [--interior-only]

--bleed          extra mm around each page, for printers that ask for bleed (photos that touch an edge extend into it)
--left-binding   also write book-print-left-binding.pdf: for a Hebrew book printed by a service that binds on the left
                 only, the pages go in reverse (back cover, last page ... first page, front cover), so the printed book
                 opens from the right
--interior-only  also write book-interior.pdf without the covers, for services that take the cover as a separate file

Photos are prepared once into WORK/print/: rotated, sRGB, graded with the style's look (one balance, contrast and
warmth for all, and the style's tone), and at most 300 DPI at their printed size. Needs Chrome, Edge or Chromium (set CHROME_PATH).
"""
import argparse
import base64
import hashlib
import html
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ASSETS, font_path, find_browser, load, save  # noqa: E402
from maps import route_svg  # noqa: E402

E = html.escape


def grade(im, g):
    """One look for all the photos: casts halfway to neutral, a little contrast, colour and warmth."""
    from PIL import ImageEnhance, ImageFilter, ImageOps, ImageStat
    if not g:
        return im
    r, gg, b = ImageStat.Stat(im.resize((160, 160))).mean
    avg = (r + gg + b) / 3
    lut = []
    for c in (r, gg, b):
        f = (avg / max(c, 1)) ** g.get('neutralize', 0)
        lut += [min(255, int(v * f)) for v in range(256)]
    im = ImageOps.autocontrast(im.point(lut), cutoff=(0.4, 0.6), preserve_tone=True)
    im = ImageEnhance.Color(ImageEnhance.Contrast(im).enhance(g.get('contrast', 1))).enhance(g.get('saturation', 1))
    w = g.get('warmth', 0)
    im = im.point([min(255, int(v * (1 + w))) for v in range(256)] + list(range(256)) + [int(v * (1 - w)) for v in range(256)])
    im = tone(im, g.get('mode'))
    return im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=45, threshold=3))


def tone(im, mode):
    """A style's photo treatment: warm (a brown monochrome print), bw, retro (warm and faded) or soft (light, low
    contrast). Old or flash snapshots look better toned than shown as they are."""
    from PIL import Image, ImageEnhance, ImageOps
    if mode == 'warm':
        g = ImageOps.autocontrast(im.convert('L'), cutoff=1)
        return ImageOps.colorize(g, black='#22190f', white='#f3e9d8', mid='#8c7357')
    if mode == 'bw':
        return ImageOps.autocontrast(im.convert('L'), cutoff=1.5).convert('RGB')
    if mode == 'retro':
        im = ImageEnhance.Color(im).enhance(0.8)
        r, g, b = im.split()
        return Image.merge('RGB', (r.point(lambda v: min(255, int(v * 0.95 + 22))), g.point(lambda v: min(255, int(v * 0.9 + 18))),
                                   b.point(lambda v: min(255, int(v * 0.74 + 20)))))
    if mode == 'soft':
        im = ImageEnhance.Color(ImageEnhance.Contrast(im).enhance(0.9)).enhance(0.86)
        r, g, b = im.split()
        return Image.merge('RGB', (r.point(lambda v: int(20 + v * 0.92)), g.point(lambda v: int(16 + v * 0.92)),
                                   b.point(lambda v: int(18 + v * 0.9))))
    return im


def luminance(hexc):
    if not isinstance(hexc, str) or not hexc.startswith('#') or len(hexc) < 7:
        return 0.9
    r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def arrow_svg(W, H, x0, y0, x1, y1, color, bend=12):
    """A hand-drawn arrow over the page, with a light halo so it shows on a photo too."""
    import math
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy) or 1
    cx, cy = mx - dy / n * bend, my + dx / n * bend
    ang = math.atan2(y1 - cy, x1 - cx)
    h1 = (x1 + 3.8 * math.cos(ang + 2.6), y1 + 3.8 * math.sin(ang + 2.6))
    h2 = (x1 + 3.8 * math.cos(ang - 2.6), y1 + 3.8 * math.sin(ang - 2.6))
    d = f'M{x0:.1f} {y0:.1f}Q{cx:.1f} {cy:.1f} {x1:.1f} {y1:.1f}M{h1[0]:.1f} {h1[1]:.1f}L{x1:.1f} {y1:.1f}L{h2[0]:.1f} {h2[1]:.1f}'
    return (f'<svg class="abs" viewBox="0 0 {W:.2f} {H:.2f}" style="left:0;top:0;width:{W:.2f}mm;height:{H:.2f}mm">'
            f'<path d="{d}" stroke="#fffefb" stroke-width="1.5" opacity=".85" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="{d}" stroke="{color}" stroke-width=".55" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def renditions(book, work, bleed):
    from PIL import Image, ImageOps
    out = os.path.join(work, 'print')
    os.makedirs(out, exist_ok=True)
    g = book.get('style', {}).get('grade')
    need = {}
    for p in book['pages']:
        for f in p.get('frames', []):
            mm = f['img'][2] + 2 * bleed
            need[f['id']] = max(need.get(f['id'], 0), mm)
    uris = {}
    for pid, mm in need.items():
        ph = book['photos'][str(pid)]
        tw = min(ph['w'], max(200, int(mm / 25.4 * 300 / 50 + 1) * 50))
        tag = hashlib.sha1(json.dumps([g, tw], sort_keys=True).encode()).hexdigest()[:6]
        name = f'{pid}-{tag}.jpg'
        dst = os.path.join(out, name)
        if not (os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(ph['src'])):
            im = Image.open(ph['src'])
            icc = im.info.get('icc_profile')
            im = ImageOps.exif_transpose(im)
            if icc:
                try:
                    from PIL import ImageCms
                    im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                                   ImageCms.createProfile('sRGB'), outputMode='RGB')
                except Exception:
                    pass
            im = im.convert('RGB')
            if im.width != tw:
                im = im.resize((tw, max(1, round(im.height * tw / im.width))), Image.LANCZOS)
            grade(im, g).save(dst, quality=90, subsampling=0)
        uris[pid] = f'print/{name}'  # relative to the HTML in WORK, so the folder still works when moved
    return uris


def qr_svg(url, dark='#2B2724'):
    import segno
    q = segno.make(url, error='m', micro=False)
    svg = q.svg_inline(scale=1, border=4, dark=dark, light='#ffffff', omitsize=True)
    ok = None
    try:
        import zxingcpp
        from PIL import Image
        buf = io.BytesIO()
        q.save(buf, kind='png', scale=8, border=4)
        buf.seek(0)
        ok = any(r.text == url for r in zxingcpp.read_barcodes(Image.open(buf)))
    except ImportError:
        pass
    return svg, ok


def fonts_css(extra=None):
    """Assistant, and the concept's own display face (a file in assets/fonts), embedded so the PDF is complete."""
    css = []
    for w in (200, 300, 400, 600):
        with open(font_path(w), 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        css.append(f"@font-face{{font-family:Assistant;font-weight:{w};src:url(data:font/ttf;base64,{b64}) format('truetype')}}")
    done = set()
    for role in (extra or {}).values():
        if not role or role['file'] in done:
            continue
        done.add(role['file'])
        with open(os.path.join(ASSETS, 'fonts', role['file']), 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        css.append(f"@font-face{{font-family:'{role['family']}';font-weight:{role.get('weights', '400')};"
                   f"src:url(data:font/ttf;base64,{b64}) format('truetype')}}")
    return '\n'.join(css)


class Ctx:
    def __init__(self, book, uris, bleed, work):
        self.book, self.uris, self.b, self.work = book, uris, bleed, work
        self.W, self.H = book['w'], book['h']
        self.art = load(os.path.join(ASSETS, 'illustrations.json'))
        self.qr_checks = []
        self.photos = book['photos']

    def mm(self, v):
        return f'{v:.2f}mm'

    def extend(self, x, y, w, h):
        """A box that touches or crosses an edge of the page reaches into the bleed beyond it."""
        b, e = self.b, 0.01
        x0, y0, x1, y1 = x, y, x + w, y + h
        if b:
            if x0 <= e:
                x0 -= b
            if y0 <= e:
                y0 -= b
            if x1 >= self.W - e:
                x1 += b
            if y1 >= self.H - e:
                y1 += b
        return x0 + b, y0 + b, x1 - x0, y1 - y0

    PAD = {'mat': (5, 5, 5, 5), 'polaroid': (4.5, 4.5, 4.5, 16), 'rounded': (5, 5, 5, 5), 'print': (4, 4, 4, 9),
           'retro': (3, 3, 3, 3), 'keyline': (2.5, 2.5, 2.5, 2.5)}

    def frame(self, f):
        skin = f.get('skin')
        if skin in self.PAD:
            return self.framed(f, skin)
        X, Y, Wd, Hd = self.extend(*f['clip'])
        ix, iy, iw, ih = f['img'][0] + self.b - X, f['img'][1] + self.b - Y, f['img'][2], f['img'][3]
        cx, cy = ix + iw / 2, iy + ih / 2   # the bleed reaches past the photo: grow it around its centre to cover
        k = max(1, 2 * cx / iw, 2 * (Wd - cx) / iw, 2 * cy / ih, 2 * (Hd - cy) / ih)
        iw, ih = iw * k, ih * k
        ix, iy = cx - iw / 2, cy - ih / 2
        sh = ' shadow' if f.get('shadow') else ' mat' if f.get('mat') else ' lift' if skin == 'shadow' else f' {skin}' if skin else ''
        return (f'<div class="clip{sh}" style="left:{self.mm(X)};top:{self.mm(Y)};width:{self.mm(Wd)};height:{self.mm(Hd)}">'
                f'<img alt="" src="{self.uris[f["id"]]}" style="left:{self.mm(ix)};top:{self.mm(iy)};width:{self.mm(iw)};height:{self.mm(ih)}"></div>')

    def framed(self, f, skin):
        """A photo inside its frame: a mat, a polaroid, a print, a rounded frame, a keyline; tilted, taped."""
        u, b = self.book['u'], self.b
        l, t, r, bt = (v * u for v in self.PAD[skin])
        x, y, w, h = f['clip']
        ix, iy, iw, ih = f['img'][0] - x, f['img'][1] - y, f['img'][2], f['img'][3]
        ow, oh = w + l + r, h + t + bt
        inner = (f'<div class="clip" style="left:{self.mm(l)};top:{self.mm(t)};width:{self.mm(w)};height:{self.mm(h)}">'
                 f'<img alt="" src="{self.uris[f["id"]]}" style="left:{self.mm(ix)};top:{self.mm(iy)};width:{self.mm(iw)};'
                 f'height:{self.mm(ih)}"></div>')
        if f.get('caption'):
            inner += (f'<div class="cap h1" style="left:0;top:{self.mm(t + h)};width:{self.mm(ow)};height:{self.mm(bt)}">'
                      f'{E(f["caption"])}</div>')
        for tp in f.get('tape') or []:
            tw = 26 * u
            tx = {'start': 6 * u, 'end': ow - tw - 6 * u}.get(tp['at'], (ow - tw) / 2)
            rot = {'start': -8, 'end': 7}.get(tp['at'], 3)
            cls = 'tape washi' if tp.get('c') else 'tape'
            col = f'--c:{tp["c"]};' if tp.get('c') else ''
            inner += (f'<div class="{cls}" style="{col}left:{self.mm(tx)};top:{self.mm(-4 * u)};width:{self.mm(tw)};'
                      f'height:{self.mm(8.5 * u)};transform:rotate({rot}deg)"></div>')
        rot = f'transform:rotate({f["tilt"]}deg);' if f.get('tilt') else ''
        return (f'<div class="fx {skin}" style="left:{self.mm(x - l + b)};top:{self.mm(y - t + b)};width:{self.mm(ow)};'
                f'height:{self.mm(oh)};{rot}">{inner}</div>')

    def text(self, t):
        col = f'color:{t["color"]};' if t.get('color') else ''
        rot = ''
        if t.get('rot'):
            origin = 'center' if t['align'] == 'center' else t['align']
            rot = f'transform:rotate({t["rot"]}deg);transform-origin:{origin} top;'
        if t.get('anchor') == 'bottom':   # set from its last line up
            pos = f'bottom:{self.mm(self.H + 2 * self.b - (t["y"] + self.b))}'
        else:
            pos = f'top:{self.mm(t["y"] + self.b)}'
        return (f'<div class="t {t["cls"]}" style="left:{self.mm(t["x"] + self.b)};{pos};'
                f'width:{self.mm(t["w"])};text-align:{t["align"]};{col}{rot}">{E(t["text"])}</div>')

    def dots(self):
        """A dotted paper: one vector path of small dots every 6 mm."""
        u, W, H = self.book['u'], self.W + 2 * self.b, self.H + 2 * self.b
        step, r = 6 * u, 0.33 * u
        d = []
        y = step / 2
        while y < H:
            x = step / 2
            while x < W:
                d.append(f'M{x - r:.2f} {y:.2f}a{r:.2f} {r:.2f} 0 1 0 {2 * r:.2f} 0a{r:.2f} {r:.2f} 0 1 0 {-2 * r:.2f} 0')
                x += step
            y += step
        return (f'<svg class="abs" viewBox="0 0 {W:.2f} {H:.2f}" style="left:0;top:0;width:{W:.2f}mm;height:{H:.2f}mm">'
                f'<path d="{"".join(d)}" fill="rgba(120,100,80,.32)"/></svg>')

    def shape(self, it):
        """The style's shapes: blocks, rules, dots, arches, stamps, tags, badges and arrows."""
        b, u, k = self.b, self.book['u'], it['type']
        if k in ('rect', 'arch'):
            X, Y, Wd, Hd = self.extend(it['x'], it['y'], it['w'], it['h'])
            rad = f'border-radius:{self.mm(Wd / 2)} {self.mm(Wd / 2)} 0 0;' if k == 'arch' else ''
            return (f'<div class="abs" style="left:{self.mm(X)};top:{self.mm(Y)};width:{self.mm(Wd)};height:{self.mm(Hd)};'
                    f'background:{it["color"]};{rad}"></div>')
        if k == 'arrow':
            return arrow_svg(self.W + 2 * b, self.H + 2 * b, it['x0'] + b, it['y0'] + b, it['x1'] + b, it['y1'] + b, it['color'])
        pos = f'left:{self.mm(it["x"] + b)};top:{self.mm(it["y"] + b)};'
        if k == 'rule':
            if it.get('double'):
                line = f'height:{self.mm(1.6 * u)};border-top:.25mm solid {it["color"]};border-bottom:.25mm solid {it["color"]}'
            else:
                line = f'height:0;border-top:.3mm solid {it["color"]}'
            return f'<div class="abs" style="{pos}width:{self.mm(it["w"])};{line}"></div>'
        if k == 'dot':
            return (f'<div class="abs" style="{pos}width:{self.mm(it["d"])};height:{self.mm(it["d"])};border-radius:50%;'
                    f'background:{it["color"]}"></div>')
        if k == 'stamp':
            d = it['d']
            return (f'<div class="abs stamp" style="{pos}width:{self.mm(d)};height:{self.mm(d)};border-color:{it["color"]};'
                    f'color:{it["color"]}"><div class="label" style="width:{self.mm(d - 5 * u)};height:{self.mm(d - 5 * u)};'
                    f'border-color:{it["color"]};color:{it["color"]}">{E(it["text"])}</div></div>')
        if k == 'pill':
            return (f'<div class="abs pill label" style="{pos}width:{self.mm(it["w"])};height:{self.mm(it["h"])};'
                    f'background:{it["bg"]};color:{it["color"]};border-radius:{self.mm(it["h"] / 2)}">{E(it["text"])}</div>')
        if k == 'badge':
            d = it['d']
            return (f'<div class="abs badge" style="{pos}width:{self.mm(d)};height:{self.mm(d)};background:{it["color"]}">'
                    f'<span>{E(it["small"])}</span><b>{E(it["big"])}</b></div>')
        if k == 'arrow':
            return arrow_svg(self.W + 2 * b, self.H + 2 * b, it['x0'] + b, it['y0'] + b, it['x1'] + b, it['y1'] + b, it['color'])
        return ''

    def shade(self, s):
        X, Y, Wd, Hd = self.extend(s['x'], s['y'], s['w'], s['h'])
        g = 'rgba(0,0,0,.5),rgba(0,0,0,0)' if s['dir'] == 'down' else 'rgba(0,0,0,0),rgba(0,0,0,.5)'
        return f'<div class="abs" style="left:{self.mm(X)};top:{self.mm(Y)};width:{self.mm(Wd)};height:{self.mm(Hd)};background:linear-gradient({g})"></div>'

    def item(self, it):
        b = self.b
        if it['type'] == 'route':
            tracks = {int(n): t for n, t in self.book['tracks'].items()}
            return (f'<div class="abs map" style="left:{self.mm(it["x"] + b)};top:{self.mm(it["y"] + b)};width:{self.mm(it["w"])};'
                    f'height:{self.mm(it["h"])}">{route_svg(tracks, it["w"], it["h"], labels=True, places=it.get("places") or ())}</div>')
        if it['type'] == 'qr':
            svg, ok = qr_svg(it['url'], self.book['style']['colors']['ink'])
            self.qr_checks.append((it['url'], ok))
            return (f'<div class="abs qr" style="left:{self.mm(it["x"] + b)};top:{self.mm(it["y"] + b)};width:{self.mm(it["size"])}">'
                    f'{svg}<span>{E(it.get("label", ""))}</span></div>')
        if it['type'] == 'ill':
            a = self.art.get(it['name'] or '')
            return (f'<svg class="abs ill" viewBox="0 0 48 48" style="left:{self.mm(it["x"] + b)};top:{self.mm(it["y"] + b)};'
                    f'width:{self.mm(it["size"])};height:{self.mm(it["size"])}">{a}</svg>') if a else ''
        if it['type'] == 'logo':
            ext = os.path.splitext(it['path'])[1]
            dst = os.path.join(self.work, 'print', 'logo' + ext)
            if not os.path.isfile(dst) or os.path.getmtime(dst) < os.path.getmtime(it['path']):
                shutil.copyfile(it['path'], dst)
            return (f'<img class="abs logo" alt="" src="print/logo{ext}" style="left:{self.mm(it["x"] + b)};top:{self.mm(it["y"] + b)};'
                    f'width:{self.mm(it["w"])};height:{self.mm(it["h"])}">')
        if it['type'] in ('rect', 'arch', 'rule', 'dot', 'stamp', 'pill', 'badge', 'arrow'):
            return self.shape(it)
        if it['type'] == 'pass':
            ps = it['pass']
            plane = f'<svg class="plane" viewBox="0 0 48 48">{self.art.get("plane", "")}</svg>'
            legs = [('FROM', ps.get('from'))] + ([('VIA', ps['via'])] if ps.get('via') else []) + [('TO', ps.get('to'))]
            inner = plane.join(f'<div><small>{x}</small><b>{E(str(c or ""))}</b></div>' for x, c in legs)
            if ps.get('date'):
                inner += f'<div class="d"><small>DATE</small><b>{E(ps["date"])}</b></div>'
            return (f'<div class="abs pass" style="left:{self.mm(it["x"] + b)};top:{self.mm(it["y"] + b)};width:{self.mm(it["w"])};'
                    f'height:{self.mm(it["h"])}">{inner}</div>')
        return ''

    def page(self, p, last=False):
        body = ''.join(self.item(i) for i in p.get('under', []))   # blocks, stripes, arches: behind the photos
        body += ''.join(self.frame(f) for f in p.get('frames', []))
        body += ''.join(self.shade(s) for s in p.get('shades', []))
        body += ''.join(self.item(i) for i in p.get('items', []))
        body += ''.join(self.text(t) for t in p.get('texts', []))
        fg = f';color:{p["fg"]}' if p.get('fg') else ''
        bg = p.get('bg', '#fff')
        tex = self.book['style'].get('texture')
        cls = f' {tex}' if tex and luminance(bg) > 0.5 else ''
        if cls == ' dots':
            cls = ''
            body = self.dots() + body
        return f'<section class="page{" last" if last else ""}{cls}" style="background-color:{bg}{fg}">{body}</section>'


def css(book, bleed):
    st = book['style']
    c, u = st['colors'], book['u']
    W, H = book['w'] + 2 * bleed, book['h'] + 2 * bleed
    fonts, fam = st.get('fonts') or {}, {}
    for role, key in (('display', 'display_classes'), ('text', 'text_classes')):
        if fonts.get(role):
            for k in st.get(key, []):
                fam[k] = fonts[role]['family']
    types = ''.join(f'.{k}{{font-weight:{w};font-size:{s * u:.2f}pt;line-height:{1.05 if s > 15 else 1.45}' +
                    (f";font-family:'{fam[k]}',Assistant,sans-serif" if k in fam else '') + '}\n'
                    for k, (w, s) in st['type'].items())
    label_col = c['accent'] if st.get('label_color') == 'accent' else c.get('label', c['accent'])
    extra = (f'.h1,.h2,.hero{{color:{c["accent"]}}}\n' if st.get('title_color') == 'accent' else '')
    extra += f'.label,.deck{{letter-spacing:{st["label_spacing"]}}}\n' if st.get('label_spacing') else ''
    extra += skin_css(st, c, u)
    return f'''{fonts_css(st.get('fonts'))}
@page{{size:{W:.2f}mm {H:.2f}mm;margin:0}}
*{{box-sizing:border-box;margin:0;padding:0}}
html{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
body{{font-family:Assistant,sans-serif;color:{c["ink"]}}}
.page{{position:relative;width:{W:.2f}mm;height:{H:.2f}mm;overflow:hidden}}
.abs,.t,.clip{{position:absolute}}
.clip{{overflow:hidden}}
.clip img{{position:absolute;display:block;max-width:none}}
.clip.shadow{{box-shadow:0 2mm 7mm rgba(0,0,0,.5);overflow:visible}}
.clip.shadow img{{position:absolute}}
.clip.mat{{overflow:hidden;box-shadow:0 0 0 {2.2 * u:.2f}mm #fff,0 {1.2 * u:.2f}mm {3 * u:.2f}mm {2.2 * u:.2f}mm rgba(0,0,0,.16)}}
.ill{{fill:none;stroke:currentColor}}
.t{{text-wrap:balance}}
{types}.label,.folio{{color:{label_col}}}
{extra}
.qr svg{{width:100%;height:auto;display:block}}
.qr span{{display:block;font-weight:400;font-size:{2.4 * u:.2f}mm;text-align:center;margin-top:1mm;color:{c["accent"]}}}
.map svg{{width:100%;height:100%;display:block}}
.land{{fill:#e2dbcf}} .sea{{fill:transparent}}
.trk{{fill:none;stroke:{c["accent"]};stroke-linecap:round;stroke-linejoin:round}} .trk.dim{{stroke:#d3c9bc}}
.link{{stroke:#8c8379;opacity:.55;stroke-linecap:round}}
.dot{{fill:{c["accent"]}}} .dot.dim{{fill:#d3c9bc}}
.lbl{{fill:{c["ink"]};font-family:Assistant,sans-serif;font-weight:600}}
.ill{{fill:none}}
.pass{{display:flex;align-items:center;justify-content:center;gap:{6 * u:.2f}mm;border:.3mm dashed #d3c9bc;border-radius:2.5mm;direction:ltr}}
.pass div{{display:flex;flex-direction:column;align-items:center}}
.pass small{{font-weight:400;font-size:{2.2 * u:.2f}mm;letter-spacing:.14em;color:#8c8379}}
.pass b{{font-weight:300;font-size:{8 * u:.2f}mm;letter-spacing:.04em;line-height:1.05}}
.pass .plane{{width:{8 * u:.2f}mm;height:{8 * u:.2f}mm}}
.pass .d b{{font-size:{4 * u:.2f}mm}}
@media screen{{
  body{{background:#e6e3de;padding:8mm 0 16mm}}
  .spread{{display:flex;justify-content:center;margin:0 auto 3mm}}
  .page{{box-shadow:0 .8mm 3mm rgba(0,0,0,.14)}}
  .ghost{{width:{W:.2f}mm;height:{H:.2f}mm}}
  .label-row{{text-align:center;font:400 12px/1.4 Assistant,sans-serif;color:#8a857e;margin-bottom:7mm}}
}}
@media print{{
  .spread{{display:contents}}
  .ghost,.label-row{{display:none}}
  .page{{break-after:page}}
  .page.last{{break-after:auto}}
}}
'''


NOISE = """url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 .35 0 0 0 0 .28 0 0 0 0 .2 0 0 0 ALPHA 0'/></filter><rect width='160' height='160' filter='url(%23n)'/></svg>")"""


def skin_css(st, c, u):
    """The frames, tapes, stamps, tags and paper textures of the style."""
    key = st.get('keyline') or c['accent']
    return f"""
.fx{{position:absolute}}
.fx .clip{{position:absolute;overflow:hidden}}
.fx .clip img{{position:absolute;display:block;max-width:none}}
.fx.mat{{background:#fff;box-shadow:0 .4mm 1.6mm rgba(60,45,30,.18);outline:{.22 * u:.2f}mm solid {key};outline-offset:{2.2 * u:.2f}mm}}
.fx.polaroid{{background:#fffefb;box-shadow:0 .8mm 2.6mm rgba(0,0,0,.2)}}
.fx.rounded{{background:#fff;border-radius:{5 * u:.2f}mm;box-shadow:0 1mm 2.5mm rgba(35,65,90,.18)}}
.fx.rounded .clip{{border-radius:{2 * u:.2f}mm}}
.fx.print{{background:#fbf7ef;box-shadow:0 1.2mm 3.5mm rgba(40,28,15,.28)}}
.fx.retro{{background:#fff9ee;border-radius:{3.5 * u:.2f}mm;box-shadow:0 1mm 3mm rgba(70,40,20,.25)}}
.fx.retro .clip{{border-radius:{1.8 * u:.2f}mm}}
.fx.keyline{{border:.3mm solid {key}}}
.clip.soft{{border-radius:{4 * u:.2f}mm}}
.clip.lift{{box-shadow:0 1.2mm 4mm rgba(0,0,0,.22)}}
.cap{{position:absolute;display:flex;align-items:center;justify-content:center;text-align:center;color:{c["ink"]}}}
.tape{{position:absolute;background:rgba(236,224,196,.72);box-shadow:0 .2mm .6mm rgba(0,0,0,.12)}}
.tape.washi{{background:repeating-linear-gradient(45deg,var(--c) 0 2.2mm,rgba(255,255,255,.55) 2.2mm 3.4mm);opacity:.9}}
.stamp{{border:.7mm solid;border-radius:50%;transform:rotate(-12deg);display:flex;align-items:center;justify-content:center;opacity:.82}}
.stamp div{{position:static;border:.25mm solid;border-radius:50%;display:flex;align-items:center;justify-content:center;text-align:center;line-height:1.15}}
.pill{{display:flex;align-items:center;justify-content:center;white-space:nowrap}}
.badge{{border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;line-height:1.05}}
.badge span{{font-size:{9 * u:.2f}pt}} .badge b{{font-size:{17 * u:.2f}pt;font-weight:600}}
.grain{{background-image:{NOISE.replace('ALPHA', '.09')}}}
.kraft{{background-image:{NOISE.replace('ALPHA', '.12')}}}
.dots{{background-image:radial-gradient(rgba(120,100,80,.3) {.32 * u:.2f}mm,transparent {.38 * u:.2f}mm);background-size:{6 * u:.2f}mm {6 * u:.2f}mm}}
"""


def build_html(book, ctx, pages, spreads, bleed):
    head = (f'<!doctype html><html lang="{book["lang"]}" dir="{book["dir"]}"><head><meta charset="utf-8">'
            f'<title>{E(book["title"])}</title><style>{css(book, bleed)}</style></head><body>')
    out = [head]
    last = pages[-1]
    if spreads:
        inner = pages[1:-1]
        rows = [[pages[0]]] + ([[None, inner[0]]] if inner else [])
        for i in range(1, len(inner), 2):
            pair = inner[i:i + 2]
            rows.append(pair if len(pair) == 2 else [pair[0], None])
        rows.append([pages[-1]])
        for row in rows:
            cells = ''.join('<div class="ghost"></div>' if p is None else ctx.page(p, p is last) for p in row)
            nums = ' · '.join(str(p['n']) for p in row if p and 'n' in p) or ('cover' if row[0] is pages[0] else 'back')
            out.append(f'<div class="spread">{cells}</div><div class="label-row">{nums}</div>')
    else:
        out += [ctx.page(p, p is last) for p in pages]
    out.append('</body></html>')
    return ''.join(out)


def print_pdf(html_path, pdf_path):
    exe = find_browser()
    if not exe:
        sys.exit('Chrome, Edge or Chromium is needed to make the PDF. Install one, or set CHROME_PATH to its program file.')
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    # Linux sandboxes such as Cowork's: Chrome's own sandbox can't start there, and /dev/shm is small
    linux = ['--no-sandbox', '--disable-dev-shm-usage'] if sys.platform.startswith('linux') else []
    with tempfile.TemporaryDirectory() as profile:  # a separate profile, so an open browser window is not disturbed
        r = subprocess.run([exe, *linux, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                            f'--user-data-dir={profile}', '--no-pdf-header-footer', '--print-to-pdf-no-header',
                            '--run-all-compositor-stages-before-draw', '--virtual-time-budget=30000',
                            f'--print-to-pdf={pdf_path}', Path(html_path).resolve().as_uri()],
                           capture_output=True, text=True, errors='replace', timeout=900)
    if not os.path.isfile(pdf_path) or os.path.getsize(pdf_path) < 1000:
        sys.exit('The browser did not write the PDF.\n' + (r.stderr or '')[-1500:])


def count_pages(pdf):
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError:
            return None
    with pymupdf.open(pdf) as d:
        return d.page_count


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work', required=True)
    ap.add_argument('--bleed', type=float, default=0.0)
    ap.add_argument('--left-binding', action='store_true')
    ap.add_argument('--interior-only', action='store_true')
    a = ap.parse_args()
    work = os.path.abspath(a.work)
    book = load(os.path.join(work, 'book.json'))
    if 'style' not in book:
        sys.exit('This book.json comes from an older version: run layout.py again.')
    if book.get('bleed') != a.bleed:  # saved before the PDF, so the PDF stays the newer file
        book['bleed'] = a.bleed
        save(os.path.join(work, 'book.json'), book)
    uris = renditions(book, work, a.bleed)
    ctx = Ctx(book, uris, a.bleed, work)
    pages = book['pages']

    jobs = [('book', pages, True)]
    if a.left_binding:
        jobs.append(('book-print-left-binding', [pages[-1]] + pages[1:-1][::-1] + [pages[0]], False))
    if a.interior_only:
        jobs.append(('book-interior', pages[1:-1], False))
    for name, seq, spreads in jobs:
        hp = os.path.join(work, name + '.html')
        with open(hp, 'w', encoding='utf-8') as f:
            f.write(build_html(book, ctx, seq, spreads, a.bleed))
        pdf = os.path.join(work, name + '.pdf')
        print_pdf(hp, pdf)
        n = count_pages(pdf)
        print(f'{pdf}  ({os.path.getsize(pdf) / 1e6:.1f} MB' + (f', {n} pages' if n else '') + ')')
        if n and n != len(seq):
            print(f'  Warning: expected {len(seq)} pages. Some content may overflow a page; check the preview.')
    print(f'Preview: {os.path.join(work, "book.html")} (open it in a browser: spreads in reading order)')
    if a.left_binding and book['dir'] == 'ltr':
        print('Note: --left-binding is meant for right-to-left books; an English book binds on the left as it is.')
    for url, ok in dict.fromkeys(ctx.qr_checks):
        print(f'QR {"scans" if ok else "DOES NOT SCAN" if ok is False else "made (install zxing-cpp to check it)"}: {url}')


if __name__ == '__main__':
    main()
