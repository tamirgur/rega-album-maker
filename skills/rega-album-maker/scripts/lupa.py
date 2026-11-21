#!/usr/bin/env python3
"""Prepare and upload curated Rega photos for Lupa via Lupa MCP.

    python lupa.py --work WORK --choose --cover COVER_ID --density DENSITY --direction RTL|LTR
                   [--book-type REGULAR] [--photos N] [--min-photos N] [--max-photos N] [--album TOKEN]
    python lupa.py --work WORK --pack [--check-only]
    python lupa.py --work WORK --sync
    python lupa.py --work WORK --upload --album TOKEN --ticket TICKET [--folder-name NAME | --no-folder-name] [--workers 6]

--choose  writes the Lupa product settings and target photo count into WORK/brief.json.
--pack    checks selected photos against Lupa rules (>= 800 px both sides, <= 15 MB or JPEG compressed
          to <= 2400 px short side) and prepares WORK/../for-lupa/ (or ללופה/) + WORK/lupa-manifest.json.
--sync    reconciles WORK/lupa-manifest.json and WORK/selection.json if photos were deleted from for-lupa/ללופה.
--upload  syncs deletions, then uploads the packed photos to Lupa's upload_api using a ticket from
          start_album/get_upload_link, saving progress in WORK/lupa-upload-state.json (exit code 2 on 401).
"""
import argparse
import io
import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import album_dir, load, save  # noqa: E402

ACCEPTED_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.heic', '.heif', '.avif'}
MIN_SIDE_PX = 800
MAX_BYTES = 15_728_640
COMPRESS_SHORT_SIDE = 2400
JPEG_QUALITY = 85
MAX_PARALLEL = 6
UPLOAD_BASE = 'https://mcp.lupa.co.il/upload'
BOOK_BOUNDS = {
    'REGULAR': (24, 864),
    'MINI_LUPA': (24, 144),
    'HAGGADAH': (24, 60),
}
EXTRA_MIME = {
    '.heic': 'image/heic',
    '.heif': 'image/heif',
    '.webp': 'image/webp',
    '.avif': 'image/avif',
}


def _ascii_stem(path, fallback_id):
    stem = os.path.splitext(os.path.basename(path))[0]
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', '_', stem).strip('._-')
    return (cleaned[:48] if cleaned else f'photo_{fallback_id}')


def _image_size(path, rec):
    w, h = rec.get('w'), rec.get('h')
    if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
        return w, h
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
        try:
            orient = im.getexif().get(0x0112, 1)
        except Exception:
            orient = 1
    if orient in (5, 6, 7, 8):
        w, h = h, w
    return w, h


def _compress_to_jpeg(src, dst_path=None):
    """Re-encode >15 MB photo as sRGB JPEG with shorter side <= 2400 px, quality 85, preserving EXIF."""
    from PIL import Image, ImageCms, ImageOps
    with Image.open(src) as raw:
        icc = raw.info.get('icc_profile')
        try:
            exif = raw.getexif()
        except Exception:
            exif = None
        im = ImageOps.exif_transpose(raw)
        if icc:
            try:
                im = ImageCms.profileToProfile(
                    im,
                    ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                    ImageCms.createProfile('sRGB'),
                    outputMode='RGB',
                )
            except Exception:
                im = im.convert('RGB')
        else:
            im = im.convert('RGB')
        cw, ch = im.size
        short = min(cw, ch)
        if short > COMPRESS_SHORT_SIDE:
            scale = COMPRESS_SHORT_SIDE / short
            im = im.resize((max(1, round(cw * scale)), max(1, round(ch * scale))), Image.LANCZOS)
        save_kwargs = {'format': 'JPEG', 'quality': JPEG_QUALITY, 'optimize': True}
        if exif:
            if 0x0112 in exif:
                exif[0x0112] = 1  # already transposed above; prevent double-rotation in Lupa
            try:
                save_kwargs['exif'] = exif.tobytes()
            except Exception:
                pass
        for q in (JPEG_QUALITY, 80):
            save_kwargs['quality'] = q
            buf = io.BytesIO()
            try:
                im.save(buf, **save_kwargs)
            except Exception:
                save_kwargs.pop('exif', None)
                buf = io.BytesIO()
                im.save(buf, **save_kwargs)
            data = buf.getvalue()
            if len(data) <= MAX_BYTES:
                if dst_path:
                    with open(dst_path, 'wb') as f:
                        f.write(data)
                return len(data), im.size[0], im.size[1]
    return None, im.size[0], im.size[1]


