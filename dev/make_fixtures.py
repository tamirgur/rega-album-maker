#!/usr/bin/env python3
"""Make the synthetic photo folders used by the evals (no real photos, no people).

    python dev/make_fixtures.py

Writes the files/ folder of three eval cases. Each picture is drawn from shapes, with real EXIF dates, GPS and camera
names, plus the cases the skill must handle:
- hebrew-trip-book: a near-duplicate burst, a blurred and a dark shot, a WhatsApp file, a Pixel file named in UTC,
  a photo outside the dates and a non-photo file;
- english-party-qr: a party, and a screenshot;
- mixed-sources-book: two folders (a phone and WhatsApp), hidden and trashed files, a RAW file, a Live Photo, a
  copy of a photo sent on WhatsApp, a sticker, a dense key moment of bursts, a night out, a bright beach with one
  overexposed frame, a panorama, a video and a move between places.
"""
import math
import os
import random
import shutil

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
from PIL.TiffImagePlugin import IFDRational

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVALS = os.path.join(ROOT, 'skills', 'rega-album-maker', 'evals')
W, H = 2000, 1500


def dms(v):
    v = abs(v)
    d = int(v)
    m = int((v - d) * 60)
    s = (v - d - m / 60) * 3600
    return (IFDRational(d), IFDRational(m), IFDRational(int(s * 100), 100))


def save(im, path, when=None, gps=None, make='Canon', model='EOS R6'):
    ex = Image.Exif()
    if make:
        ex[0x010F], ex[0x0110] = make, model
    if when:
        ex.get_ifd(0x8769)[0x9003] = when
    if gps:
        g = ex.get_ifd(0x8825)
        g[1], g[2], g[3], g[4] = 'N' if gps[0] >= 0 else 'S', dms(gps[0]), 'E' if gps[1] >= 0 else 'W', dms(gps[1])
    im.save(path, quality=82, exif=ex.tobytes())


def landscape(rng, portrait=False):
    w, h = (H, W) if portrait else (W, H)
    top, bot = [rng.randint(90, 200) for _ in range(3)], [rng.randint(170, 240) for _ in range(3)]
    im = Image.new('RGB', (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)))
    sx = w * rng.uniform(.1, .8)
    d.ellipse([sx, h * .12, sx + w * .1, h * .12 + w * .1], fill=(250, 235, 190))
    for k in range(3):
        base = h * (0.45 + 0.15 * k)
        amp, freq, ph = h * rng.uniform(.04, .12), rng.uniform(1, 4), rng.uniform(0, 6)
        col = tuple(rng.randint(40, 140) for _ in range(3))
        pts = [(x, base + amp * math.sin(freq * x / w * 6.28 + ph)) for x in range(0, w + 40, 40)]
        d.polygon(pts + [(w, h), (0, h)], fill=col)
    return im


