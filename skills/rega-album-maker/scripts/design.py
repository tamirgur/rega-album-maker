"""The design of the book: the style (the look, from looks.py), the templates (the layouts), the planner that turns
chapters into pages, and the rules that check the result. layout.py drives it; render.py draws what it decides.

Every page is a list of frames (a photo, its visible box and where the photo sits behind it), texts, shades and
items (route map, QR code, boarding pass, illustration, logo), in mm, in the page's own coordinates.
"""
import colorsys
import itertools
import math
import os

from common import is_rtl
from looks import resolve, style_names

TEMPLATES = ('opener-spread', 'band', 'side', 'fill', 'hero', 'quiet', 'jewel')
TINTS = {'sand': '#EFE6D8', 'linen': '#F4EFE7', 'rose': '#F1E3DF', 'mist': '#E4EAEF', 'sage': '#E3E9E0',
         'slate': '#2E3A4B', 'white': '#FBFAF7'}
# the border a frame style puts around a photo (left, top, right, bottom, in mm on a 21 cm page). The layout keeps
# room for it, so framed photos never overlap or leave the page.
SKINS = {'mat': (7.6, 7.6, 7.6, 7.6), 'polaroid': (4.5, 4.5, 4.5, 16), 'rounded': (5, 5, 5, 5), 'print': (4, 4, 4, 9),
         'retro': (3, 3, 3, 3), 'keyline': (2.8, 2.8, 2.8, 2.8), 'soft': (0, 0, 0, 0), 'shadow': (0, 0, 0, 0),
         'none': (0, 0, 0, 0)}


def luminance(hexc):
    if not hexc.startswith('#') or len(hexc) < 7:
        return 0.9
    r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
EDGE = {'opener-spread', 'band', 'side', 'hero'}           # templates whose photo runs to the edge of the page


# ---------------------------------------------------------------- the look: structure, style and palette (looks.py)

def concepts():
    return style_names()


def concept(name, palette=None, photo_paths=(), structure=None):
    return resolve(name, palette, structure, photo_paths)


def _hex(rgb):
    return '#%02x%02x%02x' % tuple(int(max(0, min(255, v))) for v in rgb)


def palette_from_photos(paths):
    """Paper, ink and accent from the book's own photos. The accent is the most saturated colour of middle
    lightness that is really there, even if it covers little: the gowns, not the stone wall."""
    from PIL import Image
    tiles = []
    for p in list(paths)[:40]:
        with Image.open(p) as im:
            tiles.append(im.convert('RGB').resize((64, 48)))
    m = Image.new('RGB', (64 * len(tiles), 48))
    for n, t in enumerate(tiles):
        m.paste(t, (64 * n, 0))
    q = m.quantize(colors=32, method=Image.Quantize.MEDIANCUT)
    pal, total, cols = q.getpalette(), m.width * m.height, []
    for cnt, c in q.getcolors():
        h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in pal[3 * c:3 * c + 3]))
        cols.append((cnt / total, h, l, s))
    good = [c for c in cols if c[0] > 0.003 and 0.2 < c[2] < 0.65] or cols
    _, h, l, s = max(good, key=lambda c: c[3] * min(1, c[0] / 0.02))
    acc = colorsys.hls_to_rgb(h, min(l, 0.42), min(1, s * 1.1))
    return {'accent': _hex([v * 255 for v in acc]), 'paper': _hex([v * 255 for v in colorsys.hls_to_rgb(h, 0.972, 0.16)]),
            'ink': _hex([v * 255 for v in colorsys.hls_to_rgb(h, 0.14, 0.22)]),
            'endpaper': _hex([v * 255 for v in colorsys.hls_to_rgb(h, 0.22, 0.35)])}


# ---------------------------------------------------------------- photos and faces

class Photo:
    def __init__(self, rec, no_people):
        self.id, self.w, self.h = rec['id'], rec['w'], rec['h']
        self.a = self.w / self.h
        self.src, self.thumb = rec['path'], rec.get('thumb')
        self.known = 'faces' in rec                       # were faces looked for?
        faces = [f for f in rec.get('faces', []) if f[3] >= 0.035]
        top = max((f[3] for f in faces), default=0)
        # the people the photo is about: a title keeps off them and the spine misses them; a crowd behind is fair game
        self.main = [f for f in faces if f[3] >= max(0.06, 0.5 * top)]
        # faces a crop must not cut: everyone in a small group, only the main people in a crowd
        self.faces = faces if len(rec.get('faces', [])) <= 6 else self.main
        self.marked_no_people = rec['id'] in no_people
        self.taken = rec['taken']

    @property
    def crop_ok(self):
        """May this photo be cropped? Yes with nobody in it, or when we know where the faces are."""
        return self.marked_no_people or self.known


def cover_img(ph, clip, focus):
    """Where the photo sits behind a frame that it fills (object-fit: cover around the focus point)."""
    x, y, w, h = clip
    k = max(w / ph.w, h / ph.h)
    iw, ih = ph.w * k, ph.h * k
    return [x - (iw - w) * focus[0], y - (ih - h) * focus[1], iw, ih]


def faces_mm(ph, img, main=False):
    ix, iy, iw, ih = img
    return [(ix + f[0] * iw, iy + f[1] * ih, f[2] * iw, f[3] * ih) for f in (ph.main if main else ph.faces)]


def crop_safe(ph, clip, img):
    """No face cut by the frame (2 mm to spare), and no feet: with a whole body in the photo, almost nothing off the bottom."""
    if ph.marked_no_people:
        return True
    if not ph.known:
        return abs(clip[2] / clip[3] - ph.a) < 0.01
    x, y, w, h = clip
    for fx, fy, fw, fh in faces_mm(ph, img):
        if fx < x + 2 or fy < y + 2 or fx + fw > x + w - 2 or fy + fh > y + h - 2:
            return False
    # the feet: protected only when a whole body is in the photo (a face small enough, high enough, to have feet
    # below it); a seated or half-length photo may lose its bottom
    feet = any(f[1] + 8 * f[3] <= 1.02 for f in ph.faces)
    return not feet or (img[1] + img[3]) - (y + h) <= 0.04 * img[3] + 0.01


def best_focus(ph, clip, extra=None):
    """The safe crop nearest the middle (a little above it), or None when no crop is safe."""
    best = None
    for fx in range(0, 101, 10):
        for fy in range(0, 101, 10):
            f = (fx / 100, fy / 100)
            img = cover_img(ph, clip, f)
            if not crop_safe(ph, clip, img) or (extra and not extra(f, img)):
                continue
            d = abs(fx - 50) + abs(fy - 45)
            if best is None or d < best[0]:
                best = (d, f)
    return best[1] if best else None


def busyness(ph, box_frac):
    """How busy a part of the photo is (edges), against the photo as a whole: below 0.7 is calm."""
    from PIL import Image, ImageFilter, ImageStat
    if not ph.thumb or not os.path.isfile(ph.thumb):
        return 1.0
    im = Image.open(ph.thumb).convert('L').filter(ImageFilter.FIND_EDGES)
    W, H = im.size
    x0, y0, x1, y1 = (max(0, min(1, v)) for v in box_frac)
    if x1 - x0 < 0.02 or y1 - y0 < 0.02:
        return 1.0
    part = ImageStat.Stat(im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))).mean[0]
    return part / max(ImageStat.Stat(im).mean[0], 1e-6)


def lightness(ph, box_frac):
    from PIL import Image, ImageStat
    if not ph.thumb or not os.path.isfile(ph.thumb):
        return 0.5
    im = Image.open(ph.thumb).convert('L')
    W, H = im.size
    x0, y0, x1, y1 = (max(0, min(1, v)) for v in box_frac)
    return ImageStat.Stat(im.crop((int(x0 * W), int(y0 * H), max(int(x0 * W) + 1, int(x1 * W)),
                                  max(int(y0 * H) + 1, int(y1 * H))))).mean[0] / 255


def sharp_enough(ph, w, h, dpi=170):
    """Does the photo, filling a w x h mm box, print at `dpi` or more?"""
    k = max(w / ph.w, h / ph.h)   # mm per pixel
    return 25.4 / k >= dpi


def overlap(a, b):
    return max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) * max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))


