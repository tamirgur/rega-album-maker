#!/usr/bin/env python3
"""Turn WORK/selection.json into WORK/book.json: every page with its frames, texts and items, in mm.

    python layout.py --work WORK [--size square-21 | --w 200 --h 200] [--pages 24]
                     [--style nordic] [--palette sand] [--structure album] [--pad]

The selection gives the chapters (a title, the photos in order, highlights, quiet moments, details), the cover and
the closing photo. The brief's "design" gives the look in three levels: the structure (album, journal, magazine),
the style (15, in assets/styles) and the palette. The planner (design.py) chooses a template for every page: an
opener across a spread, band, side, fill, hero, quiet or jewel. A printer chosen with printer.py sets the exact size
and the part of the fold the binding hides.

The book:
  page 1        the route map (a trip with GPS) or a title page with a small photo
  pages 2 ...   the chapters, each starting on the right page of a spread (the left one in an English book)
  last page     the closing photo
The page count is the one in brief.json (or --pages). The rules are checked and saved in book.json ("rules"):
the script prints what passed and what needs another choice.
"""
import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D  # noqa: E402
from common import SIZES, even_up, fmt_date, fmt_long, fmt_range, is_rtl, load, save, words  # noqa: E402
from scan import EXCLUDE  # noqa: E402


