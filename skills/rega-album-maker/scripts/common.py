"""Shared helpers for the Rega album maker scripts (Python 3.9+, Pillow).

Nothing here ever writes to the user's photo folders: every output goes to the work folder.
"""
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(SKILL_DIR, 'assets')
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp'}
VIDEO_EXT = {'.mp4', '.mov', '.m4v', '.3gp'}
RAW_EXT = {'.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2', '.pef', '.srw'}
# folders never scanned: hidden ones, NAS indexes (@eaDir), the recycle bin ($RECYCLE.BIN), zip leftovers
SKIP_DIR = re.compile(r'^(\.|@|\$|__MACOSX$|System Volume Information$)', re.I)
DAY_START = 4  # a "day" runs 04:00 to 04:00, so late-night photos stay with their evening
PER_PAGE = 1.9  # photos per photo page on average: the default rhythm, with room for pages that hold one photo

# Book sizes in mm, with the usual minimum number of inside pages. Check the printer's own numbers.
SIZES = {
    'square-21': (210, 210, 24),
    'square-30': (300, 300, 24),
    'a5-portrait': (148, 210, 20),
    'a5-landscape': (210, 148, 20),
    'a4-portrait': (210, 297, 24),
    'a4-landscape': (297, 210, 24),
}
# the sizes offered: square and portrait pages pass the design rules in every style; landscape pages left too much
# empty space in most styles, so they are kept only for books made with an earlier version
OFFERED = ['square-21', 'square-30', 'a4-portrait', 'a5-portrait']


def shape_ok(w, h):
    """A page shape the styles are made for: square or portrait."""
    return h >= w * 0.98
TINTS = ['sand', 'linen', 'rose', 'mist', 'sage']
TEXT = {
    'he': {'day': 'יום', 'clip': 'לצפייה בסרטון', 'route': 'המסלול', 'days': '{n} ימים', 'one_day': 'יום אחד',
           'places': '{n} מקומות', 'one_place': 'מקום אחד',
           'weekdays': ['שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת', 'ראשון'],
           'months': ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני', 'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר',
                      'נובמבר', 'דצמבר']},
    'en': {'day': 'Day', 'clip': 'Watch the clip', 'route': 'Our route', 'days': '{n} days', 'one_day': '1 day',
           'places': '{n} places', 'one_place': '1 place',
           'weekdays': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
           'months': ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
                      'October', 'November', 'December']},
}
MONTHS_EN = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()
RTL_LANGS = {'he', 'ar', 'fa', 'ur', 'yi'}   # languages written right to left: the book opens from the right
# where the books are kept: <the place the user chose>/<ALBUMS>/<book>/ holds the finished files, and its
# <WORK> subfolder the scan, thumbnails and sheets
ALBUMS = {'he': 'אלבומים', 'en': 'Albums'}
WORK = {'he': 'קבצי עבודה', 'en': 'work files'}
_R = '֐-׿؀-ۿיִ-ﭏ'
RTL_CHARS = re.compile(f'[{_R}]')
_TOK = re.compile('([' + _R + ']+)|([A-Za-z0-9À-ɏ]+(?:[.:/–-][A-Za-z0-9]+)*)|([^A-Za-z0-9À-ɏ' + _R + ']+)')


def album_dir(work):
    """The book's own folder: the parent of its work folder, where the finished files go."""
    work = os.path.abspath(work)
    return os.path.dirname(work) if os.path.basename(work) in WORK.values() else work


def visual(s):
    """A line for Pillow, which draws characters in the order given: right-to-left words are reordered so they
    read correctly on contact sheets (a simple bidi; python-bidi is used when installed)."""
    s = (s or '').replace('\u2066', '').replace('\u2069', '')
    if not RTL_CHARS.search(s):
        return s
    try:
        from bidi.algorithm import get_display
        return get_display(s)
    except ImportError:
        pass
    toks = [('r' if m.group(1) else 'l' if m.group(2) else 'n', m.group(0)) for m in _TOK.finditer(s)]
    strong = [k for k, _ in toks if k != 'n']
    base = strong[0] if strong else 'l'
    kinds = []
    for i, (k, t) in enumerate(toks):   # a neutral between two runs of one direction takes it, else the line's
        if k == 'n':
            prev = next((x for x, _ in reversed(toks[:i]) if x != 'n'), base)
            nxt = next((x for x, _ in toks[i + 1:] if x != 'n'), base)
            k = prev if prev == nxt else base
        kinds.append(k)
    runs = []
    for k, (_, t) in zip(kinds, toks):
        if runs and runs[-1][0] == k:
            runs[-1][1] += t
        else:
            runs.append([k, t])
    out = [t[::-1] if k == 'r' else t for k, t in runs]
    return ''.join(reversed(out)) if base == 'r' else ''.join(out)


