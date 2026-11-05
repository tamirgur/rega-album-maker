#!/usr/bin/env python3
"""Contact sheets: grids of numbered thumbnails, moment by moment, so the photos can be judged a sheet at a time.

    python sheets.py --work WORK                  # every day
    python sheets.py --work WORK --day 3          # one day
    python sheets.py --work WORK --ids 12,15,19   # a closer look at chosen photos (bigger cells)
    python sheets.py --work WORK --day 3 --all    # include near-duplicates, copies, blurry and dark photos

The day's cells (--per-day, 72) are shared between its moments: busy moments and key moments get more, every moment
gets at least one. Within a moment the best photo of each stretch of time is shown, and in a key moment also up to
two more frames from the same burst, so the frame can be chosen by the faces, not by sharpness alone.

Each moment starts a new row with its time, place and photo count (KEY for a key moment). Each cell shows the photo
id (#12) and marks: W = WhatsApp (date is the day received), ? = undated, V = video (with its length),
B = another frame of the burst. Writes WORK/sheets/*.jpg and prints which ids are on each sheet.
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load, parse_time, pil_font, visual  # noqa: E402
from scan import EXCLUDE  # noqa: E402

PER_SHEET = 36


def pick(items, limit):
    """At most `limit` items: the best-scoring photo in each of `limit` equal time slots."""
    if len(items) <= limit:
        return items
    t0, t1 = parse_time(items[0]['taken']), parse_time(items[-1]['taken'])
    span = max((t1 - t0).total_seconds(), 1)
    slots = {}
    for it in items:
        k = min(limit - 1, int((parse_time(it['taken']) - t0).total_seconds() / span * limit))
        if k not in slots or it.get('score', -9) > slots[k].get('score', -9):
            slots[k] = it
    return [slots[k] for k in sorted(slots)]


def share(total, weights, caps):
    """Split `total` cells by weight: at least one for each part that has something, never more than its cap."""
    out = [1 if c else 0 for c in caps]
    left = total - sum(out)
    while left > 0:
        room = [i for i, c in enumerate(caps) if out[i] < c]
        if not room:
            break
        i = max(room, key=lambda i: weights[i] / (out[i] + 1))
        out[i] += 1
        left -= 1
    return out


def blocks_for_day(d, byid, limit, show_all):
    """[(moment, items)]: what to show of each moment of a day."""
    moments = d.get('moments') or [{'id': f'{d["n"]:02d}-m1', 'ids': d['ids'], 'key': False, 'place': None,
                                    't0': byid[d['ids'][0]]['taken'], 't1': byid[d['ids'][-1]]['taken']}]
    parts = []
    for m in moments:
        its = [byid[i] for i in m['ids'] if i in byid]
        photos = [it for it in its if it['kind'] == 'photo' and (show_all or not set(it['flags']) & EXCLUDE)]
        videos = sorted((it for it in its if it['kind'] == 'video'), key=lambda v: -(v.get('duration') or 0))[:4]
        parts.append((m, its, photos, videos))
    room = max(len(moments), limit - sum(len(v) for _, _, _, v in parts))
    alloc = share(room, [math.sqrt(len(p)) * (1.6 if m.get('key') else 1) for m, _, p, _ in parts], [len(p) for _, _, p, _ in parts])
    untimed = [byid[i] for i in d.get('untimed', []) if i in byid and (show_all or not set(byid[i]['flags']) & EXCLUDE)]
    if untimed and d.get('moments'):  # WhatsApp and undated photos: their time is not when they were taken
        parts.append(({'id': 'other', 'label': 'WhatsApp or undated: not placed in time', 't0': '', 't1': ''},
                      untimed, untimed, []))
        alloc.append(min(len(untimed), 12))
    out = []
    for (m, its, photos, videos), k in zip(parts, alloc):
        chosen = pick(photos, k)
        if m.get('key') and not show_all:  # more frames of the best bursts, to choose by the faces
            shown = {it['id'] for it in chosen}
            for best in sorted(chosen, key=lambda it: -it.get('score', -9))[:3]:
                sib = [x for x in its if x.get('dup_of') == best['id'] and 'dup' in x['flags'] and x['id'] not in shown
                       and not set(x['flags']) & (EXCLUDE - {'dup'})]
                chosen += sorted(sib, key=lambda x: -x.get('score', -9))[:2]
        out.append((m, sorted(chosen + videos, key=lambda it: (it['taken'], it['id']))))
    return out


def sheet(blocks, path, title, cols, cell, names):
    from PIL import Image, ImageDraw, ImageOps
    lab, head, mrow = max(22, cell // 9), 44, 30
    ch = cell * 3 // 4 + lab
    H = head + sum((mrow if m else 0) + ((len(items) + cols - 1) // cols) * ch for m, items in blocks)
    img = Image.new('RGB', (cols * cell, H), (246, 245, 242))
    d = ImageDraw.Draw(img)
    d.text((12, 10), visual(title), fill=(40, 40, 40), font=pil_font(24, 600))
    f, fm = pil_font(int(lab * 0.8), 600), pil_font(19, 600)
    y = head
    for m, items in blocks:
        if m:
            where = names.get(m.get('place')) or ''
            txt = m.get('label') or (f'{m["id"]}  {m["t0"][11:16]}–{m["t1"][11:16]}  ·  {m.get("shots", len(items))} photos'
                                     + (f'  ·  {where}' if where else '') + ('  ·  KEY' if m.get('key') else ''))
            txt += m.get('more') or ''
            d.rectangle((0, y + 4, cols * cell, y + mrow - 2), fill=(232, 228, 220) if not m.get('key') else (226, 214, 190))
            d.text((10, y + 7), visual(txt), fill=(40, 40, 40), font=fm)
            y += mrow
        for i, it in enumerate(items):
            x, yy = (i % cols) * cell, y + (i // cols) * ch
            box = (cell - 6, cell * 3 // 4 - 6)
            if it.get('thumb') and os.path.isfile(it['thumb']):
                th = ImageOps.contain(Image.open(it['thumb']).convert('RGB'), box)
                img.paste(th, (x + 3 + (box[0] - th.width) // 2, yy + 3 + (box[1] - th.height) // 2))
            else:
                d.rectangle((x + 3, yy + 3, x + 3 + box[0], yy + 3 + box[1]), fill=(220, 216, 210))
            marks = []
            if it['kind'] == 'video':
                s = int(it.get('duration') or 0)
                marks.append(f'V {s // 60}:{s % 60:02d}')
            if 'whatsapp' in it['flags']:
                marks.append('W')
            if 'undated' in it['flags']:
                marks.append('?')
            bad = [k for k in it['flags'] if k in EXCLUDE]
            if bad == ['dup'] and it.get('dup_of'):  # a burst frame shown on purpose
                marks.append(f'B#{it["dup_of"]}')
                bad = []
            marks += bad
            d.text((x + 6, yy + cell * 3 // 4 - 2), f'#{it["id"]} ' + ' '.join(marks), font=f,
                   fill=(160, 60, 40) if bad else (30, 30, 30))
        y += ((len(items) + cols - 1) // cols) * ch
    img.save(path, quality=80)


def paginate(blocks):
    """Sheets of about PER_SHEET cells, starting a new sheet between moments where possible."""
    sheets, cur, n = [], [], 0
    for m, items in blocks:
        while items:
            if n and n + len(items) > PER_SHEET and n >= PER_SHEET // 2:
                sheets.append(cur)
                cur, n = [], 0
            take = items[:PER_SHEET - n] if n + len(items) > PER_SHEET else items
            more = len(items) - len(take)
            cur.append((dict(m, more='  (continues)' if more else '') if m else m, take))
            n += len(take)
            items = items[len(take):]
            if n >= PER_SHEET:
                sheets.append(cur)
                cur, n = [], 0
    if cur:
        sheets.append(cur)
    return sheets


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work', required=True)
    ap.add_argument('--day', type=int, action='append')
    ap.add_argument('--ids')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--per-day', type=int, default=72)
    ap.add_argument('--cols', type=int, default=6)
    ap.add_argument('--cell', type=int, default=230)
    a = ap.parse_args()

    scan = load(os.path.join(a.work, 'scan.json'))
    groups = load(os.path.join(a.work, 'groups.json'))
    byid = {r['id']: r for r in scan['items']}
    names = {p['id']: p['name'] for d in groups['days'] for p in d['places']}
    out = os.path.join(a.work, 'sheets')
    os.makedirs(out, exist_ok=True)

    if a.ids:
        ids = [int(x) for x in a.ids.replace(' ', '').split(',') if x]
        items = [byid[i] for i in ids if i in byid]
        cols = min(4, len(items)) or 1
        path = os.path.join(out, 'closer-' + '-'.join(str(i) for i in ids[:6]) + '.jpg')
        sheet([(None, items)], path, 'Closer look: ' + ', '.join(f'#{i}' for i in ids), cols, 420, names)
        print(path)
        return

    for d in groups['days']:
        if a.day and d['n'] not in a.day:
            continue
        pages = paginate(blocks_for_day(d, byid, a.per_day, a.all))
        for k, blocks in enumerate(pages, 1):
            path = os.path.join(out, f'day{d["n"]:02d}-{k}.jpg')
            sheet(blocks, path, f'Day {d["n"]} · {d["key"]} · sheet {k}/{len(pages)} · {len(d["ids"])} files, '
                                f'choose about {d["quota"]}', a.cols, a.cell, names)
            print(f'{path}  ids: {", ".join(str(it["id"]) for _, items in blocks for it in items)}')


if __name__ == '__main__':
    main()