def bodies(ph, img):
    """Each person as a box: the face, widened, down to about the waist. Titles keep off them."""
    return [(x - 0.5 * w, y - 0.3 * h, w * 2, h * 4.5) for x, y, w, h in faces_mm(ph, img, main=True)]


# ---------------------------------------------------------------- the fill engine: photos in their own shapes

def _leaf(p):
    return ('p', p, 1 / p.a, 0.0)


def _band(k, g):
    a = 1 / sum(1 / x[2] for x in k)
    return ('band', k, a, (-g * (len(k) - 1) + sum(x[3] / x[2] for x in k)) * a)


def _stack(k, g):
    return ('stack', k, sum(x[2] for x in k), sum(x[3] for x in k) + g * (len(k) - 1))


def _trees(ps, g):
    if len(ps) == 1:
        yield _leaf(ps[0])
        return
    for k in range(1, len(ps)):
        for a in _trees(ps[:k], g):
            for b in _trees(ps[k:], g):
                yield _band([a, b], g)
                yield _stack([a, b], g)


def _place(n, x, y, w, g, out):
    if n[0] == 'p':
        out.append((n[1], x, y, w, n[2] * w))
    elif n[0] == 'band':
        h = n[2] * w + n[3]
        for k in n[1]:
            kw = (h - k[3]) / k[2]
            _place(k, x, y, kw, g, out)
            x += kw + g
    else:
        for k in n[1]:
            _place(k, x, y, w, g, out)
            y += k[2] * w + k[3] + g


def fill_layout(ps, bw, bh, g):
    """The arrangement of 1-4 photos, each in its own shape, that fills the box best, one a little larger than
    the rest. Returns (fill ratio, [(photo, x, y, w, h)], used width, used height)."""
    best = None
    for perm in itertools.permutations(ps):
        for t in _trees(list(perm), g):
            w = bw
            h = t[2] * w + t[3]
            if h > bh:
                w, h = (bh - t[3]) / t[2], bh
            if w <= 0:
                continue
            r = []
            _place(t, 0, 0, w, g, r)
            areas = [q[3] * q[4] for q in r]
            if min(min(q[3], q[4]) for q in r) < 30:
                continue
            fill = sum(areas) / (bw * bh)
            sc = fill + 0.12 * max(areas) / sum(areas)
            if best is None or sc > best[0]:
                best = (sc, fill, r, w, h)
    return best[1:] if best else None


# ---------------------------------------------------------------- pages