def choose(work, args):
    path = os.path.join(work, 'brief.json')
    brief = load(path)
    if not args.cover or not args.density or not args.direction:
        sys.exit('--choose requires --cover, --density, and --direction')
    book_type = (args.book_type or 'REGULAR').upper()
    if book_type not in BOOK_BOUNDS:
        sys.exit(f'Unknown book_type "{book_type}". Expected one of: {", ".join(BOOK_BOUNDS)}')
    direction = args.direction.upper()
    if direction not in ('RTL', 'LTR'):
        sys.exit('--direction must be RTL or LTR')
    def_min, def_max = BOOK_BOUNDS[book_type]
    min_p = args.min_photos if args.min_photos is not None else def_min
    max_p = args.max_photos if args.max_photos is not None else def_max
    if min_p < 1 or max_p < min_p:
        sys.exit(f'Invalid photo bounds {min_p}..{max_p}')

    prev_print = brief.get('print') or {}
    album = args.album if args.album is not None else (prev_print.get('album') if prev_print.get('printer') == 'lupa' else None)
    brief['print'] = {
        'printer': 'lupa',
        'book_type': book_type,
        'cover_id': args.cover,
        'density': args.density,
        'direction': direction,
        'photos_min': min_p,
        'photos_max': max_p,
        'album': album,
    }

    fmt = dict(brief.get('format') or {})
    fmt.update({'size': f'lupa-{args.cover}', 'min_photos': min_p, 'max_photos': max_p})
    note = ''
    target = args.photos if args.photos is not None else fmt.get('target_photos')
    if isinstance(target, int):
        if target <= 0:
            sys.exit('--photos must be positive')
        fixed = min(max(target, min_p), max_p)
        if fixed != target:
            note = f' Target photo count moved from {target} to {fixed} to fit {args.cover} ({min_p}-{max_p}).'
        fmt['target_photos'] = fixed
    brief['format'] = fmt

    if brief.get('design') is None:
        brief['design'] = {'mode': 'lupa', 'theme': None}
    save(path, brief)

    print(f'Chose Lupa: {book_type}, cover {args.cover}, density {args.density}, {direction}, {min_p}-{max_p} photos.'
          + (f' Target: {fmt["target_photos"]} photos.' if isinstance(fmt.get('target_photos'), int) else '') + note)
    print('Next: run brief.py --options for photo counts, then group.py.')


def _collect_selected_ids(selection):
    raw = []
    if selection.get('cover') is not None:
        raw.append(selection['cover'])
    for ch in selection.get('chapters') or selection.get('days') or []:
        raw.extend(ch.get('photos') or [])
    if selection.get('closing') is not None:
        raw.append(selection['closing'])
    seen, ordered = set(), []
    for pid in raw:
        if pid not in seen:
            seen.add(pid)
            ordered.append(pid)
    return ordered


def _write_summary(out_dir, he, title, items, skipped, min_p, max_p, book_type, cover_id, density, direction):
    compressed_cnt = sum(1 for it in items if it.get('compressed'))
    summary_name = 'סיכום-ללופה.md' if he else 'lupa-summary.md'
    if he:
        lines = [
            f'# מוכן להעלאה ללופה: {title or "אלבום"}',
            '',
            f'- **מוכנות להעלאה:** {len(items)} תמונות (טווח מותר: {min_p}–{max_p})',
            f'- **דחוסות (מעל 15 מ"ב במקור):** {compressed_cnt}',
            f'- **נדחו / לא נכללו:** {len(skipped)}',
            f'- **סוג / כריכה / צפיפות / כיוון:** {book_type} / `{cover_id}` / `{density}` / `{direction}`',
        ]
    else:
        lines = [
            f'# Ready for Lupa: {title or "Album"}',
            '',
            f'- **Ready to upload:** {len(items)} photos (allowed: {min_p}-{max_p})',
            f'- **Compressed (>15 MB originals):** {compressed_cnt}',
            f'- **Skipped:** {len(skipped)}',
            f'- **Product:** {book_type} / `{cover_id}` / `{density}` / `{direction}`',
        ]
    if skipped:
        lines += ['', '## Skipped' if not he else '## תמונות שנדחו']
        lines += [f'- #{s["id"]}: {s["reason"]}' for s in skipped]
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, summary_name), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