def party(rng):
    im = Image.new('RGB', (W, H), tuple(rng.randint(200, 250) for _ in range(3)))
    d = ImageDraw.Draw(im)
    for _ in range(rng.randint(4, 9)):
        x, y, r = rng.randint(100, W - 100), rng.randint(80, H // 2), rng.randint(60, 130)
        d.line([(x, y + r), (x + rng.randint(-40, 40), y + r + 300)], fill=(120, 120, 120), width=4)
        d.ellipse([x - r, y - r * 1.2, x + r, y + r], fill=tuple(rng.randint(60, 255) for _ in range(3)))
    d.rectangle([0, H * .72, W, H], fill=(150, 110, 80))
    cx = rng.randint(500, 1500)
    d.rectangle([cx - 260, H * .58, cx + 260, H * .73], fill=(250, 240, 230))
    d.rectangle([cx - 260, H * .58, cx + 260, H * .61], fill=(230, 120, 150))
    for i in range(5):
        x = cx - 160 + i * 80
        d.rectangle([x - 8, H * .52, x + 8, H * .58], fill=(120, 170, 230))
        d.ellipse([x - 10, H * .49, x + 10, H * .525], fill=(255, 190, 60))
    return im


def trip(out):
    rng = random.Random(7)
    places = {'rome': (41.8902, 12.4922), 'trevi': (41.9009, 12.4833), 'florence': (43.7731, 11.2560),
              'pisa': (43.7230, 10.3966), 'venice': (45.4340, 12.3388)}
    plan = [('2024:07:10', ['rome'] * 4 + ['trevi'] * 4), ('2024:07:11', ['florence'] * 4 + ['pisa'] * 2),
            ('2024:07:12', ['venice'] * 6)]
    n = 0
    for day, pl in plan:
        for i, p in enumerate(pl):
            n += 1
            im = landscape(rng, portrait=(n % 5 == 0))
            when = f'{day} {9 + i:02d}:{rng.randint(0, 59):02d}:00'
            lat, lon = places[p]
            gps = (lat + rng.uniform(-.002, .002), lon + rng.uniform(-.002, .002))
            name = f'IMG_{4000 + n}.JPG'
            save(im, os.path.join(out, name), when, gps, 'Apple', 'iPhone 13')
            if day == '2024:07:10' and i == 1:
                save(ImageEnhance.Brightness(im).enhance(1.04), os.path.join(out, f'IMG_{4000 + n}_burst.JPG'), when[:-2] + '08', gps, 'Apple', 'iPhone 13')
            if day == '2024:07:10' and i == 3:
                save(im.filter(ImageFilter.GaussianBlur(28)), os.path.join(out, f'IMG_{4000 + n}_blur.JPG'), when[:-5] + '59:40', gps, 'Apple', 'iPhone 13')
            if day == '2024:07:11' and i == 2:
                save(ImageEnhance.Brightness(im).enhance(.07), os.path.join(out, f'IMG_{4000 + n}_dark.JPG'), when[:-2] + '40', gps, 'Apple', 'iPhone 13')
    landscape(rng).save(os.path.join(out, 'IMG-20240711-WA0003.jpg'), quality=75)  # WhatsApp: no EXIF
    save(landscape(rng), os.path.join(out, 'PXL_20240712_093015123.jpg'), None, places['venice'], 'Google', 'Pixel 7')
    save(landscape(rng), os.path.join(out, 'IMG_3001.JPG'), '2024:06:01 09:00:00', places['rome'], 'Apple', 'iPhone 13')
    with open(os.path.join(out, 'packing list.txt'), 'w') as f:
        f.write('not a photo\n')


def birthday(out):
    rng = random.Random(11)
    for i in range(14):
        t = 16 * 60 + i * 11 + rng.randint(0, 6)
        save(party(rng), os.path.join(out, f'DSC0{5100 + i}.JPG'), f'2025:03:14 {t // 60:02d}:{t % 60:02d}:00', None, 'Sony', 'ZV-1')
    shot = Image.new('RGB', (1080, 2400), (245, 245, 245))
    d = ImageDraw.Draw(shot)
    for k in range(9):
        d.rectangle([60, 200 + k * 230, 1020, 380 + k * 230], fill=(220, 225, 235))
    shot.save(os.path.join(out, 'Screenshot_20250314-170212.png'))


def bright(rng):
    """A white beach under a pale sky: bright on purpose."""
    im = Image.new('RGB', (1600, 1200))
    d = ImageDraw.Draw(im)
    for y in range(1200):
        t = y / 1200
        d.line([(0, y), (1600, y)], fill=(int(236 - 6 * t), int(238 - 10 * t), int(242 - 22 * t)))
    for _ in range(rng.randint(3, 6)):
        x = rng.randint(100, 1500)
        d.polygon([(x - 90, 640), (x + 90, 640), (x, 560)], fill=tuple(rng.randint(150, 220) for _ in range(3)))
        d.line([(x, 640), (x, 760)], fill=(170, 170, 170), width=5)
    return im


def mixed(out):
    import subprocess
    rng = random.Random(23)
    phone, wa = os.path.join(out, 'phone'), os.path.join(out, 'WhatsApp Images')
    os.makedirs(phone)
    os.makedirs(wa)
    town, village, halki, beach = (37.1050, 25.3760), (37.0710, 25.5200), (37.0610, 25.4800), (37.0400, 25.3600)
    n = [6000]

    def shot(im, when, gps, name=None, size=(1600, 1200)):
        n[0] += 1
        path = os.path.join(phone, name or f'IMG_{n[0]}.JPG')
        g = (gps[0] + rng.uniform(-.001, .001), gps[1] + rng.uniform(-.001, .001))
        save(im.resize(size) if im.size != size else im, path, when, g, 'Apple', 'iPhone 15')
        return path

    def t(day, h, m, s=0):
        return f'2025:08:{day:02d} {h:02d}:{m:02d}:{s:02d}'
    # day 1: the port, the old town, a dense moment at the beach (ten bursts of three), a night out
    for i in range(4):
        shot(landscape(rng), t(3, 10, 2 + 5 * i), town)
    old_town = [shot(landscape(rng), t(3, 11, 30 + 7 * i), town) for i in range(3)]
    for b in range(10):
        im = landscape(rng)
        for k, f in enumerate((1.0, 1.03, 0.97)):
            p = shot(ImageEnhance.Brightness(im).enhance(f), t(3, 14, b, 2 * k + 5), beach)
            if b == 4 and k == 0:
                live = os.path.splitext(p)[0] + '.MOV'  # the moving part of a Live Photo
                subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-loop', '1', '-i', p, '-t', '3', '-r', '15',
                                '-vf', 'scale=640:-2', '-pix_fmt', 'yuv420p', live], check=True)
    for i in range(8):
        shot(ImageEnhance.Brightness(landscape(rng)).enhance(.2), t(3, 21, 5 * i), town)
    shot(ImageEnhance.Brightness(landscape(rng)).enhance(.03), t(3, 21, 41), town)  # taken in a pocket
    # day 2: a mountain village with a panorama, then lunch in another village with a video
    for i in range(5):
        shot(landscape(rng), t(4, 9, 6 * i), village)
    shot(landscape(rng).resize((4000, 1000)), t(4, 9, 31), village, size=(4000, 1000))
    for i in range(6):
        shot(landscape(rng), t(4, 13, 3 * i), halki)
    vid = os.path.join(phone, 'VID_20250804_131000.mp4')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=15',
                    '-t', '12', '-pix_fmt', 'yuv420p', vid], check=True)
    # day 3: a bright beach with one overexposed frame, then the sunset
    for i in range(6):
        shot(bright(rng), t(5, 11, 4 * i), beach)
    shot(ImageEnhance.Brightness(bright(rng)).enhance(1.25), t(5, 11, 26), beach)
    for i in range(3):
        shot(landscape(rng), t(5, 18, 10 * i), beach)
    # WhatsApp: a copy of an old-town photo, sent the next day; a friend's photo; a sticker
    with Image.open(old_town[1]) as im:
        im.resize((1280, 960)).save(os.path.join(wa, 'IMG-20250804-WA0007.jpg'), quality=70)
    landscape(rng).resize((1600, 1200)).save(os.path.join(wa, 'IMG-20250805-WA0011.jpg'), quality=72)
    Image.new('RGB', (512, 512), (250, 200, 60)).save(os.path.join(wa, 'STK-20250805-WA0002.webp'))
    # what a folder copied from a phone or a Mac also holds
    with open(os.path.join(phone, '._IMG_6001.JPG'), 'wb') as f:
        f.write(b'\x00\x05\x16\x07' + bytes(4092))  # a macOS resource-fork file, not a photo
    shot(landscape(rng), t(3, 12, 0), town, name='.trashed-1754300000-IMG_6999.JPG')  # deleted on the phone
    with open(os.path.join(phone, 'IMG_6300.CR2'), 'wb') as f:
        f.write(bytes(2048))


def count(out):
    files = [os.path.join(dp, f) for dp, _, fs in os.walk(out) for f in fs]
    return len(files), sum(os.path.getsize(f) for f in files)


for case, folder, make in (('hebrew-trip-book', 'photos', trip), ('english-party-qr', 'party', birthday),
                           ('mixed-sources-book', 'naxos', mixed)):
    out = os.path.join(EVALS, case, 'files', folder)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    make(out)
    k, size = count(out)
    print(f'{out}: {k} files, {size / 1e6:.1f} MB')