class Designer:
    def __init__(self, W, H, style, lang, gutter=0.0):
        self.W, self.H, self.s, self.lang = W, H, min(W, H) / 210.0, lang
        self.rtl = is_rtl(lang)
        self.c = style
        m = style['margin']
        self.mo, self.ms, self.mt = m['outer'] * self.s, m['spine'] * self.s, m['top'] * self.s
        self.gutter = gutter   # mm the binding hides at the fold (about 6 in a glued book, 0 in a layflat)
        if gutter:             # the printer's safe area: 10 mm from every edge, plus what the fold hides
            self.ms, self.mo, self.mt = max(self.ms, gutter + 10), max(self.mo, 10), max(self.mt, 10)
        self.g = style['gap'] * self.s
        self.bg = None      # the current chapter's tint, when the style gives pages a colour
        self.turn = 0       # scene pages alternate their side
        self.skin = style.get('frame', 'none') if style.get('frame') in SKINS else 'none'

    def pt(self, cls):
        """The height in mm of one line of a type class."""
        size = self.c['type'][cls][1] * self.s
        return size * 0.3528 * (1.05 if size > 15 else 1.45)

    def head_h(self):
        """The room a chapter title and its tag take above the photos."""
        return self.pt('h2') + 3 * self.s + self.pt('label') + (6 + self.c.get('head_extra', 0)) * self.s

    def color(self, role):
        c = self.c['colors']
        if role in (None, 'ink'):
            return None
        if role.startswith('ill'):
            ill = c.get('ill') or [c['accent']]
            return ill[int(role[3:] or 0) % len(ill)]
        return c.get(role, role)

    # page n: in a Hebrew book odd pages are on the left, in an English book on the right
    def side(self, n):
        return ('l' if n % 2 else 'r') if self.rtl else ('r' if n % 2 else 'l')

    def area(self, side, top_extra=0, bottom_extra=0):
        x0 = self.ms if side == 'r' else self.mo   # a right page binds on its left edge
        return [x0, self.mt + top_extra, self.W - self.mo - self.ms, self.H - 2 * self.mt - top_extra - bottom_extra]

    def page(self, tpl, side, bg=None):
        bg = bg or self.bg or self.c['colors']['paper']
        c = self.c['colors']
        light = max((c['paper'], c['ink']), key=luminance)
        return {'kind': 'page', 'tpl': tpl, 'side': side, 'bg': bg,
                'fg': light if luminance(bg) < 0.35 and luminance(c['ink']) < 0.5 else None,   # light type on a night page
                'frames': [], 'texts': [], 'shades': [], 'items': []}

    def frame(self, pg, ph, clip, focus=None, shadow=False, skin=True):
        """A photo in a box. Inside the page, the style's frame (a mat, a polaroid, a print...) is drawn around it:
        the photo shrinks inside its box to leave room for it, keeping its own shape."""
        cropped = focus is not None
        x, y, w, h = clip
        inside = x > 0.5 and y > 0.5 and x + w < self.W - 0.5 and y + h < self.H - 0.5
        sk = self.skin if skin and inside and not shadow else 'none'
        extra = {}
        if sk != 'none':
            l, t, r, b = (v * self.s for v in SKINS[sk])
            aw, ah = w - l - r, h - t - b
            if cropped:
                x, y, w, h = x + l, y + t, aw, ah
            else:
                k = min(aw / w, ah / h)
                nw, nh = w * k, h * k
                x, y, w, h = x + l + (aw - nw) / 2, y + t + (ah - nh) / 2, nw, nh
            clip = [x, y, w, h]
            tilt = self.c.get('tilt', 0)
            if tilt:
                extra['tilt'] = round(((ph.id * 7919 + len(pg['frames']) * 31) % 9 - 4) / 4 * tilt, 2)
            tape = self.c.get('tape')
            if tape:   # one strip or two across the top corners, like a print stuck in by hand
                k = ph.id + len(pg['frames'])
                where = ('start', 'end') if k % 3 else (('start',) if k % 2 else ('end',))
                extra['tape'] = [{'at': at, 'c': self.color(f'ill{(k + i) % 3}') if tape == 'washi' else None}
                                 for i, at in enumerate(where)]
        img = cover_img(ph, clip, focus) if cropped else list(clip)
        f = {'id': ph.id, 'clip': [round(v, 2) for v in clip], 'img': [round(v, 2) for v in img],
             'focus': list(focus) if focus else None, 'cropped': cropped, 'shadow': shadow,
             'skin': sk if sk != 'none' else None}
        f.update(extra)
        pg['frames'].append(f)
        return img

    def text(self, pg, cls, text, x, y, w, align=None, color=None):
        if text:
            pg['texts'].append({'cls': cls, 'text': text, 'x': round(x, 2), 'y': round(y, 2), 'w': round(w, 2),
                                'align': align or ('right' if self.rtl else 'left'), 'color': color})

    def outer_x(self, side, w):
        """The x of a box of width w set against the outer margin."""
        return self.W - self.mo - w if side == 'r' else self.mo

    def folio(self, pg, n):
        w = 20 * self.s
        self.text(pg, 'folio', str(n), self.outer_x(pg['side'], w), self.H - 9 * self.s, w,
                  align='right' if pg['side'] == 'r' else 'left')

    # ---- single pages
    def scene(self, side, photos, head=None, illustration=None):
        """A page as a scene: the photos as a group on part of the page, set to one side, the words at the bottom."""
        sc = self.c['scene']
        pg = self.page('fill', side)
        x0, y0, bw, bh = self.area(side)
        s = self.s
        self.turn += 1
        times = self.c.get('times') and photos[0].taken and len(photos[0].taken) >= 16
        words = (self.head_h() if head else self.pt('label') + 6 * s if times else 0)
        portrait = bh > bw * 1.15
        boxw = bw if portrait or len(photos) > 1 else bw * sc.get('box', 0.68)
        if len(photos) == 1 and not portrait:
            boxw = bw * min(0.86, sc.get('box', 0.68) + 0.14)
        boxh = bh - words if portrait else min(bh - words, bh * sc.get('height', 0.72))
        lay = fill_layout(photos, boxw, boxh, self.g) or fill_layout(photos, bw, bh - words, self.g)
        _, rects, w, h = lay
        start = self.turn % 2 == 0   # the group sits at the page's start side, then at its end side
        right = start == self.rtl
        ox = x0 + bw - w if right else x0
        if w > bw * 0.9:
            ox, right = x0 + (bw - w) / 2, self.rtl
        top = y0 + max(0.0, (bh - h - words) * 0.42)   # the block (photos and words) at the optical centre
        for p, x, y, rw, rh in rects:
            self.frame(pg, p, [ox + x, top + y, rw, rh])
        align = 'right' if right else 'left'   # the words under the photos, on the group's own edge
        ty = top + h + 6 * s + self.c.get('head_extra', 0) * s
        if head:
            self.head(pg, head, ox, ty, w, align)
        elif times:
            self.text(pg, 'label', photos[0].taken[11:16], ox, ty, w, align)
        return pg

    def fill(self, side, photos, head=None, running=None, qr=None, illustration=None):
        if self.c.get('scene') and not qr:
            return self.scene(side, photos, head, illustration)
        pg = self.page('fill', side)
        top = 0
        if head:  # the chapter's first page: its title above the photos
            self.head(pg, head, self.area(side)[0], self.mt, self.area(side)[2])
            top = self.head_h()
        elif running:
            self.text(pg, 'label', running, self.area(side)[0], max(3 * self.s, self.mt - 7.5 * self.s), self.area(side)[2])
        bottom = 30 * self.s if qr else 0
        x0, y0, bw, bh = self.area(side, top, bottom)
        lay = fill_layout(photos, bw, bh, self.g)
        if lay is None:  # too many for this page: put them in a row, smaller
            lay = (0, [(p, i * bw / len(photos), 0, bw / len(photos) - self.g, (bw / len(photos) - self.g) / p.a)
                       for i, p in enumerate(photos)], bw, bw / len(photos) / photos[0].a)
        _, rects, w, h = lay
        shift = max(0.0, (bh - h) * 0.42)   # the photos at the optical centre, the title kept right above them
        ox, oy = x0 + (bw - w) / 2, y0 + shift
        if head:
            for t in pg['texts']:
                t['y'] = round(t['y'] + shift, 2)
        for p, x, y, rw, rh in rects:
            self.frame(pg, p, [ox + x, oy + y, rw, rh])
        if qr:
            self.qr(pg, qr)
        return pg

    def band(self, side, ph, title=None, deck=None, caption=None, qr=None):
        """A landscape across the full width, off the top edge; a band of white below for the words."""
        pg = self.page('band', side)
        h = self.W / ph.a
        self.frame(pg, ph, [0, 0, self.W, h])
        x0, _, bw, _ = self.area(side)
        y = h + 8 * self.s
        if title:
            self.text(pg, 'h1', title, x0, y, bw, None, self.color(self.c.get('title_color')))
            y += self.pt('h1') + 4 * self.s
        for t in (deck, caption):
            if t:
                self.text(pg, 'label', t, x0, y, bw)
                y += 6 * self.s
        if qr:
            self.qr(pg, qr, y=self.H - 30 * self.s)
        return pg

    def band_ok(self, ph):
        return ph.a >= 1.15 and self.H - self.W / ph.a >= 34 * self.s

    def side_page(self, side, ph, title=None, deck=None, story=None, detail=None, caption=None, qr=None):
        """A portrait to the full height, against the outer edge; a column on the spine side for the words or a detail."""
        pg = self.page('side', side)
        w = self.H * ph.a
        x = self.W - w if side == 'r' else 0
        self.frame(pg, ph, [x, 0, w, self.H])
        col = self.W - w - self.ms - 6 * self.s
        cx = self.ms if side == 'r' else w + 6 * self.s
        y = self.mt
        if title:
            self.text(pg, 'h2', title, cx, y, col, None, self.color(self.c.get('title_color')))
            y += self.pt('h2') * (1 + (self.text_w(title, 'h2') > col)) + 3 * self.s
            if deck:
                self.text(pg, 'label', deck, cx, y, col)
                y += self.pt('label') + 6 * self.s
        if detail is not None:
            dh = col / detail.a
            if y + dh < self.H - 40 * self.s:
                self.frame(pg, detail, [cx, y + 4 * self.s, col, dh])
                y += dh + 8 * self.s
        if story:
            self.text(pg, 'story', story, cx, max(y + 4 * self.s, self.H * 0.45), col)
        if qr:
            self.qr(pg, qr, x=cx, y=self.H - 34 * self.s)
        elif caption:
            self.text(pg, 'label', caption, cx, self.H - 14 * self.s, col)
        return pg

    def side_ok(self, ph):
        return ph.a <= 0.85 and self.W - self.H * ph.a >= 40 * self.s

    def hero(self, side, ph, caption=None):
        """The photo fills the page, cropped where it is safe."""
        f = best_focus(ph, [0, 0, self.W, self.H]) if ph.crop_ok and sharp_enough(ph, self.W, self.H) else None
        if f is None:
            return None
        pg = self.page('hero', side)
        self.frame(pg, ph, [0, 0, self.W, self.H], f)
        return pg

    def quiet(self, side, ph, caption=None, scale=None):
        """One photo alone, with air around it: a pause."""
        pg = self.page('quiet', side)
        x0, y0, bw, bh = self.area(side)
        k = scale or self.c.get('quiet_scale', 0.74)
        if ph.a > 1.1 and bh > bw * 1.15:
            k = max(k, 0.92)
        w = min(bw * k, bh * k * ph.a)
        h = w / ph.a
        x, y = x0 + (bw - w) / 2, y0 + (bh - h) / 2 - 5 * self.s
        self.frame(pg, ph, [x, y, w, h])
        self.text(pg, 'label', caption, x, y + h + 4 * self.s, w)
        return pg

    def jewel(self, side, ph, caption=None):
        """A document or a detail, whole, on a dark page."""
        pg = self.page('jewel', side, self.c['colors']['dark'])
        bw = self.W * 0.42
        w = min(bw, self.H * 0.62 * ph.a)
        h = w / ph.a
        x, y = (self.W - w) / 2, (self.H - h) / 2 - 5 * self.s
        self.frame(pg, ph, [x, y, w, h], shadow=True)
        self.text(pg, 'label', caption, x, y + h + 5 * self.s, w, color=self.c['colors']['accent'])
        return pg

    def opener_spread(self, ph, title, deck, first_side):
        """A chapter opens across both pages: the photo bleeds off every edge, the title sits on a calm corner of it
        where it covers nobody. Returns the two pages (first, second) or None when no crop and corner work."""
        if not ph.crop_ok or ph.a < 1.2 or not sharp_enough(ph, 2 * self.W, self.H):
            return None
        W2, H = 2 * self.W, self.H
        clip = [0, 0, W2, H]
        tw, th = 150 * self.s, 36 * self.s
        corners = {'top-right': (W2 - 22 * self.s - tw, 18 * self.s), 'top-left': (22 * self.s, 18 * self.s),
                   'bottom-right': (W2 - 22 * self.s - tw, H - 18 * self.s - th), 'bottom-left': (22 * self.s, H - 18 * self.s - th)}

        def free(f, img):
            people = bodies(ph, img)
            g = self.gutter + 2 * self.s
            spine = any(fx - g < self.W < fx + fw + g for fx, fy, fw, fh in faces_mm(ph, img, main=True))
            return not spine and any(not any(overlap((cx, cy, tw, th), b) for b in people) for cx, cy in corners.values())
        f = best_focus(ph, clip, free)
        if f is None:
            return None
        img = cover_img(ph, clip, f)
        people = bodies(ph, img)

        def frac(cx, cy):
            return ((cx - img[0]) / img[2], (cy - img[1]) / img[3], (cx + tw - img[0]) / img[2], (cy + th - img[1]) / img[3])
        ok = [(k, v) for k, v in corners.items() if not any(overlap((v[0], v[1], tw, th), b) for b in people)]
        name, (cx, cy) = min(ok, key=lambda kv: busyness(ph, frac(*kv[1])))
        busy = busyness(ph, frac(cx, cy))
        light = lightness(ph, frac(cx, cy))
        shade = busy >= 0.7
        color = '#ffffff' if shade or light < 0.55 else self.c['colors']['ink']
        right_half_first = self.rtl   # a Hebrew spread starts on the right page
        pages = []
        for half in ((1, 0) if right_half_first else (0, 1)):
            side = 'r' if half == 1 else 'l'
            pg = self.page('opener-spread', side)
            off = -self.W * half
            self.frame(pg, ph, [off, 0, W2, H], f)
            if shade:
                top = name.startswith('top')
                pg['shades'].append({'x': off, 'y': 0 if top else H * 0.5, 'w': W2, 'h': H * 0.5, 'dir': 'down' if top else 'up'})
            if half == (1 if name.endswith('right') else 0):
                align = 'right' if name.endswith('right') else 'left'
                self.text(pg, 'hero', title, cx + off, cy, tw, align, color)
                self.text(pg, 'deck', deck, cx + off, cy + 22 * self.s, tw, align, color)
            pg['corner'], pg['busy'], pg['shade'] = name, round(busy, 2), shade
            pages.append(pg)
        return pages

    # ---- items
    def qr(self, pg, q, x=None, y=None):
        size = 20 * self.s
        x = self.outer_x(pg['side'], size) if x is None else x
        y = self.H - self.mt - size - 4 * self.s if y is None else y
        pg['items'].append({'type': 'qr', 'url': q['url'], 'label': q.get('label') or '', 'x': x, 'y': y, 'size': size})

    # ---- a chapter's title and the style's marks around it
    def head(self, pg, head, x, y, w, align=None):
        """A chapter title with its small tag under it."""
        title, tag = head
        align = align or self.c.get('title_align') or ('right' if self.rtl else 'left')
        self.text(pg, 'h2', title, x, y, w, align, self.color(self.c.get('title_color')))
        if tag:
            self.text(pg, 'label', tag, x, y + self.pt('h2') + 3 * self.s, w, align)

    def text_w(self, text, cls):
        """About how wide a line of text is, in mm."""
        return len(text or '') * self.c['type'][cls][1] * self.s * 0.3528 * 0.55

    def decorate(self, pg, ill=None):
        """The style's marks on the page that opens a chapter: around its title, and on the page itself."""
        c, s = self.c, self.s
        if pg['tpl'] in ('opener-spread', 'hero', 'jewel', 'blank'):
            return
        texts, items = pg['texts'], pg['items']
        under = pg.setdefault('under', [])
        title = next((t for t in texts if t['cls'] in ('h2', 'h1')), None)
        tag = None
        if title:
            i = texts.index(title)
            tag = next((t for t in texts[i + 1:] if t['cls'] == 'label' and t['y'] > title['y']), None)
        deco = c.get('title_deco')
        acc = c['colors']['accent']
        if title:
            tx, ty, tw, al = title['x'], title['y'], title['w'], title['align']
            th = self.pt(title['cls'])

            def at(w):   # where a box of width w starts, aligned like the title
                return tx + tw - w if al == 'right' else tx if al == 'left' else tx + (tw - w) / 2
            if deco == 'bar':
                items.append({'type': 'rect', 'x': at(36 * s), 'y': ty - 6.5 * s, 'w': 36 * s, 'h': 3.2 * s, 'color': acc})
            elif deco == 'rule2':
                if tag:
                    tag['y'] += 4.5 * s
                items.append({'type': 'rule', 'x': at(18 * s), 'y': ty + th + 1.2 * s, 'w': 18 * s, 'double': True,
                              'color': c.get('keyline') or acc})
            elif deco == 'kicker' and tag:
                tag['y'] = ty
                items.append({'type': 'rule', 'x': tx, 'y': ty + self.pt('label') + 0.6 * s, 'w': tw,
                              'color': c['colors']['ink']})
                title['y'] = ty + self.pt('label') + 3.2 * s
            elif deco == 'stamp':
                parts = (tag['text'] if tag else '').split(' · ')
                date = next((p for p in parts if any(ch.isdigit() for ch in p)), '')
                if date:
                    d = 24 * s
                    room = tw - self.text_w(title['text'], title['cls'])
                    if room > d + 8 * s:   # beside the title, on its other side
                        sx = tx if al != 'left' else tx + tw - d
                        sy = ty - 3 * s
                    else:                   # under it
                        sx, sy = at(d), (tag['y'] if tag else ty + th) + 7 * s
                    items.append({'type': 'stamp', 'x': sx, 'y': sy, 'd': d, 'text': date, 'color': acc})
                    if tag:
                        rest = [p for p in parts if p != date]
                        if rest:
                            tag['text'] = ' · '.join(rest)
                        else:
                            texts.remove(tag)
            elif deco == 'pill' and tag:
                pw = self.text_w(tag['text'], 'label') + 10 * s
                ph_ = self.pt('label') + 1.6 * s
                ta = tag['align']
                px = tag['x'] + tag['w'] - pw if ta == 'right' else tag['x'] if ta == 'left' else tag['x'] + (tag['w'] - pw) / 2
                items.append({'type': 'pill', 'x': px, 'y': tag['y'] - 0.6 * s, 'w': pw, 'h': ph_, 'bg': self.color('ill1'),
                              'color': c['colors']['ink'], 'text': tag['text']})
                texts.remove(tag)
            elif deco == 'tile':
                x0, _, bw, _ = self.area(pg['side'])
                hh = (tag['y'] + self.pt('label') if tag else ty + th) - ty + 9 * s
                under.append({'type': 'rect', 'x': x0, 'y': ty - 4.5 * s, 'w': bw, 'h': hh, 'color': acc})
                for t in (title, tag):
                    if t:
                        t.update(x=t['x'] + 5 * s, w=t['w'] - 10 * s, color='#ffffff' if t is title else 'rgba(255,255,255,.82)')
            elif deco == 'block':
                if pg['tpl'] == 'side' and pg['frames']:
                    f = pg['frames'][0]['clip']
                    bx, bw_ = (0, f[0]) if pg['side'] == 'r' else (f[0] + f[2], self.W - f[0] - f[2])
                    under.append({'type': 'rect', 'x': bx, 'y': 0, 'w': bw_, 'h': self.H, 'color': acc})
                elif pg['tpl'] == 'band' and pg['frames']:
                    f = pg['frames'][0]['clip']
                    under.append({'type': 'rect', 'x': 0, 'y': f[3], 'w': self.W, 'h': self.H - f[3], 'color': acc})
                else:
                    bw_ = self.W * 0.42
                    bx = self.W - bw_ if pg['side'] == 'r' else 0
                    under.append({'type': 'rect', 'x': bx, 'y': 0, 'w': bw_, 'h': self.H, 'color': acc})
                    pad = 9 * s
                    for t in (title, tag):
                        if t:
                            t.update(x=bx + pad, w=bw_ - 2 * pad, align='right' if self.rtl else 'left')
                title['color'] = '#ffffff'
                if tag:
                    tag['color'] = 'rgba(255,255,255,.85)'
            elif deco == 'hand':
                title['rot'] = -2.5
            if deco == 'ill' or c.get('illustrations'):
                name = ill or (c.get('default_ill') if deco == 'ill' else None)
                if name and not any(it['type'] == 'ill' for it in items):
                    sz = 11 * s
                    ix = tx if al == 'right' else tx + tw - sz if al == 'left' else tx + (tw - sz) / 2
                    iy = ty - sz - 3 * s if al == 'center' else ty + (th - sz) / 2
                    if al != 'center' and tw - self.text_w(title['text'], title['cls']) > sz + 8 * s:
                        items.append({'type': 'ill', 'name': name, 'size': sz, 'x': ix, 'y': iy})
                    elif ty - sz - 3 * s > 2 * s:
                        items.append({'type': 'ill', 'name': name, 'size': sz, 'x': at(sz), 'y': ty - sz - 3 * s})
        self.ornament(pg)

    def ornament(self, pg):
        """The style's page ornaments: confetti in the margins, stripes at the edge, an arch behind the photos."""
        c, s = self.c, self.s
        under = pg.setdefault('under', [])
        orn = c.get('ornaments') or []
        def drawn(fr):
            l, t, r, b = (v * s for v in SKINS.get(fr.get('skin') or 'none', SKINS['none']))
            m = 3 * s + abs(fr.get('tilt') or 0) * 0.02 * max(fr['clip'][2], fr['clip'][3])
            x, y, w, h = fr['clip']
            return [x - l - m, y - t - m, w + l + r + 2 * m, h + t + b + 2 * m]
        boxes = [drawn(fr) for fr in pg['frames']] + [[t['x'], t['y'], t['w'], self.pt(t['cls'])] for t in pg['texts']]
        boxes += [[it['x'], it['y'], it.get('w', it.get('d', it.get('size', 0))), it.get('h', it.get('d', it.get('size', 0)))]
                  for it in pg['items'] if 'x' in it and it['type'] != 'dot']
        if 'confetti' in orn:
            k = (pg.get('n') or 0) * 7 + 3
            cands = [(fx * self.W, fy * self.H) for fx, fy in
                     ((.05, .08), (.92, .12), (.08, .55), (.9, .5), (.06, .9), (.88, .92), (.5, .04), (.5, .96),
                      (.15, .3), (.85, .75), (.3, .93), (.7, .06))]
            put = 0
            for j in range(len(cands)):
                x, y = cands[(j + k) % len(cands)]
                r = (3 + (j + k) % 3) * s
                if any(overlap((x - r - 2 * s, y - r - 2 * s, 2 * r + 4 * s, 2 * r + 4 * s), b) for b in boxes):
                    continue
                if not (0 < x - r and x + r < self.W and 0 < y - r and y + r < self.H):
                    continue
                pg['items'].append({'type': 'dot', 'x': x - r, 'y': y - r, 'd': 2 * r, 'color': self.color(f'ill{j + k}')})
                put += 1
                if put == 5:
                    break
        if 'stripes' in orn and pg['tpl'] not in ('cover',):
            cols = [self.color('ill0'), c['colors']['accent'], self.color('ill1'), self.color('ill2')]
            bw = 6.5 * s
            for j, col in enumerate(cols):
                x = self.W - (j + 1) * bw if pg['side'] == 'r' else j * bw
                under.append({'type': 'rect', 'x': x, 'y': 0, 'w': bw, 'h': self.H, 'color': col})
        if 'arch' in orn and pg['frames']:
            xs = [f['clip'] for f in pg['frames']]
            x0 = min(f[0] for f in xs) - 9 * s
            x1 = max(f[0] + f[2] for f in xs) + 9 * s
            y0 = min(f[1] for f in xs) - 0.25 * (x1 - x0)
            if y0 > 2 * s:
                under.append({'type': 'arch', 'x': x0, 'y': y0, 'w': x1 - x0, 'h': self.H - y0, 'color': self.color('ill0')})

    # ---- elements
    def badge(self, pg, small, big):
        """A round badge (a journal's "day 3") beside the chapter title, on the side away from it."""
        title = next((t for t in pg['texts'] if t['cls'] in ('h2', 'h1')), None)
        if not title or any(it['type'] == 'stamp' for it in pg['items']):
            return
        d = 15 * self.s
        al = title['align']
        x = title['x'] if al != 'left' else title['x'] + title['w'] - d
        if al == 'center':
            x = title['x'] + (title['w'] - d) / 2
            title['y'] += d + 2 * self.s
            for t in pg['texts']:
                if t is not title and t['cls'] == 'label' and t['y'] > title['y'] - d - 2 * self.s:
                    t['y'] += d + 2 * self.s
            y = title['y'] - d - 2 * self.s
        else:
            y = title['y'] + (self.pt(title['cls']) - d) / 2
        for it in pg['items']:   # move past an illustration or a stamp already there
            if it['type'] in ('ill', 'stamp') and overlap((x, y, d, d), (it['x'], it['y'], it.get('size', it.get('d', 0)),
                                                                        it.get('size', it.get('d', 0)))):
                x = x + it.get('size', it.get('d', 0)) + 3 * self.s if al != 'left' else x - d - 3 * self.s
        pg['items'].append({'type': 'badge', 'x': x, 'y': y, 'd': d, 'small': small, 'big': str(big),
                            'color': self.c['colors']['accent']})

    def callout(self, pg, photo_id, at, text, ill=None):
        """A note in the page's free space with a hand-drawn arrow to a real detail in a photo (at: its x, y in the
        photo, 0..1). Placed only where there is room for it; returns whether it was."""
        f = next((fr for fr in pg['frames'] if fr['id'] == photo_id), None)
        if f is None or not text:
            return False
        ix, iy, iw, ih = f['img']
        cx, cy, cw, ch = f['clip']
        tx_, ty_ = ix + at[0] * iw, iy + at[1] * ih
        if not (cx <= tx_ <= cx + cw and cy <= ty_ <= cy + ch):
            return False   # the detail is cropped out of this frame
        x0, y0, bw, bh = self.area(pg['side'])
        frames = [fr['clip'] for fr in pg['frames']]
        texts = [(t['x'], t['y'], t['w'], self.pt(t['cls'])) for t in pg['texts']]
        nh = self.pt('label') + 2 * self.s
        nw = self.text_w(text, 'label') + (12 * self.s if ill else 2 * self.s)
        spots = []
        for ny in (self.H - self.mt - nh, y0 + bh - nh, self.mt):
            for nx in (x0, x0 + bw - nw):
                box = (nx, ny, nw, nh)
                if 0 < ny and ny + nh < self.H and not any(overlap(box, b) for b in frames + texts):
                    spots.append((math.hypot(nx + nw / 2 - tx_, ny + nh / 2 - ty_), nx, ny))
        if not spots:
            return False
        _, nx, ny = min(spots)
        align = 'right' if self.rtl else 'left'
        self.text(pg, 'label', text, nx, ny, nw, align)
        if ill:
            sz = nh + 2 * self.s
            pg['items'].append({'type': 'ill', 'name': ill, 'size': sz, 'y': ny - 1.5 * self.s,
                                'x': nx - sz - 1 * self.s if self.rtl else nx + nw + 1 * self.s})
        sx = nx + nw / 2
        sy = ny if ty_ < ny else ny + nh
        pg['items'].append({'type': 'arrow', 'x0': sx, 'y0': sy, 'x1': tx_, 'y1': ty_,
                            'color': self.c['colors']['ink']})
        return True

    # ---- the cover, in the style's own way
    def cover(self, ph, title, subtitle, more=()):
        c, s, W, H = self.c, self.s, self.W, self.H
        kind = c.get('cover', 'centred')
        dark = c.get('cover_dark')
        pg = self.page('cover', 'r', c['colors']['dark'] if dark else None)
        tc = self.color(c.get('title_color'))
        start = 'right' if self.rtl else 'left'
        if ph is None:
            self.text(pg, 'h1', title, 16 * s, H * 0.42, W - 32 * s, 'center', tc)
            self.text(pg, 'label', subtitle, 16 * s, H * 0.42 + self.pt('h1') + 4 * s, W - 32 * s, 'center')
            self.ornament(pg)
            return pg
        if kind in ('side', 'bleed', 'swiss') and ph.a > 0.95:
            kind = 'centred'   # a landscape photo can't hold a column beside it
        if kind == 'side':
            m = 18 * s
            h = H - 2 * m
            w = h * ph.a
            x = W - m - w if self.rtl else m
            self.frame(pg, ph, [x, m, w, h])
            cx, cw = (m, W - 2 * m - w - 7 * s) if self.rtl else (m + w + 7 * s, W - 2 * m - w - 7 * s)
            self.text(pg, 'label', subtitle, cx, m + h, cw, start)
            pg['texts'][-1]['anchor'] = 'bottom'
            self.text(pg, 'h1', title, cx, m + h - self.pt('label') - 2.5 * s, cw, start, tc)
            pg['texts'][-1]['anchor'] = 'bottom'
            if c.get('cover_ill'):
                sz = 12 * s
                pg['items'].append({'type': 'ill', 'name': c['cover_ill'], 'size': sz, 'y': m + h - 62 * s,
                                    'x': cx + cw - sz if self.rtl else cx})
        elif kind == 'bleed':
            w = H * ph.a
            x = W - w if self.rtl else 0
            self.frame(pg, ph, [x, 0, w, H])
            cx, cw = (10 * s, W - w - 14 * s) if self.rtl else (w + 4 * s, W - w - 14 * s)
            words = title.split()
            big, small = (words[-1], ' '.join(words[:-1])) if len(words) > 1 else (title, '')
            self.text(pg, 'label', subtitle, cx, H - 16 * s, cw, start)
            pg['texts'][-1]['anchor'] = 'bottom'
            self.text(pg, 'h1', big, cx, H - 16 * s - self.pt('label') - 2 * s, cw, start, tc)
            pg['texts'][-1]['anchor'] = 'bottom'
            if small:
                self.text(pg, 'label', small, cx, H - 16 * s - self.pt('label') - self.pt('h1') - 3 * s, cw, start)
                pg['texts'][-1]['anchor'] = 'bottom'
        elif kind == 'swiss':
            m = 14 * s
            h = min(H - 2 * m - 22 * s, (W - 2 * m) * 0.66 / ph.a)
            w = h * ph.a
            x = m if self.rtl else W - m - w
            y = H - m - h
            self.frame(pg, ph, [x, y, w, h])
            cx, cw = (x + w + 6 * s, W - 2 * m - w - 6 * s) if self.rtl else (m, W - 2 * m - w - 6 * s)
            pg['items'].append({'type': 'rect', 'x': cx, 'y': y, 'w': cw, 'h': 4 * s, 'color': c['colors']['accent']})
            self.text(pg, 'h1', title, cx, y + 9 * s, cw, start, tc)
            self.text(pg, 'label', subtitle, cx, y + 9 * s + 2.2 * self.pt('h1') + 4 * s, cw, start)
        elif kind == 'block':
            bw = W * 0.41
            bx = 0 if self.rtl else W - bw
            pg.setdefault('under', []).append({'type': 'rect', 'x': bx, 'y': 0, 'w': bw, 'h': H, 'color': c['colors']['accent']})
            h = min(H - 32 * s, (W - 32 * s) * 0.92 / ph.a)
            w = h * ph.a
            x = W - 16 * s - w if self.rtl else 16 * s
            self.frame(pg, ph, [x, 16 * s, w, h], skin=True)
            tx, tw = (12 * s, bw - 24 * s) if self.rtl else (W - bw + 12 * s, bw - 24 * s)
            self.text(pg, 'label', subtitle, tx, H - 16 * s, tw, start, 'rgba(255,255,255,.85)')
            pg['texts'][-1]['anchor'] = 'bottom'
            self.text(pg, 'h1', title, tx, H - 16 * s - self.pt('label') - 2.5 * s, tw, start, '#ffffff')
            pg['texts'][-1]['anchor'] = 'bottom'
        elif kind == 'headline':
            m = 16 * s
            self.text(pg, 'label', subtitle, m, m, W - 2 * m, start)
            pg['items'].append({'type': 'rule', 'x': m, 'y': m + self.pt('label') + 1 * s, 'w': W - 2 * m, 'color': c['colors']['ink']})
            self.text(pg, 'h1', title, m, m + self.pt('label') + 4 * s, W - 2 * m, start, tc)
            top = m + self.pt('label') + 4 * s + self.pt('h1') + 8 * s
            h = H - m - top
            w = min(h * ph.a, W - 2 * m)
            h = w / ph.a
            strip = next((p for p in more if p.crop_ok and p.id != ph.id), None)
            if strip is not None and W - 2 * m - w > 30 * s:
                x = W - m - w if self.rtl else m
                self.frame(pg, ph, [x, H - m - h, w, h])
                sx = m if self.rtl else m + w + 5 * s
                clip = [sx, H - m - h, W - 2 * m - w - 5 * s, h]
                f = best_focus(strip, clip)
                if f:
                    self.frame(pg, strip, clip, f)
            else:
                self.frame(pg, ph, [(W - w) / 2, H - m - h, w, h])
        elif kind == 'polaroid':
            w = min(W * 0.52, H * 0.62 * ph.a)
            h = w / ph.a
            l, t, r, b = (v * s for v in SKINS['polaroid'])
            x, y = (W - w) / 2, 16 * s
            self.frame(pg, ph, [x - l, y - t, w + l + r, h + t + b])
            f = pg['frames'][-1]
            f['tilt'] = -2.5
            f['tape'] = [{'at': 'middle', 'c': self.color('ill0')}]
            f['caption'] = title
            self.text(pg, 'label', subtitle, 18 * s, H - 20 * s, 70 * s, 'left' if self.rtl else 'right')
            pg['texts'][-1]['rot'] = -4
            if c.get('illustrations'):
                pg['items'].append({'type': 'ill', 'name': c.get('cover_ill') or 'heart', 'size': 16 * s,
                                    'x': W - 34 * s if self.rtl else 18 * s, 'y': H - 40 * s})
        elif kind == 'mosaic':
            m, g = 10 * s, max(self.g, 2 * s)
            inner = H - 2 * m
            w5 = min(inner * ph.a, W - 2 * m - 40 * s)
            h5 = w5 / ph.a
            x5 = W - m - w5 if self.rtl else m
            self.frame(pg, ph, [x5, m, w5, h5])
            cw = W - 2 * m - w5 - g
            cx = m if self.rtl else m + w5 + g
            smalls = [p for p in more if p.id != ph.id][:2]
            y = m + h5
            for p in reversed(smalls):
                hh = cw / p.a
                if y - hh < m + 50 * s:
                    break
                y -= hh
                self.frame(pg, p, [cx, y, cw, hh])
                y -= g
            th = y - m
            pg.setdefault('under', []).append({'type': 'rect', 'x': cx, 'y': m, 'w': cw, 'h': th, 'color': c['colors']['accent']})
            self.text(pg, 'label', subtitle, cx + 4 * s, m + th - 5 * s, cw - 8 * s, start, 'rgba(255,255,255,.85)')
            pg['texts'][-1]['anchor'] = 'bottom'
            self.text(pg, 'h1', title, cx + 4 * s, m + th - 5 * s - self.pt('label') - 2 * s, cw - 8 * s, start, '#ffffff')
            pg['texts'][-1]['anchor'] = 'bottom'
        else:   # centred: the photo large on one axis, the words under it
            w = min(W * 0.56, (H * 0.64) * ph.a, W - 40 * s)
            h = w / ph.a
            top = 16 * s
            sk = SKINS.get(self.skin, SKINS['none'])
            l, t, r, b = (v * s for v in sk)
            x = (W - w) / 2
            if c.get('cover_arch'):
                aw = w + 36 * s
                pg.setdefault('under', []).append({'type': 'arch', 'x': (W - aw) / 2, 'y': top - 2 * s, 'w': aw,
                                                   'h': H - top + 2 * s, 'color': self.color('ill1')})
                top += 14 * s
            if c.get('cover_stripes'):
                cols = [self.color('ill0'), c['colors']['accent'], self.color('ill1'), self.color('ill2')]
                for j, col in enumerate(cols):
                    pg.setdefault('under', []).append({'type': 'rect', 'x': 0, 'y': top + h - 14 * s + j * 6.5 * s,
                                                       'w': W, 'h': 6.5 * s, 'color': col})
            self.frame(pg, ph, [x - l, top - t, w + l + r, h + t + b])
            y = top + h + b + 9 * s
            if c.get('cover_ill'):
                sz = 10 * s
                pg['items'].append({'type': 'ill', 'name': c['cover_ill'], 'size': sz, 'x': (W - sz) / 2, 'y': y - 3 * s})
                y += sz
            if c.get('cover_stripes'):
                y += 6 * s
            self.text(pg, 'h1', title, 12 * s, y, W - 24 * s, 'center', tc)
            y += self.pt('h1') + 3 * s
            if c.get('title_deco') == 'rule2':
                pg['items'].append({'type': 'rule', 'x': W / 2 - 9 * s, 'y': y, 'w': 18 * s, 'double': True,
                                    'color': c.get('keyline') or c['colors']['accent']})
                y += 4.5 * s
            if c.get('title_deco') == 'pill':
                pw = self.text_w(subtitle, 'label') + 10 * s
                pg['items'].append({'type': 'pill', 'x': (W - pw) / 2, 'y': y, 'w': pw, 'h': self.pt('label') + 1.6 * s,
                                    'bg': self.color('ill1'), 'color': c['colors']['ink'], 'text': subtitle})
            elif c.get('title_deco') == 'stamp':
                d = 28 * s
                pg['items'].append({'type': 'stamp', 'x': 20 * s, 'y': top + h + b - 4 * s, 'd': d, 'text': subtitle,
                                    'color': c['colors']['accent']})
            else:
                self.text(pg, 'label', subtitle, 12 * s, y, W - 24 * s, 'center')
        self.ornament(pg)
        return pg