def is_rtl(lang):
    return (lang or '').split('-')[0].lower() in RTL_LANGS


def words(lang):
    """The words the book writes by itself. Hebrew and English are built in. Any other language gets numbers for
    dates and no weekday; write its chapter tags (deck) and route title yourself in selection.json."""
    return TEXT.get(lang) or dict(TEXT['en'], weekdays=None, months=None, generic=True)

for _s in (sys.stdout, sys.stderr):  # Windows consoles default to a code page without Hebrew
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

try:  # iPhone HEIC photos, if pillow-heif is installed
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF = True
except ImportError:
    HEIF = False


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def wpath(work, *parts):
    return os.path.join(work, *parts)


def parse_time(s):
    return datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S') if s else None


def fmt_time(t):
    return t.strftime('%Y-%m-%d %H:%M:%S')


def day_of(t):
    return (t - timedelta(hours=DAY_START)).date()


def fmt_date(d, lang, year=False):
    if lang == 'en':
        return f'{d.day} {MONTHS_EN[d.month - 1]}' + (f' {d.year}' if year else '')
    return f'{d.day}.{d.month}' + (f'.{d.year}' if year else '')   # Hebrew and every other language: numbers


def fmt_long(d, lang):
    """A date written out as in a sentence: 'יום שלישי, 31 בינואר 2023' or 'Tuesday, 31 January 2023'."""
    t = words(lang)
    if not t.get('weekdays'):
        return fmt_date(d, lang, True)
    if lang == 'he':
        return f'יום {t["weekdays"][d.weekday()]}, {d.day} ב{t["months"][d.month - 1]} {d.year}'
    return f'{t["weekdays"][d.weekday()]}, {d.day} {t["months"][d.month - 1]} {d.year}'


