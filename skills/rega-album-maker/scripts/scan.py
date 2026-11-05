#!/usr/bin/env python3
"""Read every photo and video once: date, place, camera, a thumbnail and quality signals.

    python scan.py FOLDER [FOLDER ...] --work WORK [--from 2024-07-10] [--to 2024-07-12]
                   [--tz 3] [--shift "GoPro=+3"] [--workers 6]

--tz     hours from UTC at the trip, for times stored in UTC (Pixel file names, most videos, Google Takeout).
         Default: the most common offset found in the photos' EXIF, else 0.
--shift  fix a camera whose clock was wrong: every file whose camera make or model contains the text
         is moved by that many hours. Repeatable.

Every collection is different, so the scan adapts:
- with --from/--to, a file whose name dates it well outside the dates is skipped unopened (a cloud folder such as
  OneDrive downloads every file that is opened);
- hidden files and folders are skipped: macOS "._" copies, Android ".trashed-" photos, NAS indexes, the recycle bin;
- the short video of an iPhone Live Photo (same name as the photo, a few seconds long) is marked "live", not a video;
- a photo found twice (in another folder, sent on WhatsApp, in a Google Takeout album) is marked "copy" of the one
  with the best date and size;
- blurry, too dark and too bright are judged against the photos taken around it, so a night out, a concert or a
  snowy day is kept, while a single bad frame among good ones is flagged;
- images too small to print (stickers, thumbnails) are marked "small"; RAW files are counted, not read.

Writes WORK/scan.json and WORK/thumbs/. The photo folders are only read, never changed.
Re-running reuses the results for files that did not change.
"""
import argparse
import bisect
import hashlib
import math
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (HEIF, IMAGE_EXT, RAW_EXT, SCREENSHOT, SKIP_DIR, VIDEO_EXT, day_of, exif_info, fmt_time, hamming,  # noqa: E402
                    load, median, name_date, parse_time, save, sidecar_info, tool, video_meta)

EXCLUDE = {'dup', 'copy', 'blur', 'dark', 'bright', 'screenshot', 'small', 'error'}  # flags that keep a photo off the sheets
# which date to trust when the same photo is found twice: its own metadata, then a file name, then WhatsApp, then nothing
DATE_RANK = {'exif': 0, 'takeout': 0, 'video': 0, 'name': 1, 'name_utc': 1, 'video_utc': 1, 'whatsapp': 2, 'file_time': 3}