def chapters_from(sel, groups, scan_by_id, lang, deck_style='dots'):
    """The chapters, from "chapters" or from the older "days"; each gets a small deck: weekday · date · place."""
    t = words(lang)
    days_by_n = {d['n']: d for d in groups['days']}
    days_by_key = {d['key']: d for d in groups['days']}
    day_of = {i: d for d in groups['days'] for i in d['ids']}
    place_of = {i: p.get('name') for d in groups['days'] for p in d['places'] for i in p.get('ids', [])}
    out = []
    for c in sel.get('chapters') or sel.get('days') or []:
        c = dict(c)
        gs = []
        if c.get('days'):
            gs = [days_by_n[n] for n in c['days'] if n in days_by_n]
        elif c.get('range'):
            gs = [d for d in groups['days'] if c['range'][0] <= d['key'] <= c['range'][1]]
        elif c.get('day') or c.get('key'):
            gs = [x for x in [days_by_n.get(c.get('day')) or days_by_key.get(c.get('key'))] if x]
        elif c.get('photos'):
            gs = [x for x in [day_of.get(c['photos'][0])] if x]
        if not c.get('deck'):
            c['deck'] = c.get('tag')
        if not c.get('deck') and gs:
            d0, d1 = date.fromisoformat(gs[0]['key']), date.fromisoformat(gs[-1]['key'])
            named = [place_of[i] for i in c.get('photos', []) if place_of.get(i)]   # where most of its photos are
            place = max(set(named), key=named.count) if named else \
                next((p['name'] for g in gs for p in g['places'] if p.get('name')), None)
            if deck_style == 'sentence':   # written as in a sentence, not a string of fields
                c['deck'] = ', '.join(x for x in [fmt_long(d0, lang) if len(gs) == 1 else fmt_range(d0, d1, lang), place] if x)
            else:
                parts = ([t['weekdays'][d0.weekday()]] if t.get('weekdays') else []) + [fmt_date(d0, lang, not t.get('weekdays'))] \
                    if len(gs) == 1 else [fmt_range(d0, d1, lang)]
                c['deck'] = ' · '.join(x for x in parts + [place] if x)
        out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work', required=True)
    ap.add_argument('--size', choices=sorted(SIZES))
    ap.add_argument('--w', type=float)
    ap.add_argument('--h', type=float)
    ap.add_argument('--pages', type=int, help='inside pages wanted (else the one in brief.json)')
    ap.add_argument('--min-pages', type=int)
    ap.add_argument('--style', '--concept', dest='style', help=f'one of: {", ".join(D.concepts())} (else the one in brief.json)')
    ap.add_argument('--palette', help='a palette name from assets/palettes.json (else the one in brief.json)')
    ap.add_argument('--structure', choices=['album', 'journal', 'magazine'], help='else the one in brief.json')
    ap.add_argument('--pad', action='store_true', help='add quiet pages when the photos cannot fill the pages')
    a = ap.parse_args()

    work = a.work
    sel = load(os.path.join(work, 'selection.json'))
    scan = load(os.path.join(work, 'scan.json'))
    groups = load(os.path.join(work, 'groups.json'))
    bpath = os.path.join(work, 'brief.json')
    brief = load(bpath) if os.path.isfile(bpath) else {}
    fmt, des = brief.get('format') or {}, brief.get('design') or {}
    els = des.get('elements') or {}
    byid = {r['id']: r for r in scan['items']}
    lang = sel.get('lang') or (brief.get('book') or {}).get('lang') or groups.get('lang') or 'en'
    t = words(lang)
    problems = []
    if t.get('generic'):
        problems.append(f'"{lang}" is not built in (only he and en): give each chapter a "deck" and the route page a '
                        '"route_title" in that language in selection.json; dates are written as numbers')
    size = a.size or sel.get('size') or fmt.get('size') or 'square-21'
    W, H, minp = SIZES.get(size, SIZES['square-21'])
    if fmt.get('w') and fmt.get('h') and not a.size:   # a printer's exact size (printer.py --choose)
        W, H, size = fmt['w'], fmt['h'], fmt.get('size') or 'custom'
        minp = fmt.get('min_pages') or minp
    if a.w and a.h:
        W, H, size = a.w, a.h, 'custom'
    if a.min_pages is not None:
        minp = a.min_pages
    goal = even_up(a.pages or fmt.get('pages') or 0) or None
    no_people = set(sel.get('no_people', []))
    moment_of = {i: m['id'] for d in groups['days'] for m in d.get('moments', []) for i in m['ids']}

    concept_name = a.style or des.get('style') or des.get('concept') or 'minimal'
    if not os.path.isfile(concept_name) and os.path.isfile(os.path.join(work, concept_name)):
        concept_name = os.path.join(work, concept_name)   # the book's own style file, in the work folder
    try:
        deck_style = D.concept(concept_name).get('deck', 'dots')
    except ValueError as e:
        sys.exit(str(e))
    structure = a.structure or des.get('structure') or 'album'
    pr = brief.get('print') or {}
    gutter = float(pr.get('gutter_mm') or 0)
    chapters = chapters_from(sel, groups, byid, lang, deck_style)
    cover_id = sel.get('cover')
    closing = sel.get('closing')
    closing_id = closing.get('photo') if isinstance(closing, dict) else closing
    if closing_id is None and chapters and chapters[-1].get('photos'):   # no closing photo: the story's last one
        closing_id = chapters[-1]['photos'][-1]
        chapters[-1]['photos'] = chapters[-1]['photos'][:-1]
    ids = {i for c in chapters for i in c.get('photos', [])} | {x for x in (cover_id, closing_id) if x}
    photos = {}
    for i in sorted(ids):
        r = byid.get(i)
        if not r or r['kind'] != 'photo' or 'error' in r['flags']:
            problems.append(f'#{i} is not a readable photo in scan.json')
            continue
        bad = set(r['flags']) & EXCLUDE
        if bad:
            problems.append(f'#{i} is marked {", ".join(sorted(bad))}; keep it only on purpose')
        if 'whatsapp' in r['flags']:
            problems.append(f'#{i} is a WhatsApp photo: its date is the day it was received. Use it only if the user '
                            'confirmed it belongs here')
        if 'undated' in r['flags']:
            problems.append(f'#{i} has no date of its own (file time only). Use it only if you know where it belongs')
        photos[i] = D.Photo(r, no_people)
    for c in chapters:
        c['photos'] = [i for i in c.get('photos', []) if i in photos]
    seen = {}
    for c in chapters:
        for i in c['photos']:
            seen[i] = seen.get(i, 0) + 1
    for i, k in seen.items():
        if k > 1:
            problems.append(f'#{i} is in more than one chapter')

    palette = a.palette or des.get('palette') or 'style'
    style = D.concept(concept_name, palette, [photos[i].thumb for i in photos if photos[i].thumb], structure)
    d = D.Designer(W, H, style, lang, gutter)
    if style.get('structure_note'):
        problems.append(style['structure_note'])
    structure = style['structure']

    # ---- the plan: chapters share the pages between page 1 and the last page, each starting on a spread
    plans = [D.plan_chapter(d, c, photos, moment_of, True) for c in chapters]
    natural = [even_up(max(2, D.count(p))) for p in plans]
    budgets = list(natural)
    if goal:
        room = goal - 2

        def most(i):  # the most pages a chapter can take: one photo a page
            return even_up(len(chapters[i]['photos']) + 1)
        while sum(budgets) < room and any(budgets[i] < most(i) for i in range(len(budgets))):
            i = max((i for i in range(len(budgets)) if budgets[i] < most(i)),
                    key=lambda i: len(chapters[i]['photos']) / budgets[i])
            budgets[i] += 2
        while sum(budgets) > room and any(b > 2 for b in budgets):
            i = min((i for i in range(len(budgets)) if budgets[i] > 2), key=lambda i: len(chapters[i]['photos']) / budgets[i])
            budgets[i] -= 2
    # each chapter's plan, fitted to its budget; then the pages are balanced across the book: a chapter that cannot
    # fill its share gives it to one that can, and every chapter keeps an even count so the next starts on a spread
    specs_all = []
    for c, b in zip(chapters, budgets):
        sp = D.plan_chapter(d, c, photos, moment_of, True)
        D.fit(sp, b)
        specs_all.append(sp)

    def grow(sp):
        return any(x['tpl'] == 'fill' and len(x['photos']) > 1 for x in sp)

    def shrink(sp):
        return any(a_['tpl'] == b_['tpl'] == 'fill' and len(a_['photos']) + len(b_['photos']) <= 4
                   for a_, b_ in zip(sp, sp[1:]))
    room = (goal - 2) if goal else None

    def spread_at(j):
        return bool(specs_all[j]) and specs_all[j][0]['tpl'] == 'opener-spread'

    def step(i, k):   # one page more (k=1) or fewer (k=-1) for chapter i, if its photos allow
        sp = specs_all[i]
        if (k > 0 and not grow(sp)) or (k < 0 and not shrink(sp)):
            return False
        D.fit(sp, D.count(sp) + k)
        return True
    for _ in range(300):
        counts = [D.count(sp) for sp in specs_all]
        total = sum(counts)
        if room is not None and total != room:   # 1. the exact count: the chapter with most photos per page grows first
            k = 1 if total < room else -1
            order = sorted(range(len(specs_all)), key=lambda i: -k * sum(len(x['photos']) for x in specs_all[i]) / max(counts[i], 1))
            if not any(step(i, k) for i in order):
                break
            continue
        # 2. a chapter that opens across a spread must start on a spread: an even number of pages before it
        bad = next((j for j in range(len(specs_all)) if spread_at(j) and sum(counts[:j]) % 2), None)
        if bad is None:
            break
        moved = False
        for before, after in ((1, -1), (-1, 1)):   # one page more before it and one fewer from it on, or the reverse
            for i in reversed(range(bad)):
                if step(i, before):
                    if any(step(j, after) for j in range(bad, len(specs_all))):
                        moved = True
                        break
                    step(i, -before)
            if moved:
                break
        if not moved:
            break   # it cannot: the chapter will open on a single page
    for specs in specs_all:
        D.tidy(d, specs)
    for a_, b_ in zip(specs_all, specs_all[1:]):
        if a_ and b_ and a_[-1]['tpl'] == b_[0]['tpl'] and a_[-1]['tpl'] in ('band', 'side', 'hero', 'quiet', 'jewel') \
                and not a_[-1].get('title'):
            a_[-1] = dict(a_[-1], tpl='fill')
    inner, n = [], 2
    tints = style.get('tints_list') or []
    ills = els.get('illustrations', True) and style.get('illustrations', True)
    multi_day = len({byid[i]['day'] for i in photos if byid[i].get('day')}) > 1
    kind = (brief.get('book') or {}).get('kind') or 'trip'
    for k, (c, specs) in enumerate(zip(chapters, specs_all)):
        t_ = c.get('tint') if tints else None   # a chapter's own tint, or the style's, in turn
        d.bg = D.TINTS.get(t_, t_) if t_ else (tints[k % len(tints)] if tints else None)
        if c.get('illustration') and ills:
            for sp in specs:
                if sp.get('head'):
                    sp['illustration'] = c['illustration']
        start = len(inner)
        for sp in specs:
            for pg in D.draw(d, sp, n):
                pg['n'] = n
                inner.append(pg)
                n += 1
        mine = inner[start:]
        first = next((p for p in mine if p.get('opens')), None)
        if first is not None:
            d.decorate(first, c.get('illustration') if ills else None)
            if style.get('badges') and els.get('badges', True) and multi_day and kind == 'trip':   # a journal: the day of the trip
                day = next((byid[i]['day'] for i in c.get('photos', []) if byid[i].get('day')), None)
                days = sorted({byid[i]['day'] for i in photos if byid[i].get('day')})
                if day in days:
                    d.badge(first, t['day'], days.index(day) + 1)
        for pg in mine:
            if pg is not first and pg['tpl'] in ('quiet',) and 'arch' in (style.get('ornaments') or []):
                d.ornament(pg)
        co = c.get('callout')
        if co and els.get('callouts', True):
            placed = any(d.callout(pg, co['photo'], co.get('at') or [0.5, 0.5], co.get('text'), co.get('ill'))
                         for pg in mine if any(f['id'] == co['photo'] for f in pg['frames']))
            if not placed:
                problems.append(f'the callout on #{co["photo"]} found no free space on its page: leave it out or '
                                'give that photo a page with more air')

    d.bg = None
    # ---- page 1: the route of a trip, or a title page; the last page: the closing photo
    title, subtitle = sel.get('title', ''), sel.get('subtitle')
    if subtitle is None:
        days = sorted({byid[i]['day'] for i in photos if byid[i].get('day')})
        subtitle = fmt_range(date.fromisoformat(days[0]), date.fromisoformat(days[-1]), lang) if days else ''
    tracks = {str(x['n']): x['track'] for x in groups['days'] if x['track']}
    journey = sel.get('journey') if els.get('route_map', True) else None
    if journey:   # the journey as the user told it (stops and how they travelled), not the photos' GPS
        from maps import journey_parts
        stops_, legs_, jp = journey_parts(journey)
        problems += jp
        if len(stops_) < 2:
            journey = None
    first = d.page('route' if journey or (groups.get('has_gps') and els.get('route_map', True) and len(tracks) > 1)
                   else 'title', d.side(1))
    x0, y0, bw, bh = d.area(first['side'])
    if first['tpl'] == 'route':
        from maps import main_region
        allp = [p for x in groups['days'] for p in x['places']]
        keep = main_region([(p['lat'], p['lon']) for p in allp])
        names = {(p.get('name') or f'{p["lat"]:.2f},{p["lon"]:.2f}').casefold() for p, k in zip(allp, keep) if k}
        nplaces = len([s for s in stops_ if not s['home']]) if journey else len(names)
        stats = ' · '.join([t['days'].format(n=len(groups['days'])) if len(groups['days']) > 1 else t['one_day'],
                            t['places'].format(n=nplaces) if nplaces > 1 else t['one_place']])
        d.text(first, 'h2', sel.get('route_title', t['route']), x0, y0, bw)
        d.text(first, 'label', stats, x0, y0 + 10 * d.s, bw)
        ph_ = 26 * d.s if sel.get('pass') and not journey else 0   # the journey's legend tells what a pass would
        first['items'].append({'type': 'route', 'x': x0, 'y': y0 + 20 * d.s, 'w': bw, 'h': bh - 20 * d.s - (ph_ + 4 * d.s if ph_ else 0),
                               'places': [{'lat': p['lat'], 'lon': p['lon'], 'name': p.get('name')}
                                          for x in groups['days'] for p in sorted(x['places'], key=lambda p: -p['count'])]})
        if journey:
            first['items'][-1].update(journey=journey, words=dict(t.get('modes') or words('en')['modes'],
                                                                  **(sel.get('journey_words') or {})))
        if ph_:
            first['items'].append({'type': 'pass', 'x': x0, 'y': y0 + bh - ph_, 'w': bw, 'h': ph_, 'pass': sel['pass']})
    else:
        if cover_id in photos:
            p = photos[cover_id]
            w = min(bw * 0.5, bh * 0.45 * p.a)
            d.frame(first, p, [x0 + (bw - w) / 2, y0 + bh * 0.16, w, w / p.a])
            y = y0 + bh * 0.16 + w / p.a + 10 * d.s
        else:
            y = y0 + bh * 0.4
        d.text(first, 'h1', title, x0, y, bw, 'center')
        d.text(first, 'label', subtitle, x0, y + 14 * d.s, bw, 'center')
    first['n'] = 1
    pages_in = [first] + inner
    want = goal or minp
    if want and len(pages_in) + 1 < want and a.pad:
        while len(pages_in) + 1 < want:
            pg = d.page('blank', d.side(len(pages_in) + 1))
            pg['n'] = len(pages_in) + 1
            pages_in.append(pg)
    last_n = len(pages_in) + 1
    if last_n % 2:   # the closing page must end the book on an even page
        pg = d.page('blank', d.side(last_n))
        pg['n'] = last_n
        pages_in.append(pg)
        last_n += 1
    last = d.quiet(d.side(last_n), photos[closing_id], (closing.get('title') if isinstance(closing, dict) else None)) \
        if closing_id in photos else d.page('quiet', d.side(last_n))
    last['n'], last['tpl'] = last_n, 'closing'
    pages_in.append(last)
    for pg in pages_in:
        if pg['tpl'] in ('fill', 'side', 'band', 'quiet', 'jewel', 'title', 'route', 'closing') and pg.get('n'):
            d.folio(pg, pg['n'])

    # ---- covers: the style's own cover; a mosaic or a newspaper cover also takes a few of the chapters' best photos
    more = [photos[i] for c in chapters for i in (c.get('highlights') or [])[:1] + c.get('photos', [])[:1] if i in photos]
    more = [p for k_, p in enumerate(more) if p not in more[:k_]]
    cover = d.cover(photos.get(cover_id), title, subtitle, more)
    back = d.page('back', 'l' if d.rtl else 'r', style['colors']['endpaper'])
    d.text(back, 'h2', title, 16 * d.s, H * 0.44, W - 32 * d.s, 'center', style['colors']['paper'])
    d.text(back, 'label', subtitle, 16 * d.s, H * 0.44 + 11 * d.s, W - 32 * d.s, 'center', style['colors']['paper'])
    logo = des.get('logo')
    if logo and os.path.isfile(logo):
        for pg, y in ((back, H - 34 * d.s), (first, H - d.mt - 16 * d.s)):
            pg['items'].append({'type': 'logo', 'path': os.path.abspath(logo), 'x': W / 2 - 12 * d.s, 'y': y, 'w': 24 * d.s, 'h': 14 * d.s})
    elif logo:
        problems.append(f'the logo {logo} was not found')
    pages = [cover] + pages_in + [back]

    rules = D.check(d, pages, photos, goal, chapters)
    book = {'title': title, 'lang': lang, 'dir': 'rtl' if is_rtl(lang) else 'ltr', 'size': size, 'w': W, 'h': H,
            'u': d.s, 'min_pages': minp, 'goal_pages': goal, 'concept': concept_name, 'structure': structure,
            'palette': style.get('palette_name'), 'gutter': gutter,
            'style': {k: style.get(k) for k in ('name', 'type', 'colors', 'grade', 'fonts', 'display_classes',
                                               'text_classes', 'texture', 'keyline', 'title_color', 'label_color',
                                               'label_spacing', 'frame')},
            'pages': pages, 'tracks': tracks,
            'photos': {str(i): {'src': p.src, 'w': p.w, 'h': p.h} for i, p in photos.items()},
            'rules': [{'rule': r, 'ok': bool(ok), 'note': note} for r, ok, note in rules]}
    save(os.path.join(work, 'book.json'), book)

    nin = len(pages_in)
    used = {f['id'] for p in pages for f in p['frames']}
    print(f'Book: {nin} inside pages + front and back cover · {size} ({W:g} x {H:g} mm) · {structure} · '
          f'style {os.path.basename(concept_name)} · palette {style.get("palette_name")} · '
          f'{lang}, {"right to left, opens from the right" if is_rtl(lang) else "opens from the left"} · {len(used)} photos.')
    tpls = {}
    for p in pages_in:
        tpls[p['tpl']] = tpls.get(p['tpl'], 0) + 1
    print('Pages: ' + ', '.join(f'{k} {v}' for k, v in sorted(tpls.items(), key=lambda kv: -kv[1])))
    if goal and nin > goal:
        print(f'Over: {nin} inside pages, {goal} planned. Leave out about {2 * (nin - goal)} photos.')
    elif goal and nin < goal:
        print(f'Short: {nin} inside pages, {goal} planned. Choose about {2 * (goal - nin)} more photos, '
              'or run again with --pad for quiet pages.')
    elif not goal and nin < minp:
        print(f'Short: the printer minimum is {minp} inside pages. Choose more photos, or agree on a page count.')
    blanks = sum(p['tpl'] == 'blank' for p in pages_in)
    if blanks:
        print(f'{blanks} blank page(s) added.' + (' That is many: choose more photos or agree on fewer pages.' if blanks > 2 else ''))
    for r in book['rules']:
        print(f'{"ok  " if r["ok"] else "RULE"}  {r["rule"]}' + (f'  ({r["note"]})' if r['note'] else ''))
    low = sorted({(int(photos[f['id']].w / (f['img'][2] / 25.4)), f['id']) for p in pages for f in p['frames']
                  if photos[f['id']].w / (f['img'][2] / 25.4) < 200})
    for dpi, i in low:
        print(f'Low resolution: #{i} prints at {dpi} DPI ' + ('(too low: a smaller frame or another photo)' if dpi < 150 else '(acceptable, 300 is best)'))
    for msg in dict.fromkeys(problems):
        print('Check: ' + msg)
    print(f'Next: python render.py --work "{work}"')


if __name__ == '__main__':
    main()