# ---------------------------------------------------------------- the planner
# First a plan in words (a list of specs: which template, which photos), then the page count is fitted and the
# pacing rules applied on that plan, and only then are the pages drawn: a page's side (left or right) changes
# its geometry, and it is known only once the count is final.

def spec(tpl, photos, **kw):
    return dict(tpl=tpl, photos=list(photos), span=2 if tpl == 'opener-spread' else 1, **kw)


def resolve_highlight(d, p, story=None):
    """A highlight: edge to edge in its own shape, else filling the page where a crop is safe, else alone."""
    if not d.c.get('edge', True):
        return spec('fill', [p])
    if d.side_ok(p):
        return spec('side', [p], story=story)
    if d.band_ok(p):
        return spec('band', [p])
    if p.crop_ok and sharp_enough(p, d.W, d.H) and best_focus(p, [0, 0, d.W, d.H]):
        return spec('hero', [p])
    return spec('quiet', [p], scale=0.86)


def plan_chapter(d, ch, photos, moment_of, spread_ok):
    hl, quiet, details = set(ch.get('highlights') or []), set(ch.get('quiet') or []), set(ch.get('details') or [])
    order = [photos[i] for i in ch['photos'] if i in photos]
    if not order:
        return []
    title, deck = ch.get('title') or '', ch.get('deck') or ''
    specs, used = [], set()
    cands = [p for p in order if p.id in hl][:2] + order[:3]
    cands = [p for i, p in enumerate(cands) if p not in cands[:i] and p.id not in details]
    bold = d.c.get('opener_spreads')   # true: any chapter may open across a spread; "marked": only those marked
    if spread_ok and ch.get('open') != 'page' and (bold is True or (bold == 'marked' and ch.get('open') == 'spread')):
        for p in cands:
            if d.opener_spread(p, title, deck, 'r'):
                specs.append(spec('opener-spread', [p], title=title, deck=deck))
                used.add(p.id)
                break
    if not specs and d.c.get('edge', True):
        for p in cands:
            if d.band_ok(p):
                specs.append(spec('band', [p], title=title, deck=deck, qr=ch.get('qr')))
            elif d.side_ok(p):
                specs.append(spec('side', [p], title=title, deck=deck, story=ch.get('story'), qr=ch.get('qr')))
            else:
                continue
            used.add(p.id)
            break
    head = None if specs else (title, deck)
    story = ch.get('story') if not any(s.get('story') for s in specs) else None
    qr = ch.get('qr') if not any(s.get('qr') for s in specs) else None
    group = []

    x0_, y0_, bw_, bh_ = d.area('r')

    def fits(a, b):   # how well two photos fill a page together
        lay = fill_layout([a, b], bw_, bh_, d.g)
        return lay[0] if lay else 0

    def flush():
        g = list(group)
        for k in range(0, len(g) - 1, 2):   # a photo may swap with a near neighbour, so the pair's shapes suit a page
            best = max(range(k + 1, min(k + 4, len(g))), key=lambda j: fits(g[k], g[j]) + (0.04 if j == k + 1 else 0))
            if best != k + 1:
                g[k + 1], g[best] = g[best], g[k + 1]
        for k in range(0, len(g), 2):  # two a page to start with; fit() then joins or splits them
            specs.append(spec('fill', g[k:k + 2]))
        group.clear()
    for p in order:
        if p.id in used:
            continue
        if p.id in hl or p.id in quiet or p.id in details:
            flush()
            if p.id in details:
                specs.append(spec('jewel', [p]))
            elif p.id in quiet:
                specs.append(spec('quiet', [p]))
            else:
                specs.append(resolve_highlight(d, p, story))
                if specs[-1].get('story'):
                    story = None
        else:
            group.append(p)
    flush()
    first = next((s for s in specs if s['tpl'] != 'opener-spread'), None)
    if head and specs:
        specs[0]['head'] = head
    if first is not None:
        if qr and not first.get('qr'):
            first['qr'] = qr
        if story and first['tpl'] in ('fill', 'side') and not first.get('story'):
            first['story'] = story
    for s in specs:
        s['chapter'] = title
        s['moments'] = {moment_of.get(p.id) for p in s['photos']}
    return specs


