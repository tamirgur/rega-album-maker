#!/usr/bin/env python3
"""Printing at Prodigi: choose a product, then pack the file and the order guide.

    python printer.py --list [--type hardcover|softcover|layflat|magazine]
    python printer.py --work WORK --choose SKU [--copies 1] [--country IL]
    python printer.py --work WORK --pack

--choose writes the product into brief.json: its exact size, its page range and the part of the fold the binding
         hides. Do it at stage 4, before the layout, because the product shapes the pages.
--pack   after render.py: checks the PDF against the product and writes WORK/<print folder>/ with the file to upload
         (mirrored for a Hebrew book, since Prodigi binds on the left), the spine values and the order guide in the
         book's language.

Prodigi is here because it ships to Israel and takes a ready PDF. It is not a recommendation: the skill takes no
responsibility for the print, the price, the delivery or the order. The user places the order and pays in their own
Prodigi account; the skill never sees an address, a card or an API key.
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ASSETS, album_dir, even_up, load, save, shape_ok  # noqa: E402

CAT = os.path.join(ASSETS, 'printers', 'prodigi.json')
TYPE_HE = {'hardcover': 'כריכה קשה', 'softcover': 'כריכה רכה', 'layflat': 'לייפלט (נפתח שטוח)', 'magazine': 'מגזין'}


def catalogue():
    return load(CAT)


def variant(sku):
    c = catalogue()
    v = next((x for x in c['variants'] if x['sku'].upper() == sku.upper()), None)
    if v is None:
        sys.exit(f'Unknown product {sku}. See: python printer.py --list')
    p = dict(c['products'][v['type']], **v)
    return c, p


def list_products(kind=None):
    c = catalogue()
    print(f'Prodigi photo books and magazines (catalogue of {c["captured"]}; prices in USD before extra pages and shipping)')
    for t, info in c['products'].items():
        if kind and t != kind:
            continue
        lo, hi = info['pages']
        print(f'\n{t}: {lo}-{hi} pages, {info["binding"]} binding, hides about {info.get("gutter_hidden_mm", 6)} mm at the fold'
              + (f'; {info["pages_note"]}' if info.get('pages_note') else ''))
        for v in c['variants']:
            if v['type'] == t and shape_ok(v['w_mm'], v['h_mm']):   # square and portrait only
                print(f'  {v["sku"]:26s} {v["w_mm"]:g} x {v["h_mm"]:g} mm  {v["paper"]:26s} from ${v["price_usd"]:.2f}')
    print('\n' + c['price_note'])
    print('Not a recommendation: ' + c['disclaimer'])


def choose(work, sku, copies, country):
    path = os.path.join(work, 'brief.json')
    brief = load(path)
    c, p = variant(sku)
    if not shape_ok(p['w_mm'], p['h_mm']):
        sys.exit(f'{p["sku"]} is a landscape book. The styles are made for square and portrait pages: choose one of '
                 'those (python printer.py --list).')
    lo, hi = p['pages']
    if p['sku'].endswith('-G-F'):
        hi = 500
    fmt = dict(brief.get('format') or {})
    pages = fmt.get('pages')
    fmt.update({'size': f'prodigi-{p["sku"]}', 'w': p['w_mm'], 'h': p['h_mm'], 'min_pages': lo, 'max_pages': hi})
    note = ''
    if isinstance(pages, int):
        fixed = min(max(even_up(pages), lo), hi - hi % 2)
        if fixed != pages:
            note = f' The page count moved from {pages} to {fixed} to fit the product.'
            fmt['pages'] = fixed
    brief['format'] = fmt
    brief['print'] = {'printer': 'prodigi', 'sku': p['sku'], 'type': p['type'], 'w': p['w_mm'], 'h': p['h_mm'],
                      'paper': p['paper'], 'pages': [lo, hi], 'gutter_mm': p.get('gutter_hidden_mm', 6),
                      'binds': 'left', 'base_usd': p['price_usd'], 'catalogue': c['captured'],
                      'copies': copies, 'country': country, 'chosen': date.today().isoformat()}
    save(path, brief)
    print(f'Chose {p["sku"]}: {p["type"]}, {p["w_mm"]:g} x {p["h_mm"]:g} mm, {p["paper"]}, {lo}-{hi} pages, '
          f'from ${p["price_usd"]:.2f} a copy before extra pages and shipping.{note}')
    if p['type'] == 'layflat':
        print('Layflat: nothing is lost at the fold, so spreads and photos across the fold are safe.')
    else:
        print(f'{p["binding"]} binding: about {p.get("gutter_hidden_mm", 6)} mm disappear at the fold. The layout keeps '
              'faces and words out of it.')
    if p['type'] == 'magazine':
        print('Note: the magazine print guide has not been checked yet. Ask the user to look at the file rules on the '
              'product page before ordering.')
    print('Next: run brief.py --options for the page counts, then layout.py.')


def pdf_info(pdf):
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError:
            return None
    with pymupdf.open(pdf) as d:
        sizes = {(round(pg.rect.width / 72 * 25.4, 1), round(pg.rect.height / 72 * 25.4, 1)) for pg in d}
        type3 = sorted({f[3] for pg in d for f in pg.get_fonts() if f[2] == 'Type3'})
        return {'pages': d.page_count, 'sizes': sizes, 'type3': type3}


def pack(work):
    brief = load(os.path.join(work, 'brief.json'))
    pr = brief.get('print') or {}
    if pr.get('printer') != 'prodigi':
        sys.exit('No Prodigi product in brief.json. Choose one first: python printer.py --work WORK --choose SKU')
    book = load(os.path.join(work, 'book.json'))
    rtl = book.get('dir') == 'rtl'
    he = book.get('lang') == 'he'   # the guide in Hebrew; any other language gets it in English
    c, p = variant(pr['sku'])
    src = os.path.join(work, 'book.pdf')
    if rtl:   # Prodigi binds on the left: a right-to-left book goes in reverse, so it opens from the right
        src = os.path.join(work, 'book-print-left-binding.pdf')
        if not os.path.isfile(src) or os.path.getmtime(src) < os.path.getmtime(os.path.join(work, 'book.json')):
            r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'render.py'),
                                '--work', work, '--left-binding'], capture_output=True, text=True,
                               encoding='utf-8', errors='replace')  # render.py writes UTF-8; Windows reads cp1252
            if r.returncode:
                sys.exit(r.stdout + r.stderr)
    if not os.path.isfile(src):
        sys.exit('No PDF yet: run render.py first.')

    # ---- the check before uploading
    problems, notes = [], []
    info = pdf_info(src)
    n_inside = len([pg for pg in book['pages'] if pg.get('n')])
    lo, hi = pr['pages']
    if info:
        total = info['pages']
        want = (round(p['w_mm'], 1), round(p['h_mm'], 1))
        bad = [s for s in info['sizes'] if abs(s[0] - want[0]) > 0.6 or abs(s[1] - want[1]) > 0.6]
        if bad:
            problems.append(f'page size {bad[0][0]} x {bad[0][1]} mm, the product is {want[0]:g} x {want[1]:g} mm')
        if total % 2:
            problems.append(f'{total} pages in the PDF: the count must be even')
        if info['type3']:
            problems.append('fonts that would print poorly (Type3): ' + ', '.join(info['type3']))
    else:
        total = n_inside + 2
        notes.append('pymupdf is not installed, so the PDF itself was not opened: size and fonts unchecked')
    if not lo <= n_inside <= hi:
        problems.append(f'{n_inside} inside pages, the product takes {lo}-{hi}')
    rules = [r for r in book.get('rules', []) if not r['ok']]
    for r in rules:
        problems.append(f'design rule: {r["rule"]} ({r["note"]})')
    low = []
    for pg in book['pages']:
        for f in pg.get('frames', []):
            ph = book['photos'][str(f['id'])]
            dpi = ph['w'] / (f['img'][2] / 25.4)
            if dpi < 150:
                low.append(f'#{f["id"]} at {int(dpi)} DPI')
    if low:
        problems.append('photos below 150 DPI: ' + ', '.join(sorted(set(low))))

    # ---- the folder
    out = os.path.join(album_dir(work), 'להדפסה' if he else 'to-print')   # in the book's folder, beside the PDFs
    os.makedirs(out, exist_ok=True)
    title = (book.get('title') or 'book').strip()
    safe = ''.join(ch for ch in title if ch not in '\\/:*?"<>|').strip() or 'book'
    name = f'{safe} - {p["sku"]} - {total} {"עמודים" if he else "pages"}.pdf'
    shutil.copyfile(src, os.path.join(out, name))
    st = book['style']
    cover = book['pages'][0]
    bg = cover.get('bg') or st['colors']['paper']
    ink = st['colors']['ink'] if luminance(bg) > 0.5 else st['colors']['paper']
    text_ok = n_inside + 2 >= c['file_rules'].get('spine_text_min_pages', 40)
    guide = order_guide(he, p, pr, name, total, n_inside, bg, ink, text_ok, c)
    gname = 'הוראות הזמנה.md' if he else 'order-guide.md'
    with open(os.path.join(out, gname), 'w', encoding='utf-8', newline='\n') as f:
        f.write(guide)

    print(f'Print folder: {out}')
    print(f'  {name}  ({total} PDF pages: front cover, {n_inside} inside pages, back cover'
          + ('; mirrored, so the right-to-left book opens from the right' if rtl else '') + ')')
    print(f'  {gname}')
    print(f'Product: {p["sku"]}, {p["w_mm"]:g} x {p["h_mm"]:g} mm, {p["paper"]}. Spine: background {bg}, text {ink}'
          + ('' if text_ok else ', colour only (under 40 pages)') + '.')
    for x in notes:
        print('Note: ' + x)
    if problems:
        print('FIX BEFORE UPLOADING:')
        for x in problems:
            print('  - ' + x)
    else:
        print('Ready to upload: size, page count, fonts, resolution and the design rules are fine.')
    print('Before the user pays: ask for a screenshot of the order summary and check it against the guide.')


def luminance(hexc):
    if not isinstance(hexc, str) or not hexc.startswith('#') or len(hexc) < 7:
        return 0.9
    r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def order_guide(he, p, pr, name, total, inside, bg, ink, text_ok, c):
    copies, country = pr.get('copies') or 1, pr.get('country') or ''
    ex = (c.get('observed_prices') or {}).get('items') or []
    ship_he = f' · משלוח ל־{country}' if country else ''
    ship_en = f' · shipping to {country}' if country else ''
    example_he = (f'\n  לדוגמה: ספר של {ex[0]["pdf_pages"]} עמודים במק"ט {ex[0]["sku"]} עלה ${ex[0]["item_usd"]} לפני משלוח '
                  f'(אוקטובר 2026).') if ex else ''
    if he:
        spine = ('   - **טקסט:** באנגלית או במספרים בלבד, כי השדרה לא מקבלת עברית. בספר בעברית עדיף בלי טקסט: '
                 'הקובץ הפוך, ולכן טקסט על השדרה עלול לצאת הפוך ביחס לכריכה הקדמית.\n' if text_ok else
                 '   - **טקסט:** בלי. מתחת ל־40 עמודים Prodigi ממליצים על צבע בלבד.\n')
        return f"""# הזמנת הספר ב־Prodigi

