#!/usr/bin/env python3
"""Group the scanned photos into days, places and moments.

    python group.py --work WORK [--geocode] [--lang he|en] [--place-km 2.5]

A day runs from 04:00 to 04:00. Places are GPS clusters (a new place starts more than --place-km away
from every place of that day); photos without GPS join the place of the nearest photo in time (within an
hour). --geocode names each place through OpenStreetMap (online, about one second per place); the names
are a starting point that the user can correct in groups.json.

Moments: each day is cut where the photographer paused for long, or moved to another place. What counts as a
long pause depends on how this person shoots: a pause of 8 minutes splits a moment only when it is much longer
than the pauses around it, and any pause of 45 minutes does. A stretch of more than two hours without such a
pause is cut at its longest break. A moment is "key" when far more photos were taken in it than in a typical
moment of this collection, or when it holds a video: people photograph a lot when something matters.

The number of photos to choose per day ("quota") follows the page count in WORK/brief.json when it is set.

Writes WORK/groups.json.
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import km, load, median, parse_time, photos_for, quotas, save, words  # noqa: E402
from looks import per_page  # noqa: E402
from scan import EXCLUDE  # noqa: E402

UNTIMED = {'whatsapp', 'undated', 'copy'}  # their time is not when they were taken: kept out of the moments


def cluster(items, km_max):
    places = []
    for it in items:
        if it.get('lat') is None:
            continue
        pt = (it['lat'], it['lon'])
        near = min(places, key=lambda p: km(p['c'], pt), default=None)
        if near and km(near['c'], pt) <= km_max:
            n = len(near['ids'])
            near['c'] = ((near['c'][0] * n + pt[0]) / (n + 1), (near['c'][1] * n + pt[1]) / (n + 1))
            near['ids'].append(it['id'])
            near['t1'] = it['taken']
        else:
            places.append({'c': pt, 'ids': [it['id']], 't0': it['taken'], 't1': it['taken']})
    gps = [it for it in items if it.get('lat') is not None]
    loose = []
    for it in items:
        if it.get('lat') is not None:
            continue
        t = parse_time(it['taken'])
        best = min(gps, key=lambda g: abs((parse_time(g['taken']) - t).total_seconds()), default=None)
        if best and abs((parse_time(best['taken']) - t).total_seconds()) <= 3600:
            next(p for p in places if best['id'] in p['ids'])['ids'].append(it['id'])
        else:
            loose.append(it['id'])
    places.sort(key=lambda p: p['t0'])
    return places, loose


def track(items):
    """The day's path: GPS points in time order, thinned to one point every 300 m."""
    out = []
    for it in items:
        if it.get('lat') is None:
            continue
        p = (round(it['lat'], 5), round(it['lon'], 5))
        if not out or km(out[-1], p) >= 0.3:
            out.append(p)
    return [list(p) for p in out]