def count(specs):
    return sum(s['span'] for s in specs)


def fit(specs, budget):
    """Reach the budget: join neighbouring fill pages (of one moment first, 4 photos at most), or split them."""
    def joinable(i):
        a, b = specs[i], specs[i + 1]
        return a['tpl'] == b['tpl'] == 'fill' and len(a['photos']) + len(b['photos']) <= 4 and not b.get('head')
    while count(specs) > budget:
        ks = [i for i in range(len(specs) - 1) if joinable(i)]
        if not ks:
            ks = [i for i in range(len(specs) - 1)   # a quiet page or a highlight gives way to its neighbour
                  if specs[i]['tpl'] == 'fill' and specs[i + 1]['tpl'] in ('quiet', 'hero') and len(specs[i]['photos']) <= 3]
            if not ks:
                break
        i = min(ks, key=lambda i: (len(specs[i]['moments'] | specs[i + 1]['moments']) > 1,
                                   len(specs[i]['photos']) + len(specs[i + 1]['photos'])))
        a, b = specs[i], specs[i + 1]
        specs[i:i + 2] = [dict(a, tpl='fill', photos=a['photos'] + b['photos'], moments=a['moments'] | b['moments'], span=1)]
    while count(specs) < budget:
        ks = [i for i, s in enumerate(specs) if s['tpl'] == 'fill' and len(s['photos']) > 1]
        if not ks:
            break
        i = max(ks, key=lambda i: len(specs[i]['photos']))
        s = specs[i]
        h = (len(s['photos']) + 1) // 2
        specs[i:i + 1] = [dict(s, photos=s['photos'][:h]), dict(s, photos=s['photos'][h:], head=None, qr=None, story=None)]
    return specs