> **חשוב:** Prodigi מופיע כאן כי הוא שירות הדפסה ששולח לכל העולם, כולל ישראל, ומקבל קובץ PDF מוכן. זו לא המלצה. אין לנו אחריות על ההדפסה, המחיר, המשלוח או ההזמנה. ההזמנה והתשלום נעשים אצלך, בחשבון שלך.

## מה מזמינים
- **מוצר:** {TYPE_HE.get(p['type'], p['type'])}, {p['w_mm']:g}×{p['h_mm']:g} מ"מ, {p['paper']}
- **מק"ט:** `{p['sku']}`
- **הקובץ:** `{name}` ({total} עמודים, כולל הכריכות)
- **עותקים:** {copies}{ship_he}
- **מחיר בסיס בקטלוג:** ${p['price_usd']:.2f} לעותק (נכון ל־{c['captured']}). עמודים נוספים ומשלוח מתווספים. המחיר המדויק מופיע רק במסך הסיכום.{example_he}

## מה צריך להכין
- חשבון ב־Prodigi (ההרשמה בחינם).
- כרטיס אשראי לתשלום.
- כתובת, טלפון ואימייל של מי שמקבל את הספר. את הפרטים האלה מקלידים רק באתר שלהם, לא אצלי.

## השלבים באתר
1. **Create order**, ואז בוחרים את מדינת המשלוח.
2. מחפשים את המוצר לפי המק"ט `{p['sku']}`, ואז **Add to basket**.
3. **Add pdf**, ומעלים את `{name}` מהתיקייה הזו.
4. **Spine** (השדרה):
{spine}   - **צבע רקע:** `{bg}` · **צבע טקסט:** `{ink}` · **גופן:** Brandon או Arial · **גודל:** 16px
5. **Continue**, ואז מקלידים את הכתובת ובוחרים שיטת משלוח.
6. **במסך הסיכום, לפני התשלום:** מצלמים מסך ושולחים לי. אבדוק שהמוצר, המידה, מספר העמודים, העותקים והשדרה תואמים.
7. רק אחרי הבדיקה משלמים.

