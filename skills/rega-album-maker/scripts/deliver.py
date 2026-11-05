#!/usr/bin/env python3
"""Put the finished book in the book's folder, as a new version: never over an earlier one.

    python deliver.py --work WORK

Copies WORK/book.pdf to the book's folder (the parent of its work folder, in the albums folder) as
"<title> - גרסה N.pdf" ("<title> - version N.pdf" in English), N the next free number. Earlier versions stay.
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import album_dir, load  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work', required=True)
    a = ap.parse_args()
    work = os.path.abspath(a.work)
    pdf = os.path.join(work, 'book.pdf')
    if not os.path.isfile(pdf):
        sys.exit('No book.pdf yet: run render.py first.')
    book = load(os.path.join(work, 'book.json'))
    if (os.path.getmtime(os.path.join(work, 'check.md')) if os.path.isfile(os.path.join(work, 'check.md')) else 0) < os.path.getmtime(pdf):
        sys.exit('Run check.py first: a book is delivered only after it passes.')
    if 'Ready for the printer' not in open(os.path.join(work, 'check.md'), encoding='utf-8').read():
        sys.exit('check.md lists problems: fix them before delivering.')
    he = book.get('lang') == 'he'
    title = ''.join(ch for ch in (book.get('title') or 'Book') if ch not in '\\/:*?"<>|').strip() or 'Book'
    out = album_dir(work)
    n = 1
    while True:
        dst = os.path.join(out, f'{title} - {"גרסה" if he else "version"} {n}.pdf')
        if not os.path.exists(dst):
            break
        n += 1
    shutil.copyfile(pdf, dst)
    print(f'Delivered: {dst}')
    print(f'The book\'s folder: {out}')


if __name__ == '__main__':
    main()