def tidy(d, specs):
    """Pacing, without changing the count: the same single-page template twice in a row becomes a fill page,
    and edge-to-edge pages are kept within the concept's share (titled pages stay)."""
    for i in range(1, len(specs)):
        a, b = specs[i - 1], specs[i]
        if a['tpl'] == b['tpl'] and b['tpl'] in ('band', 'side', 'hero', 'quiet', 'jewel') and not b.get('title'):
            specs[i] = dict(b, tpl='fill')
    total = count(specs)
    # a page with one photo gets a stronger layout when the edge budget allows and its neighbours differ
    for i, sp in enumerate(specs):
        if sp['tpl'] != 'fill' or len(sp['photos']) != 1 or sp.get('head') or sp.get('qr') or sp.get('story'):
            continue
        p = sp['photos'][0]
        prev = specs[i - 1]['tpl'] if i else None
        nxt = specs[i + 1]['tpl'] if i + 1 < len(specs) else None
        edge_now = sum(s['span'] for s in specs if s['tpl'] in EDGE)
        if edge_now + 1 <= d.c.get('edge_share', .45) * total:
            for tpl, ok in (('side', d.side_ok(p)), ('band', d.band_ok(p))):
                if ok and tpl not in (prev, nxt):
                    specs[i] = dict(sp, tpl=tpl)
                    break
        if specs[i]['tpl'] == 'fill' and 'quiet' not in (prev, nxt) and i % 3 == 1:
            specs[i] = dict(sp, tpl='quiet')
    for i in reversed(range(len(specs))):
        if sum(s['span'] for s in specs if s['tpl'] in EDGE) <= d.c.get('edge_share', .45) * total + 1:
            break
        if specs[i]['tpl'] in ('side', 'band', 'hero') and not specs[i].get('title'):
            specs[i] = dict(specs[i], tpl='fill')
    return specs