## כדאי לדעת
- **ייצור:** בערך 5 ימי עבודה, ואחר כך משלוח. מוצרים שונים יכולים להגיע בנפרד.
- **עותק ניסיון:** לספר ראשון כדאי להזמין קודם עותק אחד.
- **צבעים:** הנייר מדפיס כהה ורווי פחות מהמסך.
"""
    spine = ('   - **Text:** English letters or numbers. Keep it short.\n' if text_ok else
             '   - **Text:** none. Under 40 pages Prodigi advises colour only.\n')
    return f"""# Ordering the book at Prodigi

> **Important:** Prodigi is listed because it ships worldwide, Israel included, and takes a ready PDF. It is not a recommendation. We take no responsibility for the print, the price, the delivery or the order. You place the order and pay in your own account.

## What you order
- **Product:** {p['type']}, {p['w_mm']:g} x {p['h_mm']:g} mm, {p['paper']}
- **SKU:** `{p['sku']}`
- **File:** `{name}` ({total} pages including the covers)
- **Copies:** {copies}{ship_en}
- **Catalogue base price:** ${p['price_usd']:.2f} a copy (as of {c['captured']}). Extra pages and shipping are added. Only the order summary shows the exact price.

## What you need
- A Prodigi account (free to open).
- A payment card.
- The recipient's address, phone and email. You type them on Prodigi's site only, never here.