def cut_moments(its, place_of):
    """(start, end) index pairs: a new moment after a long pause, or when the place changes."""
    ts = [parse_time(r['taken']) for r in its]
    gaps = [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
    cuts = []
    for i, g in enumerate(gaps):
        local = median(gaps[max(0, i - 10):i] + gaps[i + 1:i + 11]) or g
        a, b = place_of.get(its[i]['id']), place_of.get(its[i + 1]['id'])
        if g >= 2700 or (g >= 480 and g >= 6 * max(local, 30)) or (a and b and a != b and g >= 180):
            cuts.append(i + 1)
    bounds = [0] + cuts + [len(its)]
    todo, out = [(bounds[k], bounds[k + 1]) for k in range(len(bounds) - 1)], []
    while todo:  # a long stretch without a clear pause (a party, a hike) is cut at its longest break
        s, e = todo.pop(0)
        if e - s > 2 and (ts[e - 1] - ts[s]).total_seconds() > 7200:
            j = max(range(s, e - 1), key=lambda k: gaps[k])
            if gaps[j] >= 120:
                todo[:0] = [(s, j + 1), (j + 1, e)]
                continue
        out.append((s, e))
    return out


def geocode(lat, lon, lang, cache):
    key = f'{lat:.3f},{lon:.3f},{lang}'
    if key in cache:
        return cache[key]
    q = urllib.parse.urlencode({'format': 'jsonv2', 'lat': f'{lat:.2f}', 'lon': f'{lon:.2f}', 'zoom': 13,
                                'accept-language': lang})
    req = urllib.request.Request('https://nominatim.openstreetmap.org/reverse?' + q,
                                 headers={'User-Agent': 'rega-album-maker/1.0 (https://github.com/tamirgur/rega-album-maker)'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.load(r)
    except Exception as e:
        print(f'  geocoding failed ({e}); names stay empty', file=sys.stderr)
        if sys.platform == 'darwin' and 'CERTIFICATE_VERIFY_FAILED' in str(e):
            print('  On a Mac, Python from python.org needs its certificates once: open Applications > Python 3.x > '
                  'Install Certificates.command, then run this again.', file=sys.stderr)
        return None
    finally:
        time.sleep(1.1)  # OpenStreetMap's usage policy: at most one request per second
    a = d.get('address') or {}
    if d.get('category') == 'aeroway' and d.get('name'):   # an airport: its own name
        cache[key] = d['name']
        return d['name']
    # a place is a 2.5 km cluster: the town or village fits better than a street; zoom 13 reaches villages,
    # and the coordinates sent are rounded to about 1 km
    name = next((a[k] for k in ('city', 'town', 'village', 'hamlet', 'island', 'suburb', 'locality', 'municipality', 'county', 'state') if a.get(k)),
                d.get('name'))
    cache[key] = name
    return name


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work', required=True)
    ap.add_argument('--geocode', action='store_true')
    ap.add_argument('--lang', help='the language for place names and labels, e.g. en, he, fr (else the brief\'s)')
    ap.add_argument('--place-km', type=float, default=2.5)
    a = ap.parse_args()

    scan = load(os.path.join(a.work, 'scan.json'))
    bpath = os.path.join(a.work, 'brief.json')
    brief = load(bpath) if os.path.isfile(bpath) else {}
    lang = a.lang or (brief.get('book') or {}).get('lang') or 'he'
    items = [r for r in scan['items'] if r['in_range'] and not {'error', 'live'} & set(r['flags'])]
    by_day = defaultdict(list)
    for r in items:
        by_day[r['day']].append(r)
    for key in [k for k, its in by_day.items()  # a day of set-aside files only (a sticker, a copy) is no day
                if not any(r['kind'] == 'video' or not set(r['flags']) & EXCLUDE for r in its)]:
        del by_day[key]
    old = {}
    gpath = os.path.join(a.work, 'groups.json')
    if os.path.isfile(gpath):  # keep names the user already fixed
        for d in load(gpath).get('days', []):
            for p in d['places']:
                if p.get('name'):
                    old[(round(p['lat'], 3), round(p['lon'], 3))] = p['name']
    cache_path = os.path.join(a.work, 'geocode-cache.json')
    cache = load(cache_path) if os.path.isfile(cache_path) else {}

    days, seen = [], []
    for n, key in enumerate(sorted(by_day), 1):
        its = sorted(by_day[key], key=lambda r: r['taken'])
        places, loose = cluster(its, a.place_km)
        cands = [r for r in its if r['kind'] == 'photo' and not set(r['flags']) & EXCLUDE]
        out_places, place_of = [], {}
        for k, p in enumerate(places, 1):
            lat, lon = round(p['c'][0], 5), round(p['c'][1], 5)
            name = old.get((round(lat, 3), round(lon, 3)))
            if name is None and a.geocode:
                name = geocode(lat, lon, lang, cache)
            pid = f'{n:02d}-{k}'
            out_places.append({'id': pid, 'name': name, 'lat': lat, 'lon': lon, 'count': len(p['ids']),
                               't0': p['t0'], 't1': p['t1'], 'ids': p['ids']})
            place_of.update({i: pid for i in p['ids']})
        pinfo = {p['id']: p for p in out_places}
        timed = [r for r in its if not set(r['flags']) & UNTIMED]
        moments = []
        for k, (s, e) in enumerate(cut_moments(timed, place_of) if timed else [], 1):
            part = timed[s:e]
            pid = Counter(place_of[r['id']] for r in part if r['id'] in place_of).most_common(1)
            pid = pid[0][0] if pid else None
            new = False
            if pid:  # the first moment at a place not seen on any earlier day or moment
                c = (pinfo[pid]['lat'], pinfo[pid]['lon'])
                new = all(km(c, x) > a.place_km for x in seen)
                seen.append(c)
            moments.append({'id': f'{n:02d}-m{k}', 't0': part[0]['taken'], 't1': part[-1]['taken'], 'place': pid,
                            'new_place': new, 'ids': [r['id'] for r in part],
                            'shots': sum(r['kind'] == 'photo' for r in part),
                            'videos': sum(r['kind'] == 'video' for r in part),
                            'candidates': sum(r['kind'] == 'photo' and not set(r['flags']) & EXCLUDE for r in part)})
        d = date.fromisoformat(key)
        days.append({'n': n, 'key': key, 'weekday': d.weekday(), 'count': len(its), 'candidates': len(cands),
                     'ids': [r['id'] for r in its], 'videos': [r['id'] for r in its if r['kind'] == 'video'],
                     'places': out_places, 'loose': loose, 'track': track(its), 'moments': moments,
                     'untimed': [r['id'] for r in its if set(r['flags']) & UNTIMED],
                     'untimed_only': not timed})

    # key moments: far more photos than in a typical moment of this collection, or a video
    typical = median(m['shots'] for d in days for m in d['moments'])
    for d in days:
        for m in d['moments']:
            m['key'] = (m['shots'] >= 8 and m['shots'] >= 2.5 * max(typical, 1)) or (m['videos'] > 0 and m['shots'] >= 5)
            m['weight'] = round(math.log2(1 + m['shots']) + 1.5 * (m['videos'] > 0) + 1.0 * m['new_place'], 2)

    has_gps = any(d['track'] for d in days)
    pages = (brief.get('format') or {}).get('pages')
    chapters = sum(1 for d in days if d['candidates'])
    target = photos_for(pages, chapters, has_gps, per_page(brief)) if pages else None
    for d, q in zip(days, quotas([d['candidates'] for d in days], target)):
        d['quota'] = q
    if a.geocode:
        save(cache_path, cache)
    save(gpath, {'lang': lang, 'days': days, 'has_gps': has_gps, 'pages': pages, 'photos': sum(d['quota'] for d in days)})

    t = words(lang)
    nm = sum(len(d['moments']) for d in days)
    print(f'{len(days)} days, {sum(len(d["places"]) for d in days)} places, {nm} moments '
          f'({sum(m["key"] for d in days for m in d["moments"])} key). '
          + (f'Planned for {pages} pages: choose about {sum(d["quota"] for d in days)} photos.' if pages else
             f'Without a page count: choose about {sum(d["quota"] for d in days)} photos.'))

    def label(p):
        return (p['name'] or '({:.3f}, {:.3f})'.format(p['lat'], p['lon'])) + ' ({})'.format(p['count'])
    names = {p['id']: p['name'] for d in days for p in d['places']}
    for d in days:
        pl = ', '.join(label(p) for p in d['places']) or 'no GPS'
        print(f'  Day {d["n"]} · {(t["weekdays"] or [""] * 7)[d["weekday"]]} {d["key"]} · {d["count"]} files, {d["candidates"]} candidates, '
              f'choose about {d["quota"]} · {pl}' + (f' · {len(d["videos"])} video(s)' if d['videos'] else '') +
              (' · ONLY WhatsApp or undated files: this date may not be when they were taken' if d['untimed_only'] else ''))
        if len(days) <= 14:
            for m in d['moments']:
                where = names.get(m['place']) or ''
                print(f'      {m["id"]}  {m["t0"][11:16]}–{m["t1"][11:16]}  {m["shots"]} photos' +
                      (f', {m["videos"]} video(s)' if m['videos'] else '') + (f' · {where}' if where else '') +
                      (' · new place' if m['new_place'] else '') + (' · KEY' if m['key'] else ''))
            if d['untimed']:
                print(f'      + {len(d["untimed"])} WhatsApp, undated or copied file(s), outside the moments')
    print('Place names can be fixed in groups.json ("name"); they are kept when you run this again.')


if __name__ == '__main__':
    main()
