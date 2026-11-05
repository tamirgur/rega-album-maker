"""The three levels of a book's look, each a file in assets/:

    structure   structures.json   how the story is told: the pace, photos a page, how deep the elements go
    style       styles/*.json     how it looks: type, frames, paper, ornaments, the cover
    palette     palettes.json     its colours, by role: paper, ink, label, accent, tints, dark, endpaper, ill

resolve() merges them into the one dict the designer and the renderer use.
"""
import colorsys
import os

from common import ASSETS, load

STYLE_DIR = os.path.join(ASSETS, 'styles')
# names from earlier versions
STYLE_ALIASES = {'magazine': 'newspaper', 'editorial': 'newspaper', 'gallery': 'minimal', 'album': 'classic'}
PALETTE_ALIASES = {'warm': 'sand', 'cool': 'mist'}
ROLES = ('paper', 'ink', 'label', 'accent', 'tints', 'dark', 'endpaper', 'ill')


def styles():
    return sorted((load(os.path.join(STYLE_DIR, f)) for f in os.listdir(STYLE_DIR) if f.endswith('.json')),
                  key=lambda s: s.get('n', 99))


def style_names():
    return [s['name'] for s in styles()]


def palettes():
    return {k: v for k, v in load(os.path.join(ASSETS, 'palettes.json')).items() if not k.startswith('_')}


def structures():
    return {k: v for k, v in load(os.path.join(ASSETS, 'structures.json')).items() if not k.startswith('_')}


def load_style(name):
    """A style by name, or the book's own style file: its values over those of the style it is "based" on."""
    if os.path.isfile(name):
        own = load(name)
        s = load_style(own.get('base', 'minimal'))
        for k, v in own.items():
            s[k] = dict(s[k], **v) if isinstance(v, dict) and isinstance(s.get(k), dict) else v
        return s
    name = STYLE_ALIASES.get(name, name)
    path = os.path.join(STYLE_DIR, f'{name}.json')
    if not os.path.isfile(path):
        raise ValueError(f'Unknown style "{name}". There are: {", ".join(style_names())}')
    return load(path)


def _hex(rgb):
    return '#%02x%02x%02x' % tuple(int(max(0, min(255, round(v)))) for v in rgb)


def photo_colours(paths, n=3):
    """The colours that are really in the photos and would make a good accent: saturated, of middle lightness,
    even if they cover little (the tablecloths, not the lawn). The strongest first, then ones of other hues."""
    from PIL import Image
    tiles = []
    for p in list(paths)[:40]:
        try:
            with Image.open(p) as im:
                tiles.append(im.convert('RGB').resize((64, 48)))
        except OSError:
            continue
    if not tiles:
        return []
    m = Image.new('RGB', (64 * len(tiles), 48))
    for k, t in enumerate(tiles):
        m.paste(t, (64 * k, 0))
    q = m.quantize(colors=48, method=Image.Quantize.MEDIANCUT)
    pal, total, cols = q.getpalette(), m.width * m.height, []
    for cnt, c in q.getcolors():
        h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in pal[3 * c:3 * c + 3]))
        cols.append((cnt / total, h, l, s))
    good = [c for c in cols if c[0] > 0.003 and 0.2 < c[2] < 0.7 and c[3] > 0.18] or cols
    good.sort(key=lambda c: -c[3] * min(1, c[0] / 0.02))
    out = []
    for share, h, l, s in good:
        if all(min(abs(h - o[0]), 1 - abs(h - o[0])) > 0.08 for o in out):
            out.append((h, l, s))
        if len(out) == n:
            break
    return out


def tone(hls, lightness, sat_cap):
    h, l, s = hls
    return _hex([v * 255 for v in colorsys.hls_to_rgb(h, lightness, min(s, sat_cap))])


def resolve(style, palette=None, structure=None, photo_paths=()):
    """The book's look: the style, coloured by the palette, told in the structure."""
    s = load_style(style)
    pals = palettes()
    want = palette if palette not in (None, 'concept', 'style') else s['palette']
    if isinstance(want, str):
        want = PALETTE_ALIASES.get(want, want)
        if want not in pals:
            raise ValueError(f'Unknown palette "{want}". There are: {", ".join(pals)}, or a brand {{"accent": "#..."}}')
    base = s.get('base_palette') or s['palette']
    if isinstance(want, str) and not pals[want].get('auto'):
        base = want
    if pals.get(base, {}).get('auto'):
        base = 'neutral'
    colors = {k: v for k, v in pals[base].items() if k in ROLES}
    colors['tints'] = list(colors.get('tints') or [])
    colors['ill'] = list(colors.get('ill') or [])
    if s.get('paper') and want in (s['palette'], s.get('base_palette')):   # the style's own paper, with its own palette
        colors['paper'] = s['paper']
        if colors['tints']:
            colors['tints'][0] = s['paper']
    found = photo_colours(photo_paths) if photo_paths and (want == 'photos' or pals[base].get('accent_from_photos')) else []
    if found:
        r, g, b_ = (int(colors['paper'][i:i + 2], 16) / 255 for i in (1, 3, 5))
        night = 0.2126 * r + 0.7152 * g + 0.0722 * b_ < 0.35   # on a dark page the accent must be light
        colors['accent'] = tone(found[0], 0.68 if night else 0.42, 0.62)
        if want == 'photos':
            colors['ill'] = [tone(c, 0.55, 0.6) for c in found] + colors['ill'][len(found):]
            colors['tints'] = [colors['paper']] + [tone(c, 0.93, 0.25) for c in found[:2]]
    if isinstance(want, dict):   # a brand: its colours over the style's palette
        colors.update({k: v for k, v in want.items() if k in ROLES})
    s['colors'] = colors
    s['palette_name'] = want if isinstance(want, str) else 'brand'
    keyline = s.get('keyline')
    if keyline and keyline.startswith('ill') and colors['ill']:
        s['keyline'] = colors['ill'][int(keyline[3:] or 0) % len(colors['ill'])]
    # the structure: the pace and the depth, over the style's own defaults
    structure = structure or 'album'
    if structure not in s.get('structures', list(structures())):   # a magazine needs photos that run to the edge
        s['structure_note'] = (f'{s["en"]} keeps photos inside the margins, so a {structure} would look like an album: '
                               f'use {" or ".join(s["structures"])}, or a style that bleeds (Minimal, Colourful, Bold, '
                               f'Newspaper, Swiss)')
        structure = 'journal' if 'journal' in s.get('structures', []) else 'album'
    st = structures().get(structure) or structures()['album']
    s['structure'] = structure
    for k in ('opener_spreads', 'running_heads', 'badges', 'times', 'depth', 'per_page'):
        if k in st:
            s[k] = st[k]
    if s['structure'] == 'magazine' and s.get('edge', True):
        s['edge_share'] = min(0.7, s.get('edge_share', 0.3) + st.get('edge_bonus', 0))
    if not s.get('edge', True):
        s['opener_spreads'] = False   # a style that keeps every photo inside the margins opens no spread
    if not s.get('tints'):
        s['tints_list'] = []
    else:
        s['tints_list'] = colors['tints']
    return s


def per_page(brief):
    """Photos a page, from the structure in the brief."""
    st = ((brief or {}).get('design') or {}).get('structure') or 'album'
    return structures().get(st, {}).get('per_page', 1.9)