def pack(work, check_only=False):
    brief = load(os.path.join(work, 'brief.json'))
    scan = load(os.path.join(work, 'scan.json'))
    sel_path = os.path.join(work, 'selection.json')
    if not os.path.isfile(sel_path):
        sys.exit('No selection.json yet: choose photos first.')
    selection = load(sel_path)

    pr = brief.get('print') or {}
    if pr.get('printer') != 'lupa':
        sys.exit('brief.json printer is not "lupa". Run: python lupa.py --work WORK --choose ...')
    lang = (brief.get('book') or {}).get('lang') or 'en'
    he = str(lang).lower().startswith('he')
    title = ((brief.get('book') or {}).get('title') or selection.get('title') or '').strip()
    if title and not (2 <= len(title) <= 28):
        print(f'Warning: book title "{title}" is {len(title)} chars; Lupa finish_album requires 2-28 chars.')

    out_dir = os.path.join(album_dir(work), 'ללופה' if he else 'for-lupa')
    if not check_only:
        os.makedirs(out_dir, exist_ok=True)
        for fn in os.listdir(out_dir):
            if re.match(r'^\d{3,}_', fn) or fn in ('סיכום-ללופה.md', 'lupa-summary.md'):
                fp = os.path.join(out_dir, fn)
                if os.path.isfile(fp):
                    os.remove(fp)

    byid = {r['id']: r for r in scan['items']}
    ordered_ids = _collect_selected_ids(selection)
    items, skipped = [], []

    for pid in ordered_ids:
        rec = byid.get(pid)
        if rec is None:
            skipped.append({'id': pid, 'src': None, 'reason': 'id not found in scan.json'})
            continue
        src = rec['path']
        if not os.path.isfile(src):
            skipped.append({'id': pid, 'src': src, 'reason': 'file not found on disk'})
            continue
        ext = os.path.splitext(src)[1].lower()
        if ext not in ACCEPTED_EXT:
            skipped.append({'id': pid, 'src': src, 'reason': f'unsupported extension {ext}'})
            continue
        try:
            w, h = _image_size(src, rec)
        except Exception as e:
            skipped.append({'id': pid, 'src': src, 'reason': f'could not read dimensions: {e}'})
            continue
        if min(w, h) < MIN_SIDE_PX:
            skipped.append({
                'id': pid,
                'src': src,
                'reason': f'too small ({w}x{h} px; Lupa requires both sides >= {MIN_SIDE_PX} px)',
            })
            continue

        idx = len(items) + 1
        stem = _ascii_stem(src, pid)
        file_size = os.path.getsize(src)
        if file_size <= MAX_BYTES:
            out_name = f'{idx:03d}_{stem}{ext}'
            dst_path = os.path.join(out_dir, out_name)
            if not check_only:
                shutil.copy2(src, dst_path)
            items.append({
                'id': pid, 'file': out_name, 'path': dst_path, 'src': src,
                'w': w, 'h': h, 'bytes': file_size, 'compressed': False,
            })
        else:
            out_name = f'{idx:03d}_{stem}.jpg'
            dst_path = os.path.join(out_dir, out_name)
            try:
                out_bytes, nw, nh = _compress_to_jpeg(src, None if check_only else dst_path)
            except Exception as e:
                skipped.append({'id': pid, 'src': src, 'reason': f'compression failed (>15 MB; use upload_url): {e}'})
                continue
            if out_bytes is None:
                skipped.append({'id': pid, 'src': src, 'reason': 'still > 15 MB after JPEG compression; upload via upload_url'})
                continue
            items.append({
                'id': pid, 'file': out_name, 'path': dst_path, 'src': src,
                'w': nw, 'h': nh, 'bytes': out_bytes, 'compressed': True,
            })

    min_p = pr.get('photos_min') or 24
    max_p = pr.get('photos_max') or 864
    in_bounds = min_p <= len(items) <= max_p

    manifest = {
        'out_dir': out_dir,
        'title': title or None,
        'book_type': pr.get('book_type', 'REGULAR'),
        'cover_id': pr.get('cover_id'),
        'density': pr.get('density'),
        'direction': pr.get('direction'),
        'photos_min': min_p,
        'photos_max': max_p,
        'items': items,
        'skipped': skipped,
    }
    manifest_path = os.path.join(work, 'lupa-manifest.json')
    save(manifest_path, manifest)

    if not check_only:
        _write_summary(out_dir, he, title, items, skipped, min_p, max_p,
                       pr.get('book_type', 'REGULAR'), pr.get('cover_id'), pr.get('density'), pr.get('direction'))

    compressed_cnt = sum(1 for it in items if it.get('compressed'))
    print(f'Lupa pack{" (check only)" if check_only else ""}: {len(items)} ready ({compressed_cnt} compressed), '
          f'{len(skipped)} skipped. Folder: {out_dir}')
    for s in skipped:
        print(f'  SKIP #{s["id"]}: {s["reason"]}')
    if not in_bounds:
        print(f'OUT OF BOUNDS: {len(items)} photos ready, but {pr.get("cover_id")} requires {min_p}-{max_p}.')
        sys.exit(1)
    print(f'Manifest saved: {manifest_path}')