def draw(d, s, n):
    """The page(s) of one spec, starting at inside page n."""
    side = d.side(n)
    p = s['photos'][0]
    t = s['tpl']
    if t == 'opener-spread' and n % 2:   # a spread must start on an even page; else the chapter opens on one page
        t = 'band' if d.band_ok(p) else 'side' if d.side_ok(p) else 'fill'
        s = dict(s, tpl=t, head=None if t != 'fill' else (s['title'], s['deck']))
    if s.get('head') and t == 'hero':   # a chapter never opens with its title over a full-page photo
        t = 'fill'
    if s.get('head') and t in ('band', 'side'):   # these set a title themselves, by the photo
        s = dict(s, title=s['head'][0], deck=s['head'][1], head=None)
    if t == 'opener-spread':
        pages = d.opener_spread(p, s['title'], s['deck'], side)
    elif t == 'band':
        pages = [d.band(side, p, s.get('title'), s.get('deck'), qr=s.get('qr'))]
    elif t == 'side':
        pages = [d.side_page(side, p, s.get('title'), s.get('deck'), story=s.get('story'), qr=s.get('qr'))]
    elif t == 'hero':
        pages = [d.hero(side, p) or d.quiet(side, p, scale=0.86)]
    elif t == 'quiet':
        pages = [d.quiet(side, p, scale=s.get('scale'))]
    elif t == 'jewel':
        pages = [d.jewel(side, p)]
    else:
        running = None if s.get('head') or not d.c.get('running_heads', True) else s.get('chapter')
        if running and d.c.get('times'):   # a journal: the hours of this page's photos
            ts = sorted(p.taken[11:16] for p in s['photos'] if p.taken and len(p.taken) >= 16)
            if ts:
                running += f' · {ts[0]}' + (f'–{ts[-1]}' if ts[-1] != ts[0] else '')
        pages = [d.fill(side, s['photos'], head=s.get('head'), running=running,
                        qr=s.get('qr'), illustration=s.get('illustration') if s.get('head') else None)]
        if s.get('story'):
            pg = pages[0]
            pg['texts'].append({'cls': 'story', 'text': s['story'], 'x': d.area(side)[0], 'y': d.H - d.mt - 12 * d.s,
                                'w': d.area(side)[2], 'align': 'right' if d.rtl else 'left', 'color': None})
    if s.get('head') and t != 'fill':   # a quiet page or a document: the title and its tag right under the photo
        pg0 = pages[0]
        if pg0['frames']:
            fx, fy, fw, fh = pg0['frames'][0]['clip']
            sk = SKINS.get(pg0['frames'][0].get('skin') or 'none', SKINS['none'])
            pg0['texts'] = [x for x in pg0['texts'] if x['cls'] != 'label']   # the head replaces a caption
            d.head(pg0, s['head'], fx, fy + fh + (sk[3] + 5) * d.s, fw)
        else:
            x0, _, bw, _ = d.area(side)
            d.head(pg0, s['head'], x0, d.mt, bw)
    for k, pg in enumerate(pages):
        pg['chapter'] = s.get('chapter')
        pg['opens'] = bool(s.get('title') or s.get('head')) and k == 0
    return pages


