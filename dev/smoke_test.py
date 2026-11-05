#!/usr/bin/env python3
"""End-to-end test of the scripts on the synthetic eval photos. It needs the packages in requirements.txt and
Chrome, Edge or Chromium; it touches nothing outside a temporary folder.

    python dev/smoke_test.py            # quick: 4 styles, 3 languages, the Prodigi stage (a few minutes)
    python dev/smoke_test.py --all      # every style

What it checks, without an AI: every palette and structure resolves for every style; a trip (GPS, WhatsApp, a
blurred and a duplicate photo) and a party (no GPS) are scanned, grouped, laid out, rendered and checked; the book
has the asked page count and passes the design rules; English, Hebrew and an unbuilt language (French) work; a
Prodigi product is chosen, the book follows its size, and the print folder is packed; the style samples are made.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, 'skills', 'rega-album-maker')
SCRIPTS = os.path.join(SKILL, 'scripts')
EVALS = os.path.join(SKILL, 'evals')
sys.path.insert(0, SCRIPTS)
failures = []


def run(script, *args, expect=0):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], capture_output=True, text=True,
                       encoding='utf-8', errors='replace',
                       env=dict(os.environ, PYTHONIOENCODING='utf-8', REGA_NO_OPEN='1'))   # no windows during tests
    if r.returncode != expect:
        failures.append(f'{script} {" ".join(args[:3])}: exit {r.returncode}\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}')
    return r.stdout + r.stderr


def check(cond, msg):
    if not cond:
        failures.append(msg)
    return cond


def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def save(p, d):
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False)


def looks():
    """Every style with every palette and structure: the colours and fonts it needs are there."""
    from looks import palettes, resolve, structures, style_names
    n = 0
    for s in style_names():
        for p in ['style'] + list(palettes()):
            for st in structures():
                c = resolve(s, p, st)
                n += 1
                for role in ('paper', 'ink', 'label', 'accent', 'dark', 'endpaper'):
                    check(isinstance(c['colors'].get(role), str), f'{s}/{p}/{st}: colour {role} missing')
    resolve('minimal', {'accent': '#1f4aa8'})
    print(f'  looks: {n} combinations resolve')


def book(work, folder, lang, style, structure, pages, title, extra_brief=None):
    run('brief.py', '--work', work, '--init', folder)
    out = run('scan.py', folder, '--work', work)
    check('Traceback' not in out, f'scan crashed for {folder}')
    run('group.py', '--work', work, '--lang', lang)
    scan, groups = load(os.path.join(work, 'scan.json')), load(os.path.join(work, 'groups.json'))
    by = {r['id']: r for r in scan['items']}
    bad = {'dup', 'blur', 'dark', 'bright', 'screenshot', 'small', 'copy', 'live', 'whatsapp', 'undated', 'error'}
    chapters = []
    for d in groups['days']:
        ids = [i for i in d['ids'] if by[i]['kind'] == 'photo' and not set(by[i]['flags']) & bad]
        if ids:
            chapters.append({'title': f'Day {d["n"]}', 'photos': ids, 'highlights': ids[:1], 'deck': None})
    every = [i for c in chapters for i in c['photos']]
    check(len(every) >= 4, f'{folder}: too few usable photos ({len(every)})')
    save(os.path.join(work, 'selection.json'), {'title': title, 'lang': lang, 'cover': every[0], 'closing': None,
                                                'no_people': every, 'chapters': chapters})
    brief = load(os.path.join(work, 'brief.json'))
    brief.update({'scope': {}, 'story': {}, 'book': {'title': title, 'lang': lang, 'kind': 'trip', 'chapters': 'day'},
                  'format': {'size': 'square-21', 'pages': pages}, 'print': {'printer': 'none'},
                  'design': {'structure': structure, 'style': style, 'palette': 'style'}, 'confirmed': True})
    brief.update(extra_brief or {})
    save(os.path.join(work, 'brief.json'), brief)


def build(work, label):
    out = run('layout.py', '--work', work, '--pad')
    rules = [line for line in out.splitlines() if line.startswith('RULE')]
    check(not rules, f'{label}: design rules failed: {rules}')
    run('render.py', '--work', work)
    b = load(os.path.join(work, 'book.json'))
    inside = len([p for p in b['pages'] if p.get('n')])
    goal = b.get('goal_pages')
    check(not goal or inside == goal, f'{label}: {inside} inside pages, {goal} asked')
    out = run('check.py', '--work', work)
    check('Ready for the printer' in out, f'{label}: check.py did not pass:\n{out[-1200:]}')
    return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--all', action='store_true')
    a = ap.parse_args()
    from looks import style_names
    styles = style_names() if a.all else ['nordic', 'scrapbook', 'swiss', 'mosaic']
    t0 = time.time()
    tmp = tempfile.mkdtemp(prefix='rega-smoke-')
    try:
        print('looks')
        looks()
        trip = os.path.join(EVALS, 'hebrew-trip-book', 'files', 'photos')
        party = os.path.join(EVALS, 'english-party-qr', 'files', 'party')
        for k, (folder, lang, style, structure) in enumerate(
                [(trip, 'he', 'nordic', 'journal'), (party, 'en', 'kids', 'album'), (party, 'fr', 'newspaper', 'magazine')]):
            work = os.path.join(tmp, f'book-{k}')
            print(f'book {k}: {lang} {style} {structure}')
            book(work, folder, lang, style, structure, 12, 'Test')
            b = build(work, f'{lang}/{style}')
            check(b['dir'] == ('rtl' if lang == 'he' else 'ltr'), f'{lang}: direction {b["dir"]}')
        print('journey')   # the route page from the journey the user told: a flight and a train, with a legend
        work = os.path.join(tmp, 'book-0')
        sel = load(os.path.join(work, 'selection.json'))
        sel['journey'] = {'stops': [{'name': 'תל אביב', 'lat': 32.01, 'lon': 34.89, 'home': True},
                                    {'name': 'רומא', 'lat': 41.9, 'lon': 12.5},
                                    {'name': 'פירנצה', 'lat': 43.77, 'lon': 11.25, 'main': True}],
                          'legs': [{'from': 'תל אביב', 'to': 'רומא', 'by': 'flight'},
                                   {'from': 'רומא', 'to': 'פירנצה', 'by': 'train'}]}
        save(os.path.join(work, 'selection.json'), sel)
        b = build(work, 'journey')
        route = [i for p in b['pages'] for i in p.get('items', []) if i['type'] == 'route']
        check(bool(route) and bool(route[0].get('journey')), 'journey: the route page has no journey')
        with open(os.path.join(work, 'book.html'), encoding='utf-8') as f:
            html = f.read()
        check('class="jleg"' in html and 'טיסה' in html and 'רכבת' in html, 'journey: the map or its legend is missing')
        work = os.path.join(tmp, 'styles')
        book(work, party, 'en', styles[0], 'album', 8, 'Styles')
        for s in styles:
            print(f'style {s}')
            br = load(os.path.join(work, 'brief.json'))
            br['design']['style'] = s
            save(os.path.join(work, 'brief.json'), br)
            b = build(work, f'style {s}')
            check(b['style']['name'] == s, f'style {s}: book.json has {b["style"]["name"]}')
        print('prodigi')
        work = os.path.join(tmp, 'prodigi')
        book(work, trip, 'he', 'classic', 'album', 20, 'Print')
        run('printer.py', '--work', work, '--choose', 'BOOK-FE-A5-P-SOFT-G', '--copies', '1', '--country', 'GB')
        b = build(work, 'prodigi A5')
        check((b['w'], b['h']) == (148, 210), f'prodigi: the book is {b["w"]} x {b["h"]}, not 148 x 210')
        check(b.get('gutter') == 6, 'prodigi: the fold is not kept clear')
        out = run('printer.py', '--work', work, '--pack')
        check('Ready to upload' in out, f'prodigi pack:\n{out[-1200:]}')
        folder = os.path.join(work, 'להדפסה')
        check(os.path.isdir(folder) and any(f.endswith('.pdf') for f in os.listdir(folder)), 'prodigi: no upload file')
        print('samples')
        out = run('sample.py', '--work', os.path.join(tmp, 'book-1'), '--styles', 'minimal,kids')
        check(os.path.isfile(os.path.join(tmp, 'book-1', 'samples', 'styles.png')), f'samples: no sheet\n{out[-800:]}')
        run('brief.py', '--work', os.path.join(tmp, 'book-1'))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        print(f'\nFAILED ({len(failures)}):')
        for f in failures:
            print('- ' + f)
        sys.exit(1)
    print(f'\nOK in {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
