#!/usr/bin/env python3
"""Where a book stands: the ten stages, what is done, what is missing, and the line to show the user.

    python brief.py --work WORK                      # the checklist, the next step and the user's status line
    python brief.py --init FOLDER ... --albums PLACE --name "BOOK" [--lang he]
                                                     # start a book in PLACE/אלבומים/BOOK/ (Albums/ in English):
                                                     # the finished files go there, the work in its "קבצי עבודה"
    python brief.py --work WORK --options            # page count options for the scanned photos

WORK/brief.json holds the user's answers, one section per stage (see references/book-json.md). The scripts read
it: group.py takes the page count and the structure for the quotas, layout.py the size, the page count, the look
and the elements, printer.py the printer.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ALBUMS, OFFERED, SIZES, WORK, base_quota, even_up, load, pages_for, photos_for, save, shape_ok  # noqa: E402
from looks import palettes, per_page, structures, style_names  # noqa: E402

ELEMENTS = ['route_map', 'illustrations', 'badges', 'callouts', 'qr', 'day_maps']
STAGES = {   # (English, Hebrew)
    1: ('Start', 'התחלה'), 2: ('Scan', 'סריקה'), 3: ('The story', 'הסיפור'), 4: ('Print and size', 'הדפסה וגודל'),
    5: ('Design', 'עיצוב'), 6: ('Confirm', 'אישור'), 7: ('Build', 'בנייה'), 8: ('Review', 'סקירה'),
    9: ('Print files', 'קבצים להדפסה'), 10: ('Sort the photos (optional)', 'סידור התמונות (רשות)')}
TEMPLATE = {
    'folders': [],
    'scope': None,      # {"from": "2024-07-10", "to": "2024-07-12", "days": null, "places": null, "topic": null}
    'story': None,      # {"moments": ["..."], "people": [{"name": "...", "looks": "..."}], "best": null}
    'book': {'title': None, 'lang': None, 'kind': None, 'chapters': 'day'},
    'print': None,      # {"printer": "prodigi", "sku": "...", ...} from printer.py --choose, or {"printer": "other"}
    'format': None,     # {"size": "square-21", "pages": 36}
    'design': None,     # {"structure": "album", "style": "nordic", "palette": "style", "elements": {...}, "logo": null}
    'confirmed': False,
    'approved': False,  # the user approved the preview
}


def mtime(path):
    return os.path.getmtime(path) if os.path.isfile(path) else None


def options(work, brief):
    groups = load(os.path.join(work, 'groups.json'))
    fm = brief.get('format') or {}
    size = fm.get('size') or 'square-21'
    minp = fm.get('min_pages') or SIZES.get(size, SIZES['square-21'])[2]
    maxp = fm.get('max_pages')
    els = (brief.get('design') or {}).get('elements') or {}
    route = groups.get('has_gps') and els.get('route_map', True)
    days = [d for d in groups['days'] if d['candidates']]
    chapters, cands = len(days), sum(d['candidates'] for d in days)
    pp = per_page(brief)
    std = even_up(max(minp, pages_for(sum(base_quota(d['candidates']) for d in days), chapters, route, pp)))
    picks = sorted({even_up(max(minp, round(std * 0.7))), std, even_up(round(std * 1.4))})
    if maxp:
        picks = sorted({min(p, maxp - maxp % 2) for p in picks})
    print(f'{chapters} days, {cands:,} good photos (after duplicates, blur and the like). Size {size}, printer minimum '
          f'{minp} inside pages' + (f', maximum {maxp}' if maxp else '') + '.')
    print('Page count options (inside pages, without the covers):')
    for p in picks:
        n = photos_for(p, chapters, route, pp)
        name = 'compact' if p < std else 'standard (recommended)' if p == std else 'rich'
        warn = f'  - only {cands} good photos: some pages would hold one photo' if n > cands else ''
        print(f'  {p:3d} pages  ~{n} photos  (~{n / max(chapters, 1):.0f} a day)  {name}{warn}')
    pr = brief.get('print') or {}
    if pr.get('printer') == 'prodigi':
        print(f'Prodigi {pr["sku"]}: from ${pr["base_usd"]:.2f} a copy, before extra pages and shipping; the order '
              'summary on their site shows the exact price.')
    print('Write the chosen count in brief.json ("format": {"pages": N}), then run group.py again for the quotas.')


def status(work, brief):
    rows, nxt = [], None
    lang = (brief.get('book') or {}).get('lang') or 'en'

    def row(n, ok, note):
        nonlocal nxt
        rows.append(f'[{"x" if ok else " "}] {n}. {STAGES[n][0]}: {note}')
        if not ok and nxt is None and n < 10:
            nxt = n

    folders = brief.get('folders') or []
    missing = [f for f in folders if not os.path.isdir(f)]
    row(1, folders and not missing,
        f'{len(folders)} folder(s)' if folders and not missing else 'not found: ' + ', '.join(missing) if missing else 'no photo folders yet')

    scan_p = os.path.join(work, 'scan.json')
    if os.path.isfile(scan_p):
        scan = load(scan_p)
        same = {os.path.abspath(f) for f in scan.get('folders', [])} == {os.path.abspath(f) for f in folders}
        n = sum(r['in_range'] for r in scan['items'])
        scope = brief.get('scope') or {}
        redo = [f'--from {scope["from"]}'] if scope.get('from') and scope['from'] != scan.get('from') else []
        redo += [f'--to {scope["to"]}'] if scope.get('to') and scope['to'] != scan.get('to') else []
        groups_ok = (mtime(os.path.join(work, 'groups.json')) or 0) >= mtime(scan_p)
        ok = same and not redo and groups_ok
        note = f'{n:,} files in range' if ok else 'the folders changed: scan again' if not same else \
            f'scan again with {" ".join(redo)}' if redo else 'run group.py'
        row(2, ok, note)
    else:
        row(2, False, 'not scanned yet')

    bk = brief.get('book') or {}
    lack = [k for k in ('scope', 'story') if brief.get(k) is None] + ([] if bk.get('kind') else ['book.kind'])
    row(3, not lack, 'answered' if not lack else 'missing ' + ', '.join(lack))

    fm, pr = brief.get('format') or {}, brief.get('print')
    size, pages = fm.get('size'), fm.get('pages')
    bad = [] if pr else ['where it will be printed ("print": printer.py --choose, or {"printer": "other"})']
    if fm.get('w') and fm.get('h'):
        if not shape_ok(fm['w'], fm['h']):
            bad.append('landscape pages are not offered: choose a square or portrait size')
    elif size not in OFFERED:
        bad.append(f'size must be one of {", ".join(OFFERED)}, or a printer\'s size from printer.py --choose')
    if not isinstance(pages, int) or pages < 2 or pages % 2:
        bad.append('pages must be an even number (python brief.py --options)')
    elif fm.get('min_pages') and not fm['min_pages'] <= pages <= (fm.get('max_pages') or 10 ** 6):
        bad.append(f'pages must be {fm["min_pages"]}-{fm.get("max_pages")} for this product')
    if not bk.get('lang') or not bk.get('title'):
        bad.append('the language and the title (book.lang, book.title)')
    row(4, not bad, f'{(pr or {}).get("sku") or size}, {pages} pages' if not bad else '; '.join(bad))

    de = brief.get('design') or {}
    style = de.get('style') or de.get('concept')
    bad = []
    if not de:
        bad.append('not chosen')
    else:
        if de.get('structure', 'album') not in structures():
            bad.append(f'structure must be one of {", ".join(structures())}')
        elif style in style_names():
            from looks import load_style
            ok = load_style(style).get('structures', list(structures()))
            if de.get('structure', 'album') not in ok:
                bad.append(f'{style} works with {" or ".join(ok)}, not {de.get("structure")}: a magazine needs a style '
                           'whose photos run to the edge (minimal, colourful, bold, newspaper, swiss)')
        if style not in style_names() and not (style and os.path.isfile(os.path.join(work, style))):
            bad.append(f'style must be one of {", ".join(style_names())}')
        pal = de.get('palette', 'style')
        if not (isinstance(pal, dict) or pal in ('style', 'concept', 'warm', 'cool', *palettes())):
            bad.append(f'palette must be "style", {", ".join(palettes())}, or brand colours {{"accent": "#..."}}')
        bad += [f'unknown element "{k}"' for k in (de.get('elements') or {}) if k not in ELEMENTS]
        if de.get('logo') and not os.path.isfile(de['logo']):
            bad.append(f'logo not found: {de["logo"]}')
    row(5, not bad, f'{de.get("structure", "album")} · {style} · palette {de.get("palette", "style")}' if not bad else '; '.join(bad))

    row(6, brief.get('confirmed') is True, 'yes' if brief.get('confirmed') is True else 'not yet')

    sel, book, pdf, chk = (os.path.join(work, f) for f in ('selection.json', 'book.json', 'book.pdf', 'check.md'))
    if not os.path.isfile(sel):
        row(7, False, 'no selection.json yet')
    elif (mtime(book) or 0) < mtime(sel):
        row(7, False, 'selection changed: run layout.py')
    elif (mtime(pdf) or 0) < mtime(book):
        row(7, False, 'book.json changed: run render.py')
    elif (mtime(chk) or 0) < mtime(pdf):
        row(7, False, 'run check.py')
    else:
        with open(chk, encoding='utf-8') as f:
            ready = 'Ready for the printer' in f.read()
        row(7, ready, 'checked, ready' if ready else 'check.md lists problems')
    row(8, brief.get('approved') is True, 'the user approved the preview' if brief.get('approved') is True else 'waiting for the user')
    if (pr or {}).get('printer') == 'prodigi':
        folder = os.path.join(work, 'להדפסה' if lang == 'he' else 'to-print')
        done = os.path.isdir(folder) and (mtime(pdf) or 0) <= max((mtime(os.path.join(folder, f)) or 0) for f in os.listdir(folder)) \
            if os.path.isdir(folder) and os.listdir(folder) else False
        row(9, done, 'the print folder is ready' if done else 'run printer.py --pack')
    else:
        row(9, False, 'give the PDF and the print notes for their printer')
    rows.append(f'[ ] 10. {STAGES[10][0]}: offer it at the end')

    title = bk.get('title')
    print(f'Book{": " + title if title else ""} (work folder {work})')
    print('\n'.join(rows))
    if nxt:
        name = STAGES[nxt][1] if lang == 'he' else STAGES[nxt][0]
        line = f'שלב {nxt} מתוך 10 · {name}' if lang == 'he' else f'Stage {nxt} of 10 · {name}'
        print(f'Next: stage {nxt}, {STAGES[nxt][0]}. See SKILL.md' + (' and references/questions.md.' if 3 <= nxt <= 5 else '.'))
        print(f'Status line for the user: {line}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work', help='the work folder (made by --init with --albums)')
    ap.add_argument('--albums', metavar='PLACE', help='with --init: the place the user chose for the albums folder')
    ap.add_argument('--name', help='with --albums: the book\'s folder name, e.g. "Florence 2026"')
    ap.add_argument('--lang', default='en', help='with --albums: the folder names\' language (he: אלבומים, else Albums)')
    ap.add_argument('--init', nargs='+', metavar='FOLDER')
    ap.add_argument('--options', action='store_true')
    a = ap.parse_args()
    if a.init and a.albums:
        if not a.name:
            sys.exit('--albums needs --name, the book\'s folder name')
        lang = 'he' if a.lang.startswith('he') else 'en'
        place = os.path.abspath(a.albums)
        if not os.path.isdir(place):
            sys.exit(f'Not a folder: {place}')
        safe = ''.join(ch for ch in a.name if ch not in '\\/:*?"<>|').strip() or 'Book'
        book, k = os.path.join(place, ALBUMS[lang], safe), 2
        while os.path.exists(os.path.join(book, WORK[lang], 'brief.json')):   # a book of that name exists: never touch it
            book, k = os.path.join(place, ALBUMS[lang], f'{safe} ({k})'), k + 1
        a.work = os.path.join(book, WORK[lang])
        os.makedirs(a.work, exist_ok=True)
        print(f'Book folder: {book}  (finished files here; the work in "{WORK[lang]}")')
    if not a.work:
        sys.exit('Give --work, or --init with --albums and --name')
    work = os.path.abspath(a.work)
    path = os.path.join(work, 'brief.json')
    if a.init:
        if os.path.isfile(path):
            sys.exit(f'{path} exists already. Edit it instead.')
        save(path, dict(TEMPLATE, folders=[os.path.abspath(f) for f in a.init]))
        print(f'Started {path}')
    brief = load(path) if os.path.isfile(path) else {}
    if not brief:
        print(f'No brief yet. Start one: python brief.py --work "{work}" --init "<photo folder>" ...')
        return
    if a.options:
        if not os.path.isfile(os.path.join(work, 'groups.json')):
            sys.exit('Run scan.py and group.py first.')
        options(work, brief)
        return
    status(work, brief)


if __name__ == '__main__':
    main()