def sync(work, quiet_if_unchanged=False):
    """Reconcile lupa-manifest.json and selection.json when the user deletes files from for-lupa/ללופה."""
    manifest_path = os.path.join(work, 'lupa-manifest.json')
    if not os.path.isfile(manifest_path):
        sys.exit('No lupa-manifest.json yet: run lupa.py --pack first.')
    manifest = load(manifest_path)
    items = manifest.get('items') or []
    kept = [it for it in items if os.path.isfile(it['path'])]
    removed_cnt = len(items) - len(kept)

    brief_path = os.path.join(work, 'brief.json')
    brief = load(brief_path) if os.path.isfile(brief_path) else {}
    pr = brief.get('print') or {}
    min_p = pr.get('photos_min') or manifest.get('photos_min') or 24
    max_p = pr.get('photos_max') or manifest.get('photos_max') or 864

    if removed_cnt:
        kept_ids = {it['id'] for it in kept}
        sel_path = os.path.join(work, 'selection.json')
        if os.path.isfile(sel_path):
            sel = load(sel_path)
            for ch in sel.get('chapters') or sel.get('days') or []:
                ch['photos'] = [pid for pid in (ch.get('photos') or []) if pid in kept_ids]
            ordered_ids = [pid for ch in (sel.get('chapters') or sel.get('days') or []) for pid in (ch.get('photos') or [])]
            if sel.get('cover') not in kept_ids:
                sel['cover'] = ordered_ids[0] if ordered_ids else (kept[0]['id'] if kept else None)
            if sel.get('closing') not in kept_ids:
                sel['closing'] = ordered_ids[-1] if ordered_ids else (kept[-1]['id'] if kept else None)
            save(sel_path, sel)
        manifest['items'] = kept
        save(manifest_path, manifest)  # saved after selection.json so brief.py sees manifest up-to-date
        lang = (brief.get('book') or {}).get('lang') or 'en'
        he = str(lang).lower().startswith('he')
        _write_summary(
            manifest['out_dir'], he, manifest.get('title'), kept, manifest.get('skipped') or [],
            min_p, max_p, manifest.get('book_type', 'REGULAR'), manifest.get('cover_id'),
            manifest.get('density'), manifest.get('direction'),
        )
        print(f'Lupa sync: removed {removed_cnt} missing file(s); {len(kept)} photo(s) ready.')
    elif not quiet_if_unchanged:
        print(f'Lupa sync: all {len(kept)} packed photo(s) present.')

    if not (min_p <= len(kept) <= max_p):
        print(f'OUT OF BOUNDS: {len(kept)} photos ready, but {manifest.get("cover_id")} requires {min_p}-{max_p}.')
        sys.exit(1)
    return manifest


