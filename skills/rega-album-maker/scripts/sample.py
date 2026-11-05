#!/usr/bin/env python3
"""Show the looks on the user's own photos, before anything is chosen, so they choose by eye.

    python sample.py --work WORK --gallery                         # all 15 styles: the cover of each
    python sample.py --work WORK --styles nordic,kids,classic       # the cover and a spread in each style
    python sample.py --work WORK --style kids --palettes vivid,pastel,photos
    python sample.py --work WORK --style kids --structures          # one chapter as an album, a journal, a magazine
    ... [--cover ID] [--photos ID,ID,...]                            # your own pick for the cover and the spread

It picks a cover and a few strong photos from the scan by itself (the user's real selection comes later), builds a
small book in each look with the real layout and renderer, from the scan's thumbnails (fast, and no cloud photo is
downloaded for a sample), and puts the results side by side in one image, WORK/samples/<name>.png (and .pdf).

The image opens on the user's screen by itself (--no-open, or REGA_NO_OPEN=1, to skip): Claude reading an image does
not show it to the user. Read it too, to check it.
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fmt_range, is_rtl, load, save, words  # noqa: E402
from looks import load_style, palettes, structures, style_names  # noqa: E402
from render import fonts_css, print_pdf  # noqa: E402
from scan import EXCLUDE  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    import pymupdf  # noqa: F401  (the samples are cut from the rendered PDFs)
except ImportError:
    try:
        import fitz as pymupdf  # noqa: F401
    except ImportError:
        sys.exit('sample.py needs PyMuPDF: pip install pymupdf (or pip install -r requirements.txt)')


def provisional(work, brief, cover=None, photos=None):
    """A cover and two short chapters of strong photos, picked from the scan (or given): only for the samples."""
    scan = load(os.path.join(work, 'scan.json'))
    groups = load(os.path.join(work, 'groups.json'))
    byid = {r['id']: r for r in scan['items']}

    def good(i):
        r = byid.get(i)
        return r and r['kind'] == 'photo' and r.get('in_range', True) and not set(r['flags']) & EXCLUDE \
            and 'error' not in r['flags']
    chunks = []
    for d in groups['days']:
        ms = d.get('moments') or [{'ids': d['ids'], 'key': False}]
        for m in sorted(ms, key=lambda m: (not m.get('key'), -len(m['ids']))):
            ids = [i for i in m['ids'] if good(i)]
            if len(ids) >= 3:
                chunks.append((d, ids))
    if photos:
        ids = [i for i in photos if i in byid]
        chunks = [({'n': 1, 'key': byid[ids[0]].get('day') or ''}, ids[:len(ids) // 2 or 1]),
                  ({'n': 2, 'key': byid[ids[-1]].get('day') or ''}, ids[len(ids) // 2 or 1:])]
        chunks = [c for c in chunks if c[1]]
    if not chunks:
        sys.exit('Not enough good photos in the scan to make samples.')
    chunks.sort(key=lambda c: -len(c[1]))
    chunks = sorted(chunks[:2], key=lambda c: c[0]['key'])
    lang = (brief.get('book') or {}).get('lang') or groups.get('lang') or 'en'
    used, chapters = set(), []
    for d, ids in chunks:
        best = sorted(ids, key=lambda i: -byid[i].get('score', 0))[:6]
        best.sort(key=lambda i: byid[i]['taken'] or '')
        used.update(best)
        chapters.append({'title': (words(lang)['day'] + f' {d["n"]}'), 'photos': best,
                         'highlights': [max(best, key=lambda i: byid[i].get('score', 0))]})
    rest = [i for d, ids in chunks for i in ids if i not in used]
    people = [i for i in rest if byid[i].get('faces')] or rest or [chapters[0]['photos'][0]]
    cover = cover if cover in byid else max(people, key=lambda i: (len(byid[i].get('faces') or []) > 0, byid[i].get('score', 0)))
    days = sorted(d['key'] for d in groups['days'])
    title = (brief.get('book') or {}).get('title') or ('האלבום שלנו' if lang == 'he' else 'Our album')
    sub = fmt_range(date.fromisoformat(days[0]), date.fromisoformat(days[-1]), lang) if days else ''
    return {'title': title, 'subtitle': sub, 'lang': lang, 'cover': cover, 'closing': None, 'no_people': [],
            'chapters': chapters}


def build_many(work, brief, sel, jobs):
    """Several looks at once, a few browsers side by side (each look in its own folder): [(imgs, rtl)] in order."""
    from concurrent.futures import ThreadPoolExecutor
    n = max(1, min(4, (os.cpu_count() or 2) // 2, len(jobs)))
    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = [ex.submit(build, work, brief, sel, *j) for j in jobs]
        return [f.result() for f in futs]


def build(work, brief, sel, style, palette, structure, tag):
    """One small book in one look; returns the page images (cover, first spread) as files."""
    sw = os.path.join(work, 'samples', '_work', tag)
    os.makedirs(sw, exist_ok=True)
    for f in ('scan.json', 'groups.json'):
        src, dst = os.path.join(work, f), os.path.join(sw, f)
        if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            continue
        if f == 'scan.json':   # the samples are small: draw them from the thumbnails, never the originals
            scan = load(src)
            for r in scan['items']:
                if r.get('kind') == 'photo' and r.get('thumb') and os.path.isfile(r['thumb']):
                    r['path'] = r['thumb']
            save(dst, scan)
        else:
            shutil.copyfile(src, dst)
    b = {k: v for k, v in brief.items() if k in ('book', 'print')}
    fmt = dict(brief.get('format') or {})
    fmt['pages'] = 6
    fmt['min_pages'] = 2
    b['format'] = fmt
    b['design'] = {'structure': structure, 'style': style, 'palette': palette, 'elements': {'route_map': False}}
    save(os.path.join(sw, 'brief.json'), b)
    save(os.path.join(sw, 'selection.json'), sel)
    for script in ('layout.py', 'render.py'):
        args = [sys.executable, os.path.join(HERE, script), '--work', sw] + (['--pad'] if script == 'layout.py' else [])
        r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if r.returncode:
            sys.exit(f'{script} failed for {tag}:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}')
    import pymupdf
    book = load(os.path.join(sw, 'book.json'))
    pages = book['pages']
    op = next((i for i, p in enumerate(pages) if p.get('opens') and p.get('n', 0) >= 2), 2)
    if pages[op]['side'] == ('l' if book['dir'] == 'rtl' else 'r'):   # show the spread the opener sits in
        op -= 1
    out = []
    with pymupdf.open(os.path.join(sw, 'book.pdf')) as d:
        for k, i in (('cover', 0), ('a', op), ('b', op + 1)):
            if i < d.page_count:
                p = os.path.join(work, 'samples', f'{tag}-{k}.png')
                d[i].get_pixmap(dpi=60).save(p)
                out.append(p)
    return out, book['dir'] == 'rtl'


def sheet(work, name, rows, title, covers_only=False, lang='en'):
    """The samples side by side, labelled, as a PDF and a PNG."""
    u = lambda p: Path(p).as_uri()  # noqa: E731
    cells = []
    for label, sub, imgs, rtl in rows:
        if covers_only:
            cells.append(f'<div class="c"><img src="{u(imgs[0])}"><b>{label}</b><span>{sub}</span></div>')
        else:
            a, b = (imgs[1], imgs[2]) if len(imgs) > 2 else (imgs[1], imgs[1])
            first, second = (b, a) if rtl else (a, b)   # the spread as it lies open: left page on the left
            cells.append(f'<div class="r"><div class="h"><b>{label}</b><span>{sub}</span></div>'
                         f'<img src="{u(imgs[0])}"><i></i><img src="{u(first)}"><img src="{u(second)}"></div>')
    css = f'''{fonts_css()}
@page{{size:{297 if covers_only else 280}mm {40 + 92 * ((len(rows) + 4) // 5) if covers_only else 72 * len(rows) + 30}mm;margin:0}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:Assistant;background:#3c3c3c;color:#eee;padding:8mm}}
h1{{font:300 15pt Assistant;margin-bottom:5mm}}
.g{{display:grid;grid-template-columns:repeat(5,1fr);gap:5mm}}
.c img{{width:100%;display:block;box-shadow:0 .6mm 2mm rgba(0,0,0,.4)}}
.c b{{display:block;font:600 11pt Assistant;margin-top:1.5mm}} .c span{{font:300 8.5pt Assistant;color:#bbb}}
.r{{display:flex;align-items:flex-end;gap:2mm;margin-bottom:6mm;direction:ltr}}
.r .h{{width:42mm;direction:rtl;text-align:right}} .r .h b{{display:block;font:600 12pt Assistant}} .r .h span{{font:300 8.5pt Assistant;color:#bbb}}
.r img{{height:52mm;display:block;box-shadow:0 .6mm 2mm rgba(0,0,0,.4)}} .r i{{width:6mm}}
'''
    body = f'<h1>{title}</h1>' + (f'<div class="g">{"".join(cells)}</div>' if covers_only else ''.join(cells))
    d_ = 'rtl' if is_rtl(lang) else 'ltr'
    html = f'<!doctype html><html lang="{lang}" dir="{d_}"><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>'
    hp = os.path.join(work, 'samples', f'{name}.html')
    with open(hp, 'w', encoding='utf-8') as f:
        f.write(html)
    pdf = os.path.join(work, 'samples', f'{name}.pdf')
    print_pdf(hp, pdf)
    import pymupdf
    png = os.path.join(work, 'samples', f'{name}.png')
    from PIL import Image
    with pymupdf.open(pdf) as d:   # one image, even if the sheet ran over a page
        ims = []
        for pg in d:
            pix = pg.get_pixmap(dpi=110)
            ims.append(Image.frombytes('RGB', (pix.width, pix.height), pix.samples))
    out = Image.new('RGB', (max(i.width for i in ims), sum(i.height for i in ims)), (60, 60, 60))
    y = 0
    for i in ims:
        out.paste(i, (0, y))
        y += i.height
    from PIL import ImageChops
    box = ImageChops.difference(out, Image.new('RGB', out.size, (60, 60, 60))).getbbox()
    if box:   # no empty band under the last row
        out = out.crop((0, 0, out.width, min(out.height, box[3] + 40)))
    out.save(png)
    print(png)
    if SHOW:
        print('Opened on the user\'s screen.' if show(png) else
              f'Could not open it here: give the user this link to open it: {Path(png).as_uri()}')
    return png


SHOW = True


def show(path):
    """Open the image in the computer's own viewer, so the user sees it. False where there is no screen."""
    if os.environ.get('REGA_NO_OPEN', '').strip() not in ('', '0'):
        return False
    try:
        if sys.platform == 'win32':
            os.startfile(path)   # noqa: S606 - the user's own image viewer
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
            subprocess.Popen(['xdg-open', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            return False   # a sandbox with no screen (Cowork): the link is the way
        return True
    except (OSError, AttributeError):
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work', required=True)
    ap.add_argument('--gallery', action='store_true')
    ap.add_argument('--styles')
    ap.add_argument('--style')
    ap.add_argument('--palettes')
    ap.add_argument('--structures', action='store_true')
    ap.add_argument('--cover', type=int, help='the photo for the sample cover (an id from the sheets)')
    ap.add_argument('--photos', help='ids for the sample chapters, in order')
    ap.add_argument('--no-open', action='store_true', help='do not open the image on the screen')
    a = ap.parse_args()
    global SHOW
    SHOW = not a.no_open
    work = os.path.abspath(a.work)
    brief = load(os.path.join(work, 'brief.json')) if os.path.isfile(os.path.join(work, 'brief.json')) else {}
    des = brief.get('design') or {}
    sel = provisional(work, brief, a.cover, [int(x) for x in a.photos.split(',')] if a.photos else None)
    he = sel['lang'] == 'he'
    structure = des.get('structure') or 'album'
    rows = []
    if a.gallery:
        names = style_names()
        built = build_many(work, brief, sel, [(s, 'style', structure, s) for s in names])
        for s, (imgs, rtl) in zip(names, built):
            st = load_style(s)
            rows.append((f'{st["n"]}. {st["he"] if he else st["en"]}', st['describe_he'] if he else st['describe'], imgs, rtl))
        sheet(work, 'gallery', rows, 'הסגנונות על התמונות שלך' if he else 'The styles, on your photos', covers_only=True,
              lang=sel['lang'])
    elif a.styles:
        names = a.styles.split(',')
        built = build_many(work, brief, sel, [(s, des.get('palette') if des.get('style') == s else 'style', structure, s)
                                              for s in names])
        for s, (imgs, rtl) in zip(names, built):
            st = load_style(s)
            rows.append((st['he'] if he else st['en'], st['describe_he'] if he else st['describe'], imgs, rtl))
        sheet(work, 'styles', rows, 'שער וכפולה בכל סגנון' if he else 'A cover and a spread in each style', lang=sel['lang'])
    elif a.style and a.palettes:
        pals = palettes()
        names = a.palettes.split(',')
        built = build_many(work, brief, sel, [(a.style, p, structure, f'{a.style}-{p}') for p in names])
        for p, (imgs, rtl) in zip(names, built):
            rows.append((pals[p]['he'] if he else pals[p]['en'], '', imgs, rtl))
        sheet(work, 'palettes', rows, 'אותו סגנון בפלטות שונות' if he else 'One style, several palettes', lang=sel['lang'])
    elif a.style and a.structures:
        sts = structures()
        names = load_style(a.style).get('structures', ['album', 'journal', 'magazine'])
        built = build_many(work, brief, sel, [(a.style, des.get('palette') or 'style', k, f'{a.style}-{k}') for k in names])
        for k, (imgs, rtl) in zip(names, built):
            rows.append((sts[k]['he'] if he else sts[k]['en'], sts[k]['describe_he'] if he else sts[k]['describe'], imgs, rtl))
        sheet(work, 'structures', rows, 'אותו פרק בשלושה מבנים' if he else 'One chapter in three structures', lang=sel['lang'])
    else:
        sys.exit('Give --gallery, --styles, --style with --palettes, or --style with --structures.')


if __name__ == '__main__':
    main()