def fmt_range(d0, d1, lang):
    if d0 == d1:
        return fmt_date(d0, lang, True)
    if is_rtl(lang):
        return f'\u2066{fmt_date(d0, lang, d0.year != d1.year)}–{fmt_date(d1, lang, True)}\u2069'
    return f'{fmt_date(d0, lang, d0.year != d1.year)} – {fmt_date(d1, lang, True)}'


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def hamming(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count('1')


def median(xs):
    s = sorted(xs)
    return s[len(s) // 2] if s else 0


# ---------------------------------------------------------------- how many photos a book of N pages holds

def base_quota(cands):
    """The photos to choose for a day with this many candidates when no page count is set: 1 to 12."""
    return max(1, min(12, round(1.6 * math.sqrt(cands) + 1))) if cands else 0


def quotas(cands, total=None):
    """One quota per day. With a total, the quotas are scaled to it, never above a day's candidates."""
    base = [base_quota(c) for c in cands]
    if not total or not sum(base):
        return base
    raw = [b * total / sum(base) for b in base]
    q = [min(c, int(x)) for x, c in zip(raw, cands)]
    for i in sorted(range(len(q)), key=lambda i: raw[i] - int(raw[i]), reverse=True):  # largest remainders first
        if sum(q) >= total:
            break
        if q[i] < cands[i]:
            q[i] += 1
    while sum(q) < total and any(x < c for x, c in zip(q, cands)):  # a day without enough candidates gives its share away
        i = max((i for i in range(len(q)) if q[i] < cands[i]), key=lambda i: cands[i] - q[i])
        q[i] += 1
    return [max(1, x) if c else 0 for x, c in zip(q, cands)]


def photos_for(pages, chapters, route, per_page=PER_PAGE):
    """About how many photos fill this many inside pages: one on each chapter opener, per_page on the rest (the
    structure sets it: a journal holds more photos a page than an album)."""
    return chapters + max(0, round((pages - chapters - (1 if route else 0)) * per_page))


def pages_for(photos, chapters, route, per_page=PER_PAGE):
    return chapters + (1 if route else 0) + math.ceil(max(0, photos - chapters) / per_page)


def even_up(n):
    return n + (n % 2)


# ---------------------------------------------------------------- dates from metadata and file names

NAME_PATTERNS = [  # (regex, kind): 'whatsapp' = date received, 'utc' = UTC time, 'local' = local time
    (re.compile(r'(?:IMG|VID|STK)-(\d{4})(\d{2})(\d{2})-WA\d+', re.I), 'whatsapp'),
    (re.compile(r'WhatsApp (?:Image|Video) (\d{4})-(\d{2})-(\d{2}) at (\d{1,2})\.(\d{2})\.(\d{2})', re.I), 'whatsapp'),
    (re.compile(r'PXL_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})', re.I), 'utc'),
    (re.compile(r'(?<!\d)(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})(?!\d)'), 'local'),
    (re.compile(r'(?<!\d)(\d{4})-(\d{2})-(\d{2})[ _](?:at )?(\d{2})[.:\-](\d{2})[.:\-](\d{2})'), 'local'),
]
SCREENSHOT = re.compile(r'screenshot|screen shot|צילום מסך|scrnshot', re.I)


EPOCH_MS = re.compile(r'^(1[3-9]\d{11})(?:[_-]\d+)?\.\w+$')   # 1713795196960.jpg: Unix time in ms (Android saves, Telegram)


def name_date(name):
    """A date from the file name: (datetime, kind) or (None, None)."""
    m = EPOCH_MS.match(name)
    if m:   # milliseconds since 1970: the moment the file was saved (a download, a share), like a WhatsApp date
        return datetime(1970, 1, 1) + timedelta(milliseconds=int(m.group(1))), 'whatsapp'
    for rx, kind in NAME_PATTERNS:
        m = rx.search(name)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        try:
            t = datetime(*g[:3], *(g[3:6] if len(g) >= 6 else (12, 0, 0)))
        except ValueError:
            continue
        if 1990 < t.year < 2100:
            return t, kind
    return None, None


def _deg(v, ref):
    try:
        d, m, s = (float(x) for x in v)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    x = d + m / 60 + s / 3600
    return -x if ref in ('S', 'W', b'S', b'W') else x


def exif_info(im):
    """Date taken, offset, GPS and camera from an opened (not yet transposed) PIL image."""
    out = {}
    try:
        ex = im.getexif()
    except Exception:
        return out
    sub = ex.get_ifd(0x8769)
    dt = sub.get(0x9003) or sub.get(0x9004) or ex.get(0x0132)
    if isinstance(dt, str) and re.match(r'\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}', dt) and not dt.startswith('0000'):
        out['exif_time'] = dt[:10].replace(':', '-') + dt[10:19]
        off = sub.get(0x9011)
        if isinstance(off, str) and re.match(r'[+-]\d{2}:\d{2}', off):
            out['offset'] = int(off[:3]) + (1 if off[0] == '+' else -1) * int(off[4:6]) / 60
    gps = ex.get_ifd(0x8825)
    if gps:
        lat, lon = _deg(gps.get(2), gps.get(1)), _deg(gps.get(4), gps.get(3))
        if lat is not None and lon is not None and (abs(lat) > 1e-6 or abs(lon) > 1e-6):
            out['lat'], out['lon'] = round(lat, 6), round(lon, 6)
    for tag, k in ((0x010F, 'make'), (0x0110, 'model')):
        v = ex.get(tag)
        if isinstance(v, str) and v.strip('\x00 '):
            out[k] = v.strip('\x00 ')
    out['orientation'] = ex.get(0x0112, 1)
    return out


def sidecar_info(path):
    """Google Takeout writes a JSON next to each photo with the time taken (UTC) and GPS."""
    for cand in (path + '.json', path + '.supplemental-metadata.json', os.path.splitext(path)[0] + '.json'):
        if os.path.isfile(cand):
            try:
                d = load(cand)
            except Exception:
                continue
            out = {}
            ts = (d.get('photoTakenTime') or {}).get('timestamp')
            if ts:
                out['takeout_utc'] = fmt_time(datetime(1970, 1, 1) + timedelta(seconds=int(ts)))
            g = d.get('geoData') or {}
            if g.get('latitude') or g.get('longitude'):
                out['lat'], out['lon'] = round(g['latitude'], 6), round(g['longitude'], 6)
            return out
    return {}


# ---------------------------------------------------------------- external tools

def tool(name):
    return shutil.which(name)


def ffprobe(path):
    exe = tool('ffprobe')
    if not exe:
        return None
    r = subprocess.run([exe, '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', path],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    try:
        return json.loads(r.stdout or '{}')
    except ValueError:
        return None


def video_meta(path):
    """Duration, size, time, place and HDR of a video. Empty when ffprobe is missing."""
    meta = ffprobe(path)
    if not meta:
        return {}
    fmt, out = meta.get('format') or {}, {}
    tags = {k.lower(): v for k, v in (fmt.get('tags') or {}).items()}
    v = next((s for s in meta.get('streams', []) if s.get('codec_type') == 'video'), {})
    tags.update({k.lower(): x for k, x in (v.get('tags') or {}).items() if k.lower() not in tags})
    out['duration'] = round(float(fmt.get('duration') or v.get('duration') or 0), 2)
    out['w'], out['h'] = v.get('width'), v.get('height')
    rot = abs(int(float((v.get('tags') or {}).get('rotate', 0) or 0)))
    for sd in v.get('side_data_list') or []:
        if 'rotation' in sd:
            rot = abs(int(sd['rotation']))
    if rot in (90, 270) and out['w']:
        out['w'], out['h'] = out['h'], out['w']
    out['hdr'] = v.get('color_transfer') in ('smpte2084', 'arib-std-b67')
    local = tags.get('com.apple.quicktime.creationdate')  # iPhone: local time with offset
    m = re.match(r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})', local or '')
    if m:
        out['video_local'] = f'{m[1]} {m[2]}'
    ct = tags.get('creation_time')
    m = re.match(r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})', ct or '')
    if m and not m[1].startswith('1970'):
        out['video_utc'] = f'{m[1]} {m[2]}'
    loc = tags.get('com.apple.quicktime.location.iso6709') or tags.get('location') or tags.get('location-eng')
    m = re.match(r'([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)', loc or '')
    if m and (abs(float(m[1])) > 1e-6 or abs(float(m[2])) > 1e-6):
        out['lat'], out['lon'] = float(m[1]), float(m[2])
    return out


def find_browser():
    """Chrome, Edge or Chromium, for printing HTML to PDF. CHROME_PATH overrides."""
    cands = [os.environ.get('CHROME_PATH')]
    cands += [shutil.which(n) for n in ('google-chrome', 'google-chrome-stable', 'chrome', 'chromium',
                                        'chromium-browser', 'msedge', 'microsoft-edge')]
    if sys.platform == 'win32':
        for base in (os.environ.get('PROGRAMFILES'), os.environ.get('PROGRAMFILES(X86)'), os.environ.get('LOCALAPPDATA')):
            if base:
                cands += [os.path.join(base, 'Google', 'Chrome', 'Application', 'chrome.exe'),
                          os.path.join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe')]
    elif sys.platform == 'darwin':
        cands += ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                  '/Applications/Chromium.app/Contents/MacOS/Chromium']
    else:  # Linux, including the Cowork and claude.ai sandboxes, which carry Playwright's Chromium
        cands.append('/opt/pw-browsers/chromium')
        for base in (os.environ.get('PLAYWRIGHT_BROWSERS_PATH'), '/opt/pw-browsers', os.path.expanduser('~/.cache/ms-playwright')):
            if base:
                cands += sorted(glob.glob(os.path.join(base, 'chromium-*', 'chrome-linux*', 'chrome')), reverse=True)
    return next((c for c in cands if c and os.path.isfile(c)), None)


def font_path(weight):
    names = {200: 'ExtraLight', 300: 'Light', 400: 'Regular', 600: 'SemiBold'}
    return os.path.join(ASSETS, 'fonts', f'Assistant-{names[weight]}.ttf')


def pil_font(size, weight=400):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(font_path(weight), size)
    except OSError:
        return ImageFont.load_default()