def photo_info(path, thumb):
    from PIL import Image, ImageFilter, ImageOps, ImageStat
    im = Image.open(path)
    fmt = im.format
    info = exif_info(im)
    w, h = im.size
    if info.pop('orientation', 1) in (5, 6, 7, 8):
        w, h = h, w
    if fmt == 'JPEG':
        im.draft('RGB', (900, 900))
    im = ImageOps.exif_transpose(im).convert('RGB')
    im.thumbnail((640, 640))
    im.save(thumb, quality=82)
    g = im.convert('L')  # 640 px: small enough to be fast, big enough to tell blur from soft light
    lap = g.filter(ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), 1, 128))
    hist = g.histogram()
    n = float(sum(hist))
    px = list(g.resize((9, 8), Image.BILINEAR).getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (px[y * 9 + x] > px[y * 9 + x + 1])
    return dict(info, w=w, h=h, fmt=fmt, sharp=round(ImageStat.Stat(lap).var[0], 1),
                mean=round(ImageStat.Stat(g).mean[0], 1), dark=round(sum(hist[:32]) / n, 3),
                clip=round(sum(hist[246:]) / n, 3), dhash=f'{bits:016x}')


def video_info(path, thumb):
    out = video_meta(path)
    ff = tool('ffmpeg')
    if ff and out.get('duration'):
        import subprocess
        at = min(1.0, out['duration'] / 3)
        subprocess.run([ff, '-y', '-loglevel', 'error', '-ss', f'{at:.2f}', '-i', path, '-frames:v', '1',
                        '-vf', 'scale=640:-2', thumb], capture_output=True)
    return out


def analyze(job):
    path, thumbs = job
    st = os.stat(path)
    key = hashlib.sha1(path.encode('utf-8')).hexdigest()[:12]
    rec = {'path': path, 'name': os.path.basename(path), 'size': st.st_size, 'mtime': int(st.st_mtime), 'key': key}
    thumb = os.path.join(thumbs, key + '.jpg')
    try:
        if os.path.splitext(path)[1].lower() in VIDEO_EXT:
            rec['kind'] = 'video'
            rec.update(video_info(path, thumb))
        else:
            rec['kind'] = 'photo'
            rec.update(photo_info(path, thumb))
        rec.update({k: v for k, v in sidecar_info(path).items() if k not in rec})
    except Exception as e:  # a broken file must not stop the scan
        rec['error'] = f'{type(e).__name__}: {e}'[:200]
    if os.path.isfile(thumb):
        rec['thumb'] = thumb
    return rec


def resolve_time(r, tz, shifts):
    """The best local time for a file, and where it came from."""
    t, src = None, None
    if r.get('exif_time'):
        t, src = parse_time(r['exif_time']), 'exif'
    elif r.get('video_local'):
        t, src = parse_time(r['video_local']), 'video'
    elif r.get('takeout_utc'):
        t, src = parse_time(r['takeout_utc']) + timedelta(hours=tz), 'takeout'
    elif r.get('video_utc'):
        t, src = parse_time(r['video_utc']) + timedelta(hours=tz), 'video_utc'
    if t is None:
        nt, kind = name_date(r['name'])
        if nt:
            t, src = (nt + timedelta(hours=tz), 'name_utc') if kind == 'utc' else (nt, 'whatsapp' if kind == 'whatsapp' else 'name')
    if t is None:
        t, src = datetime.fromtimestamp(r['mtime']), 'file_time'
    cam = f"{r.get('make', '')} {r.get('model', '')}".lower()
    for text, hours in shifts:
        if text in cam:
            t += timedelta(hours=hours)
    return t, src


def window_median(photos, times, key, secs=2700):
    """For each photo: the median of `key` over the photos taken within `secs` of it, and how many there are."""
    out, win, lo, hi = [], [], 0, -1
    for i in range(len(photos)):
        while hi + 1 < len(photos) and (times[hi + 1] - times[i]).total_seconds() <= secs:
            hi += 1
            bisect.insort(win, photos[hi][key])
        while (times[i] - times[lo]).total_seconds() > secs:
            win.pop(bisect.bisect_left(win, photos[lo][key]))
            lo += 1
        out.append((win[len(win) // 2], len(win)))
    return out


def looks_same(a, b):
    """Two thumbnails that are the same picture, give or take compression and size."""
    from PIL import Image, ImageChops, ImageStat
    try:
        x, y = (Image.open(r['thumb']).convert('L').resize((32, 32)) for r in (a, b))
    except Exception:
        return True  # no thumbnails: the hash, the shape and the brightness already agree
    return ImageStat.Stat(ImageChops.difference(x, y)).mean[0] < 8


def copy_pairs(photos):
    """Pairs of photos that are the same picture at different times: a copy in another folder or from another source."""
    bands = defaultdict(list)
    for r in photos:
        h = int(r['dhash'], 16)
        if not 6 <= bin(h).count('1') <= 58:  # a nearly flat picture (sky, a wall, a dark frame) says too little
            continue
        for b, sh in enumerate((0, 13, 26, 39, 52)):  # within distance 4, two hashes share at least one of 5 bands
            bands[(b, (h >> sh) & 0x1FFF)].append(r)
    seen, pairs = set(), []
    for grp in bands.values():
        if not 1 < len(grp) <= 60:
            continue
        for i, a in enumerate(grp):
            for b in grp[i + 1:]:
                k = (min(a['id'], b['id']), max(a['id'], b['id']))
                if k in seen:
                    continue
                seen.add(k)
                if abs((parse_time(a['taken']) - parse_time(b['taken'])).total_seconds()) <= 180:
                    continue  # a burst: handled with the near-duplicates
                if a['date_source'] == b['date_source'] == 'exif' and (a.get('make'), a.get('model')) == (b.get('make'), b.get('model')):
                    continue  # two shots of the same view by the same camera: separate photos, not a copy
                ra, rb = a['w'] / a['h'], b['w'] / b['h']
                if hamming(a['dhash'], b['dhash']) <= 4 and abs(ra - rb) <= 0.02 * ra and abs(a['mean'] - b['mean']) <= 12 \
                        and looks_same(a, b):
                    pairs.append((a, b))
    return pairs


def union(pairs, ids):
    """Groups of two or more ids, joined by the pairs."""
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in pairs:
        parent[find(a)] = find(b)
    groups = defaultdict(list)
    for i in ids:
        groups[find(i)].append(i)
    return [g for g in groups.values() if len(g) > 1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('folders', nargs='+')
    ap.add_argument('--work', required=True)
    ap.add_argument('--from', dest='d0')
    ap.add_argument('--to', dest='d1')
    ap.add_argument('--tz', type=float)
    ap.add_argument('--shift', action='append', default=[])
    ap.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()

    work = os.path.abspath(a.work)
    folders = [os.path.abspath(f) for f in a.folders]
    for f in folders:
        if not os.path.isdir(f):
            sys.exit(f'Not a folder: {f}')
        if work == f:
            sys.exit('The work folder must not be a photo folder, so the originals stay untouched.')
        if work.startswith(f + os.sep) and not os.path.isfile(os.path.join(work, 'brief.json')):
            sys.exit('The work folder is inside a photo folder. Start it with brief.py --init (it is then skipped by '
                     'the scan), or put it elsewhere.')
    thumbs = os.path.join(work, 'thumbs')
    os.makedirs(thumbs, exist_ok=True)

    files, other, raw = [], 0, 0
    for root in folders:
        for dp, dns, fns in os.walk(root):
            # never the hidden or system folders, and never a book's own work folder (it holds a brief.json)
            dns[:] = [d for d in dns if not SKIP_DIR.match(d) and not os.path.isfile(os.path.join(dp, d, 'brief.json'))]
            for fn in fns:
                if fn.startswith('.'):  # hidden: macOS "._" copies, Android ".trashed-" photos
                    continue
                ext = os.path.splitext(fn)[1].lower()
                if ext in IMAGE_EXT or ext in VIDEO_EXT:
                    files.append(os.path.join(dp, fn))
                elif ext in RAW_EXT:
                    raw += 1
                elif not fn.endswith('.json'):
                    other += 1

    d0 = date.fromisoformat(a.d0) if a.d0 else None
    d1 = date.fromisoformat(a.d1) if a.d1 else None
    outside = 0
    if d0 or d1:  # a name that dates the file well outside the dates: skip it unopened (a cloud folder downloads what is opened)
        keep = []
        for p in files:
            nt, _ = name_date(os.path.basename(p))
            if nt and ((d0 and nt.date() < d0 - timedelta(days=2)) or (d1 and nt.date() > d1 + timedelta(days=2))):
                outside += 1
            else:
                keep.append(p)
        files = keep

    old = {}
    scan_path = os.path.join(work, 'scan.json')
    if os.path.isfile(scan_path):
        for r in load(scan_path).get('items', []):
            old[r['path']] = r
    recs, todo = [], []
    for p in files:
        st = os.stat(p)
        r = old.get(p)
        if r and r.get('size') == st.st_size and r.get('mtime') == int(st.st_mtime) and \
                (r.get('thumb') is None or os.path.isfile(r['thumb'])):
            recs.append({k: v for k, v in r.items() if k not in ('id', 'taken', 'date_source', 'flags', 'score', 'dup_of', 'in_range', 'day')})
        else:
            todo.append(p)
    print(f'{len(files):,} photos and videos in {len(folders)} folder(s), {other:,} other files' +
          (f', {raw:,} RAW files (not read: use the JPEGs saved beside them, or export JPEGs)' if raw else '') +
          (f', {outside:,} skipped unopened: their names date them outside the dates' if outside else '') + '. '
          f'Reading {len(todo):,} ({len(files) - len(todo):,} known from the last scan).', flush=True)
    t0, step = time.time(), max(200, len(todo) // 20)
    if todo:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            for i, r in enumerate(ex.map(analyze, [(p, thumbs) for p in todo], chunksize=8), 1):
                recs.append(r)
                if i % step == 0:
                    print(f'  {i:,} of {len(todo):,} read ({time.time() - t0:.0f} s)', flush=True)

    import faces
    has_faces = faces.available()
    if has_faces:  # faces, from the thumbnails: where people are, so a crop or a title never touches them
        todo_f = [r for r in recs if r['kind'] == 'photo' and 'error' not in r and r.get('thumb') and 'faces' not in r]
        for r in todo_f:
            try:
                r['faces'] = faces.detect(r['thumb'])
            except Exception:
                r['faces'] = []
        if todo_f:
            print(f'Looked for faces in {len(todo_f):,} photos.', flush=True)

    offs = Counter(round(r['offset'] * 2) / 2 for r in recs if 'offset' in r)
    tz = a.tz if a.tz is not None else (offs.most_common(1)[0][0] if offs else 0.0)
    shifts = []
    for s in a.shift:
        text, _, hours = s.rpartition('=')
        shifts.append((text.strip().lower(), float(hours)))

    stems = {(os.path.dirname(r['path']), os.path.splitext(r['name'])[0].lower()) for r in recs if r['kind'] == 'photo'}
    for r in recs:
        root = next((f for f in folders if r['path'].startswith(f + os.sep)), folders[0])
        rel = os.path.relpath(os.path.dirname(r['path']), root)
        r['folder'] = os.path.basename(root) + ('' if rel == '.' else '/' + rel.replace(os.sep, '/'))
        t, src = resolve_time(r, tz, shifts)
        r['taken'], r['date_source'] = fmt_time(t), src
        r['day'] = day_of(t).isoformat()
        r['in_range'] = (d0 is None or day_of(t) >= d0) and (d1 is None or day_of(t) <= d1)
        f = []
        if 'error' in r:
            f.append('error')
        if src == 'whatsapp':
            f.append('whatsapp')
        if src == 'file_time':
            f.append('undated')
        if r['kind'] == 'photo' and 'error' not in r:
            if SCREENSHOT.search(r['name']) or (r.get('fmt') == 'PNG' and not r.get('make')):
                f.append('screenshot')
            if max(r['w'], r['h']) < 600:
                f.append('small')
        if r['kind'] == 'video' and (r.get('duration') or 0) <= 4.5 and \
                (os.path.dirname(r['path']), os.path.splitext(r['name'])[0].lower()) in stems:
            f.append('live')  # the moving part of a Live Photo, not a video of its own
        r['flags'] = f
    photo_time = {(os.path.dirname(r['path']), os.path.splitext(r['name'])[0].lower()): r for r in recs if r['kind'] == 'photo'}
    for r in recs:  # a Live Photo's video belongs to the moment of its photo
        if 'live' in r['flags']:
            ph = photo_time[(os.path.dirname(r['path']), os.path.splitext(r['name'])[0].lower())]
            r['taken'], r['date_source'], r['day'], r['in_range'] = ph['taken'], ph['date_source'], ph['day'], ph['in_range']
            r['flags'] = [f for f in r['flags'] if f != 'undated'] + [f for f in ph['flags'] if f == 'undated']
    recs.sort(key=lambda r: (r['taken'], r['name']))
    # ids stay the same from one scan to the next, so a selection made earlier still points at the same photos;
    # a new file gets the next free number
    old_id = {p: r['id'] for p, r in old.items() if 'id' in r}
    nxt = max(old_id.values(), default=0) + 1
    for r in recs:
        if r['path'] in old_id:
            r['id'] = old_id[r['path']]
        else:
            r['id'] = nxt
            nxt += 1

    photos = [r for r in recs if r['kind'] == 'photo' and 'error' not in r and r['in_range']]
    by_day = defaultdict(list)
    for r in photos:
        by_day[r['day']].append(r['sharp'])
    all_sharp = median(r['sharp'] for r in photos)
    times = [parse_time(r['taken']) for r in photos]
    # each photo is judged against the photos taken within 45 minutes of it
    for r, (near_sharp, n), (near_mean, _) in zip(photos, window_median(photos, times, 'sharp'),
                                                   window_median(photos, times, 'mean')):
        alone = n < 5
        base = (median(by_day[r['day']]) if len(by_day[r['day']]) >= 4 else all_sharp) if alone else near_sharp
        if r['sharp'] < 0.2 * base:  # real photos: blurred ~0.08 of the median, sharp >= 0.26
            r['flags'].append('blur')
        if (r['mean'] < 32 or r['dark'] > 0.6) and (r['mean'] < 12 or alone or r['mean'] < 0.6 * near_mean):
            r['flags'].append('dark')
        if (r['mean'] > 228 or r['clip'] > 0.45) and (r['mean'] > 245 or alone or r['mean'] > near_mean + 30):
            r['flags'].append('bright')
        r['score'] = round(math.log10(1 + r['sharp']) - abs(r['mean'] - 125) / 90 - 3 * r['clip'] - 2 * r['dark'], 3)

    # near-duplicates: similar pictures (dHash distance <= 10) taken within 3 minutes form a burst; keep the best
    pairs = []
    for i, r in enumerate(photos):
        j = i - 1
        while j >= 0 and (times[i] - times[j]).total_seconds() <= 180:
            if hamming(r['dhash'], photos[j]['dhash']) <= 10:
                pairs.append((r['id'], photos[j]['id']))
            j -= 1
    byid = {r['id']: r for r in photos}
    for group in union(pairs, list(byid)):
        group = [byid[i] for i in group]
        best = max(group, key=lambda r: (not set(r['flags']) & EXCLUDE, r['score']))
        for r in group:
            if r is not best:
                r['flags'].append('dup')
                r['dup_of'] = best['id']

    # the same picture found twice at different times: keep the one with the best date, then the biggest
    for group in union([(a['id'], b['id']) for a, b in copy_pairs(photos)], list(byid)):
        group = [byid[i] for i in group]
        keep = min(group, key=lambda r: (DATE_RANK.get(r['date_source'], 3), -r['w'] * r['h'], r['path']))
        for r in group:
            if r is not keep:
                r['flags'].append('copy')
                r['dup_of'] = keep['id']

    save(scan_path, {'folders': folders, 'from': a.d0, 'to': a.d1, 'tz': tz, 'items': recs})

    inr = [r for r in recs if r['in_range']]
    cnt = Counter(f for r in inr for f in r['flags'])
    vids = [r for r in inr if r['kind'] == 'video' and 'live' not in r['flags']]
    print(f'\nDone in {time.time() - t0:.0f} s. Time zone used for UTC times: {tz:+g} h.')
    if has_faces:
        with_people = sum(bool(r.get('faces')) for r in photos)
        print(f'Faces: people in {with_people:,} photos, nobody in {len(photos) - with_people:,}.')
    else:
        print('Faces: not looked for (pip install opencv-python-headless). Photos with people will not be cropped.')
    if d0 or d1:
        print(f'In the dates: {len(photos):,} photos and {len(vids):,} videos. Outside the dates: {len(recs) - len(inr):,} files (ignored).')
    else:
        print(f'{len(photos):,} photos and {len(vids):,} videos.')
    names = {'dup': 'near-duplicates', 'copy': 'copies of a photo found in another folder or source', 'blur': 'blurry',
             'dark': 'too dark', 'bright': 'too bright', 'screenshot': 'screenshots', 'small': 'too small to print',
             'live': 'Live Photo videos (part of their photo)', 'whatsapp': 'WhatsApp or saved files (date = day received or saved)',
             'undated': 'undated (file date only)', 'error': 'unreadable'}
    if cnt:
        print('Flags: ' + ', '.join(f'{cnt[k]:,} {v}' for k, v in names.items() if cnt[k]))
    heic = sum('error' in r['flags'] and r['name'].lower().endswith(('.heic', '.heif')) for r in inr)
    if heic and not HEIF:
        print(f'{heic:,} iPhone HEIC photos could not be read. Install pillow-heif (pip install pillow-heif), then scan again.')
    cams = Counter(' '.join(x for x in (r.get('make'), r.get('model')) if x) or 'no camera info'
                   for r in inr if r['kind'] == 'photo' and 'error' not in r['flags'])
    print('Cameras: ' + ', '.join(f'{k} ({v:,})' for k, v in cams.most_common(6)))
    fold = Counter(r['folder'] for r in inr)
    print('Folders: ' + ', '.join(f'{k} ({v:,})' for k, v in fold.most_common(8)) + (' ...' if len(fold) > 8 else ''))
    if not tool('ffprobe') and vids:
        print('Note: ffprobe (part of ffmpeg) is missing, so video dates come from file names or file times.')
    days = Counter(r['day'] for r in inr)
    cand = Counter(r['day'] for r in photos if not set(r['flags']) & EXCLUDE)
    print('Days (photos and videos / photo candidates):')
    for d in sorted(days):
        print(f'  {d}: {days[d]:,} / {cand[d]:,}')
    if len(days) > 40:
        print('That is many days. If the book covers a shorter period, scan again with --from and --to.')


if __name__ == '__main__':
    main()