# ---------------------------------------------------------------- the rules

def check(d, pages, photos_by_id, goal=None, chapters=()):
    """[(rule, passed, note)]: the rules every book must meet."""
    out = []
    inner = [p for p in pages if p.get('n')]
    if goal:
        out.append(('the page count the user chose', len(inner) == goal, f'{len(inner)} of {goal}'))
    tpls = [p['tpl'] for p in inner]
    rep = [p['n'] for a, p in zip(inner, inner[1:]) if a['tpl'] == p['tpl'] and p['tpl'] not in ('fill', 'opener-spread', 'blank')
           and not (a.get('opens') and p.get('opens'))]   # two short chapters may open alike
    out.append(('no layout twice in a row', not rep, f'pages {rep}' if rep else ''))
    edge = sum(t in EDGE for t in tpls)
    out.append(('edge-to-edge pages within the style\'s share', edge <= d.c.get('edge_share', .45) * len(tpls) + 2,
                f'{edge} of {len(tpls)}'))
    cut, spine, covered, unknown = [], [], [], []
    for p in pages:
        for f in p['frames']:
            ph = photos_by_id[f['id']]
            if f['cropped']:
                if not ph.crop_ok:
                    unknown.append(ph.id)
                elif not crop_safe(ph, f['clip'], f['img']):
                    cut.append(ph.id)
            if p['tpl'] == 'opener-spread':
                for fx, fy, fw, fh in faces_mm(ph, f['img'], main=True):   # the spine: the edge that meets the other page
                    edge = 0 if p['side'] == 'r' else d.W
                    if fx - d.gutter < edge < fx + fw + d.gutter:
                        spine.append(ph.id)
                for t in p['texts']:
                    tb = (t['x'], t['y'], t['w'], (24 if t['cls'] == 'hero' else 8) * d.s)
                    if any(overlap(tb, b) for b in bodies(ph, f['img'])):
                        covered.append(ph.id)
    out.append(('no crop cuts a face, or the feet', not cut, f'photos {sorted(set(cut))}' if cut else ''))
    out.append(('a photo of people is cropped only when its faces are known', not unknown,
                f'photos {sorted(set(unknown))}' if unknown else ''))
    out.append(('no face in the spine', not spine, f'photos {sorted(set(spine))}' if spine else ''))
    out.append(('no title covers a person', not covered, f'photos {sorted(set(covered))}' if covered else ''))
    seen = {}
    for p in inner:
        if p['tpl'] in ('opener-spread', 'title'):   # a spread shows one photo twice; the title page echoes the cover
            continue
        for f in p['frames']:
            seen.setdefault(f['id'], []).append(p['n'])
    twice = sorted(i for i, ns in seen.items() if len(ns) > 1)
    out.append(('each photo once inside the book', not twice, f'photos {twice}' if twice else ''))
    thin, loose = [], []
    for p in inner:
        if p['tpl'] != 'fill' or not p['frames']:
            continue
        x0, y0, bw, bh = d.area(p['side'])
        boxes = []
        for f in p['frames']:   # a photo with its frame (a mat, a polaroid) is what the eye sees
            l_, t_, r_, b_ = (v * d.s for v in SKINS.get(f.get('skin') or 'none', SKINS['none']))
            x, y, w, h = f['clip']
            boxes.append((x - l_, y - t_, w + l_ + r_, h + t_ + b_))
        if sum(b[2] * b[3] for b in boxes) / (bw * bh) < 0.33:
            thin.append(p['n'])

        def gap(a, b):
            return math.hypot(max(0, b[0] - a[0] - a[2], a[0] - b[0] - b[2]), max(0, b[1] - a[1] - a[3], a[1] - b[1] - b[3]))
        words = [(t['x'], t['y'], t['w'], d.pt(t['cls'])) for t in p['texts']
                 if t['cls'] in ('h1', 'h2', 'label', 'story') and t['y'] >= d.mt - 1]   # a running head stays up top
        near_items = [(i['x'], i['y'], i.get('w', i.get('d', 0)), i.get('h', i.get('d', 0))) for i in p['items']
                      if i['type'] in ('pill', 'stamp', 'badge')]   # a tag drawn as a shape belongs to the words
        words += near_items
        near = list(boxes)
        todo = list(words)
        while True:   # words by a photo, or by words that are by a photo (a tag under its title)
            hit = [w for w in todo if min(gap(w, b) for b in near) <= 16 * d.s]
            if not hit:
                break
            near += hit
            todo = [w for w in todo if w not in hit]
        if todo:
            loose.append(p['n'])
    out.append(('the photos fill the page', not thin, f'pages {thin}' if thin else ''))
    out.append(('words sit by their photos', not loose, f'pages {loose}' if loose else ''))
    opened = {p['chapter'] for p in inner if p.get('opens')}
    missing = [c['title'] for c in chapters if c.get('title') and c['title'] not in opened]
    out.append(('every chapter opens with its title', not missing, ', '.join(missing)))
    return out
