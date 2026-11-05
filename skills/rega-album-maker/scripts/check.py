#!/usr/bin/env python3
"""Check the finished PDF the way a printer would, and make page previews to look at.

    python check.py --work WORK [--pdf book.pdf] [--previews] [--spreads 1,4,7]

Checks: the page count (inside pages even, the count the user chose, else at least the printer minimum), the page size, embedded fonts, the
resolution of every photo as printed, the design rules (faces, spine, pacing; see references/design.md), and that every
QR code scans from the page itself.
--previews writes WORK/previews/spread-*.png in reading order (right to left for Hebrew books), to look at.
Writes WORK/check.md. Needs PyMuPDF (pip install pymupdf); zxing-cpp for the QR check.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load  # noqa: E402

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None


def qr_texts(page, dpi):
    import zxingcpp
    from PIL import Image
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    found = {r.text for r in zxingcpp.read_barcodes(img)}
    if not found:  # small codes on a big page: try each quarter
        w, h = img.size
        for box in ((0, 0, w // 2 + 50, h // 2 + 50), (w // 2 - 50, 0, w, h // 2 + 50),
                    (0, h // 2 - 50, w // 2 + 50, h), (w // 2 - 50, h // 2 - 50, w, h)):
            found |= {r.text for r in zxingcpp.read_barcodes(img.crop(box))}
    return found


def previews(doc, book, work, which):
    from PIL import Image
    out = os.path.join(work, 'previews')
    os.makedirs(out, exist_ok=True)
    n = doc.page_count
    rows = [[0], [None, 1]] + [[i, i + 1] if i + 1 < n - 1 else [i, None] for i in range(2, n - 1, 2)] + [[n - 1]]
    paths = []
    for k, row in enumerate(rows):
        if which and k not in which:
            continue
        imgs = []
        for i in row:
            if i is None:
                imgs.append(None)
                continue
            pix = doc[i].get_pixmap(dpi=48)
            imgs.append(Image.frombytes('RGB', (pix.width, pix.height), pix.samples))
        w, h = max(im.width for im in imgs if im), max(im.height for im in imgs if im)
        if book.get('dir') == 'rtl':
            imgs = imgs[::-1]  # the first page of a right-to-left spread sits on the right
        sheet = Image.new('RGB', (w * len(imgs) + 4 * (len(imgs) - 1), h), (200, 196, 190))
        for j, im in enumerate(imgs):
            if im:
                sheet.paste(im, (j * (w + 4), 0))
        p = os.path.join(out, f'spread-{k:02d}.png')
        sheet.save(p)
        paths.append(p)
    return paths


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work', required=True)
    ap.add_argument('--pdf', default='book.pdf')
    ap.add_argument('--previews', action='store_true')
    ap.add_argument('--spreads', help='only these spread numbers (0 = cover)')
    a = ap.parse_args()
    if pymupdf is None:
        sys.exit('The final check needs PyMuPDF: pip install pymupdf')
    book = load(os.path.join(a.work, 'book.json'))
    pdf = a.pdf if os.path.isabs(a.pdf) else os.path.join(a.work, a.pdf)
    doc = pymupdf.open(pdf)

    if a.previews:
        which = {int(x) for x in a.spreads.split(',')} if a.spreads else None
        for p in previews(doc, book, a.work, which):
            print(p)
        return

    bad, notes = [], []
    n, inner = doc.page_count, doc.page_count - 2
    if n != len(book['pages']):
        bad.append(f'{n} pages in the PDF, {len(book["pages"])} in book.json')
    if inner % 2:
        bad.append(f'{inner} inside pages: printers need an even number')
    if book.get('goal_pages') and inner != book['goal_pages']:
        bad.append(f'{inner} inside pages: the user chose {book["goal_pages"]} (brief.json)')
    elif book.get('min_pages') and inner < book['min_pages'] and not book.get('goal_pages'):
        bad.append(f'{inner} inside pages: the minimum for this size is {book["min_pages"]}')
    b = book.get('bleed', 0)
    want = ((book['w'] + 2 * b) / 25.4 * 72, (book['h'] + 2 * b) / 25.4 * 72)
    for i, page in enumerate(doc):
        r = page.rect
        if abs(r.width - want[0]) > 2 or abs(r.height - want[1]) > 2:
            bad.append(f'PDF page {i + 1} is {r.width / 72 * 25.4:.1f} x {r.height / 72 * 25.4:.1f} mm, '
                       f'expected {book["w"] + 2 * b:g} x {book["h"] + 2 * b:g}')
            break
    fonts = {f[3] for i in range(n) for f in doc.get_page_fonts(i)}
    unembedded = {f[3] for i in range(n) for f in doc.get_page_fonts(i) if f[1] in ('n/a', '')}
    if unembedded:
        bad.append('fonts not embedded: ' + ', '.join(sorted(unembedded)))
    low = []
    for i, page in enumerate(doc):
        for info in page.get_image_info(xrefs=True):
            x0, y0, x1, y1 = info['bbox']
            if x1 - x0 < 30:
                continue
            xr = info.get('xref') or 0
            if not xr or 'DCT' not in (doc.xref_get_key(xr, 'Filter')[1] or ''):
                continue   # a shadow, a tape or a paper texture drawn by the browser, not a photo
            dpi = info['width'] / ((x1 - x0) / 72)
            if dpi < 200:
                low.append((dpi, i + 1))
    for dpi, pg in sorted(low)[:20]:
        (bad if dpi < 150 else notes).append(f'a photo on PDF page {pg} prints at {dpi:.0f} DPI')
    for r in book.get('rules', []):   # the design rules layout.py checked
        if not r['ok']:
            bad.append(f'design rule: {r["rule"]}' + (f' ({r["note"]})' if r['note'] else ''))
    qr_pages = [i for i, p in enumerate(book['pages']) if p.get('qr') or any(it.get('type') == 'qr' for it in p.get('items', []))]
    try:
        import zxingcpp  # noqa: F401
        for i in qr_pages:
            p = book['pages'][i]
            url = (p.get('qr') or next(it for it in p['items'] if it.get('type') == 'qr'))['url']
            if url not in qr_texts(doc[i], 300):
                bad.append(f'the QR code on PDF page {i + 1} does not scan as {url}')
    except ImportError:
        if qr_pages:
            notes.append('QR codes not checked: pip install zxing-cpp')

    lines = [f'# Check: {os.path.basename(pdf)}', '',
             f'- {n} pages: front cover, {inner} inside pages, back cover; {book["w"]:g} x {book["h"]:g} mm'
             + (f' + {b:g} mm bleed' if b else ''),
             f'- Fonts: {", ".join(sorted(fonts)) or "none"}',
             f'- QR codes: {len(qr_pages)}', '']
    lines += [f'- PROBLEM: {x}' for x in bad] + [f'- Note: {x}' for x in notes]
    lines.append('' if bad else 'Ready for the printer. Order one copy first, as a proof.')
    with open(os.path.join(a.work, 'check.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