## The steps on the site
1. **Create order**, then choose the destination country.
2. Find the product by its SKU `{p['sku']}`, then **Add to basket**.
3. **Add pdf** and upload `{name}` from this folder.
4. **Spine**:
{spine}   - **Background:** `{bg}` · **Text colour:** `{ink}` · **Font:** Brandon or Arial · **Size:** 16px
5. **Continue**, then type the address and choose a shipping method.
6. **On the summary, before paying:** take a screenshot and send it to me. I'll check the product, size, page count, copies and spine.
7. Pay only after that check.

## Good to know
- **Production:** about 5 working days, then shipping. Different products may arrive separately.
- **Proof:** for a first book, order one copy first.
- **Colour:** paper prints darker and less saturated than a screen.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--type', choices=['hardcover', 'softcover', 'layflat', 'magazine'])
    ap.add_argument('--choose', metavar='SKU')
    ap.add_argument('--copies', type=int, default=1)
    ap.add_argument('--country', default='')
    ap.add_argument('--pack', action='store_true')
    a = ap.parse_args()
    if a.list or not (a.choose or a.pack):
        list_products(a.type)
        return
    if not a.work:
        sys.exit('--work is needed')
    work = os.path.abspath(a.work)
    if a.choose:
        choose(work, a.choose, a.copies, a.country)
    if a.pack:
        pack(work)


if __name__ == '__main__':
    main()