def _multipart_body(fields, file_field, filename, mime, file_bytes):
    boundary = f'----RegaLupa{uuid.uuid4().hex}'
    parts = []
    for k, v in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode('utf-8'))
    parts.append(
        (f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
         f'Content-Type: {mime}\r\n\r\n').encode('utf-8')
    )
    parts.append(file_bytes)
    parts.append(f'\r\n--{boundary}--\r\n'.encode('utf-8'))
    return boundary, b''.join(parts)


def _post_file(album, ticket, item, cancel_event):
    ext = os.path.splitext(item['path'])[1].lower()
    mime = EXTRA_MIME.get(ext) or mimetypes.guess_type(item['path'])[0] or 'application/octet-stream'
    with open(item['path'], 'rb') as f:
        data = f.read()
    fields = [('shouldCompress', 'false'), ('shouldResize', 'false')] if item.get('compressed') else []
    boundary, body = _multipart_body(fields, 'file', item['file'], mime, data)
    url = f'{UPLOAD_BASE}/{album}/files'
    headers = {
        'X-Upload-Ticket': ticket,
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Content-Length': str(len(body)),
    }
    for attempt in range(1, 4):
        if cancel_event.is_set():
            return 'aborted', item['file'], 'cancelled after 401'
        req = urllib.request.Request(url, data=body, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
                try:
                    j = json.loads(raw) if raw.strip() else {}
                except ValueError:
                    j = {}
                if j.get('ok') is False:
                    status = j.get('status')
                    if status == 503 and attempt < 3:
                        time.sleep(5)
                        continue
                    return 'err', item['file'], j.get('message') or raw
                return 'ok', item['file'], j.get('message') or 'uploaded'
        except urllib.error.HTTPError as e:
            msg = e.read().decode('utf-8', errors='replace')[:300]
            if e.code == 401:
                cancel_event.set()
                return '401', item['file'], msg
            if e.code == 503 and attempt < 3:
                time.sleep(5)
                continue
            return 'err', item['file'], f'HTTP {e.code}: {msg}'
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < 3:
                time.sleep(5)
                continue
            return 'err', item['file'], str(e)
    return 'err', item['file'], 'failed after 3 attempts'


def _set_folder_name(album, ticket, folder_name):
    url = f'{UPLOAD_BASE}/{album}/folder-name'
    body = json.dumps({'folder': folder_name}, ensure_ascii=False).encode('utf-8')
    headers = {
        'X-Upload-Ticket': ticket,
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Length': str(len(body)),
    }
    for attempt in range(1, 4):
        req = urllib.request.Request(url, data=body, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
                return 'ok', ''
        except urllib.error.HTTPError as e:
            msg = e.read().decode('utf-8', errors='replace')[:300]
            if e.code == 401:
                return '401', msg
            if e.code == 503 and attempt < 3:
                time.sleep(5)
                continue
            return 'err', f'HTTP {e.code}: {msg}'
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < 3:
                time.sleep(5)
                continue
            return 'err', str(e)
    return 'err', 'failed after 3 attempts'


def upload(work, args):
    if not args.album or not args.ticket:
        sys.exit('--upload requires --album TOKEN and --ticket TICKET')
    manifest = sync(work, quiet_if_unchanged=True)
    items = manifest.get('items') or []
    if not items:
        sys.exit('lupa-manifest.json has no items to upload.')
    folder_name = args.folder_name if args.folder_name else (None if args.no_folder_name else manifest.get('title'))

    brief_path = os.path.join(work, 'brief.json')
    if os.path.isfile(brief_path):
        brief = load(brief_path)
        if (brief.get('print') or {}).get('printer') == 'lupa' and not brief['print'].get('album'):
            brief['print']['album'] = args.album
            save(brief_path, brief)

    state_path = os.path.join(work, 'lupa-upload-state.json')
    raw_state = load(state_path) if os.path.isfile(state_path) else {}
    albums = raw_state.setdefault('albums', {})
    st = albums.setdefault(args.album, {'uploaded': [], 'folder_named': False})
    done_set = set(st['uploaded'])
    pending = [it for it in items if it['file'] not in done_set]

    state_lock = threading.Lock()
    cancel_event = threading.Event()
    failures = []

    def record_ok(fname):
        with state_lock:
            if fname not in done_set:
                done_set.add(fname)
                st['uploaded'].append(fname)
                save(state_path, raw_state)

    if pending and not done_set:
        first, rest = pending[0], pending[1:]
        kind, fname, msg = _post_file(args.album, args.ticket, first, cancel_event)
        if kind == 'ok':
            record_ok(fname)
            print(f'Uploaded {len(done_set)}/{len(items)}: {fname}')
        elif kind == '401':
            print(f'TICKET_EXPIRED: uploaded {len(done_set)}/{len(items)}, remaining {len(items) - len(done_set)}. '
                  'Call get_upload_link and re-run --upload with the fresh ticket.')
            sys.exit(2)
        else:
            failures.append((fname, msg))
            rest = pending[1:]
    else:
        rest = pending

    if done_set and folder_name and not st.get('folder_named'):
        fkind, fmsg = _set_folder_name(args.album, args.ticket, folder_name)
        if fkind == 'ok':
            with state_lock:
                st['folder_named'] = True
                save(state_path, raw_state)
            print(f'Set Lupa folder name: {folder_name}')
        elif fkind == '401':
            print(f'TICKET_EXPIRED: uploaded {len(done_set)}/{len(items)}, remaining {len(items) - len(done_set)}. '
                  'Call get_upload_link and re-run --upload with the fresh ticket.')
            sys.exit(2)
        else:
            print(f'Note: folder-name call returned {fmsg} (continuing upload)')

    if rest and not cancel_event.is_set():
        workers = max(1, min(args.workers, MAX_PARALLEL))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_post_file, args.album, args.ticket, it, cancel_event) for it in rest]
            for fut in as_completed(futs):
                kind, fname, msg = fut.result()
                if kind == 'ok':
                    record_ok(fname)
                    if len(done_set) % 10 == 0 or len(done_set) == len(items):
                        print(f'Uploaded {len(done_set)}/{len(items)}: {fname}')
                elif kind == '401':
                    cancel_event.set()
                elif kind != 'aborted':
                    failures.append((fname, msg))

    if cancel_event.is_set():
        rem = len(items) - len(done_set)
        print(f'TICKET_EXPIRED: uploaded {len(done_set)}/{len(items)}, remaining {rem}. '
              'Call get_upload_link and re-run --upload with the fresh ticket.')
        sys.exit(2)
    if failures:
        print(f'UPLOAD_FAILED ({len(failures)} error(s)):')
        for fn, m in failures:
            print(f'  - {fn}: {m}')
        sys.exit(1)

    print(f'UPLOAD_COMPLETE: {len(done_set)}/{len(items)} photos uploaded to album {args.album}. '
          'Next: call get_album_summary.')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work', required=True)
    ap.add_argument('--choose', action='store_true')
    ap.add_argument('--cover')
    ap.add_argument('--density')
    ap.add_argument('--direction')
    ap.add_argument('--book-type', default='REGULAR')
    ap.add_argument('--photos', type=int)
    ap.add_argument('--min-photos', type=int)
    ap.add_argument('--max-photos', type=int)
    ap.add_argument('--album')
    ap.add_argument('--pack', action='store_true')
    ap.add_argument('--check-only', action='store_true')
    ap.add_argument('--sync', action='store_true')
    ap.add_argument('--upload', action='store_true')
    ap.add_argument('--ticket')
    ap.add_argument('--folder-name')
    ap.add_argument('--no-folder-name', action='store_true')
    ap.add_argument('--workers', type=int, default=MAX_PARALLEL)
    a = ap.parse_args()

    if sum(bool(x) for x in (a.choose, a.pack, a.sync, a.upload)) != 1:
        sys.exit('Specify exactly one action: --choose, --pack, --sync, or --upload')
    work = os.path.abspath(a.work)
    if a.choose:
        choose(work, a)
    elif a.pack:
        pack(work, a.check_only)
    elif a.sync:
        sync(work)
    else:
        upload(work, a)


if __name__ == '__main__':
    main()
