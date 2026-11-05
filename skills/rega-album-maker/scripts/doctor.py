#!/usr/bin/env python3
"""What can this computer do? Checks the tools and prints the tier: book, book + QR to links, book + clips.
Also says, in one line, when a newer Rega is out.

    python doctor.py [--no-update-check]

The version check reads one public file from GitHub (the plugin's version) and sends nothing about the user. It waits
at most 3 seconds, stays silent when offline or blocked, never installs anything, and is skipped with
--no-update-check, REGA_NO_UPDATE_CHECK=1 or CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1.
"""
import importlib
import json
import os
import re
import subprocess
import sys
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import find_browser, tool  # noqa: E402

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQ = os.path.join(SKILL_DIR, 'requirements.txt')
REPO = 'https://github.com/tamirgur/rega-album-maker'
LATEST_URL = 'https://raw.githubusercontent.com/tamirgur/rega-album-maker/main/.claude-plugin/plugin.json'


def installed_version():
    """The version in this skill's own SKILL.md, so it works however the skill folder was installed."""
    try:
        with open(os.path.join(SKILL_DIR, 'SKILL.md'), encoding='utf-8') as f:
            m = re.search(r'^\s+version:\s*"?(\d+(?:\.\d+)*)"?\s*$', f.read(6000), re.MULTILINE)
        return m.group(1) if m else None
    except OSError:
        return None


def vkey(v):
    return tuple(int(x) for x in v.split('.'))


class LatestVersion(threading.Thread):
    """Fetches the newest version in the background while the other checks run."""

    def __init__(self):
        super().__init__(daemon=True)
        self.version = None

    def run(self):
        try:
            req = urllib.request.Request(LATEST_URL, headers={'User-Agent': f'rega-album-maker ({REPO})'})
            with urllib.request.urlopen(req, timeout=3) as r:
                v = str(json.load(r).get('version', ''))
            if re.fullmatch(r'\d+(\.\d+)*', v):
                self.version = v
        except Exception:  # noqa: BLE001, S110 - offline, blocked or odd reply: say nothing, by design
            pass


def update_check_wanted():
    if '--no-update-check' in sys.argv[1:]:
        return False
    return not any(os.environ.get(k, '').strip() not in ('', '0')
                   for k in ('REGA_NO_UPDATE_CHECK', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'))


def update_line(latest):
    """One line when GitHub has a newer version than this one; None otherwise."""
    mine = installed_version()
    if not (latest and mine) or vkey(latest) <= vkey(mine):
        return None
    return (f'update   Rega {latest} is out (this is {mine}). What changed: {REPO}/blob/main/CHANGELOG.md\n'
            '         Claude Code: claude plugin marketplace update tamirgur, then '
            'claude plugin update rega-album-maker@tamirgur, then restart Claude Code')


def has(mod):
    try:
        importlib.import_module(mod)
        return True
    except Exception:
        return False


def main():
    print(f'Rega {installed_version() or "?"} · Python {sys.version.split()[0]} · {sys.platform}')   # for an issue report
    latest = LatestVersion() if update_check_wanted() else None
    if latest:
        latest.start()
    py = sys.version_info >= (3, 9)
    rows = [
        ('Python 3.9+', py, True, 'runs the scripts', 'https://www.python.org/downloads/'),
        ('Pillow', has('PIL'), True, 'reads photos', f'pip install -r "{REQ}"'),
        ('segno', has('segno'), True, 'QR codes', f'pip install -r "{REQ}"'),
        ('Chrome or Edge', bool(find_browser()), True, 'writes the PDF', 'install Google Chrome, or set CHROME_PATH'),
        ('pillow-heif', has('pillow_heif'), False, 'iPhone HEIC photos', 'pip install pillow-heif'),
        ('PyMuPDF', has('pymupdf') or has('fitz'), False, 'final PDF check and page previews', 'pip install pymupdf'),
        ('zxing-cpp', has('zxingcpp'), False, 'checks that QR codes scan',
         'pip install zxing-cpp' if sys.version_info >= (3, 10) else 'needs Python 3.10+ (no ready package for 3.9)'),
        ('OpenCV', has('cv2'), False, 'finds faces: crops and titles keep clear of people', 'pip install opencv-python-headless'),
    ]
    ff = tool('ffmpeg') and tool('ffprobe')
    install_ff = {'win32': 'winget install Gyan.FFmpeg', 'darwin': 'brew install ffmpeg'}.get(sys.platform, 'sudo apt install ffmpeg')
    rows.append(('ffmpeg', bool(ff), False, 'video clips, frames, video dates', install_ff))
    hdr = False
    if ff:
        r = subprocess.run([tool('ffmpeg'), '-hide_banner', '-filters'], capture_output=True, text=True, errors='replace')
        hdr = ' zscale ' in r.stdout
    for name, ok, required, why, fix in rows:
        print(f'{"ok     " if ok else "MISSING" if required else "missing"}  {name:15} {why}' + ('' if ok else f'   ->  {fix}'))
    if ff and not hdr:
        print('note     this ffmpeg has no zscale filter: iPhone HDR clips may look flat (a "full" build has it)')
    if latest:
        latest.join(3.5)  # a hard limit, even if the name lookup hangs
        line = update_line(latest.version)
        if line:
            print(line)
    missing = [r for r in rows if r[2] and not r[1]]
    if missing:
        print('\nTIER: not ready. Install the required items above, then run this again.')
        sys.exit(1)
    if ff:
        print('\nTIER: book + clips. Photos, maps, PDF, QR codes, and short clips cut from the videos.')
    else:
        print('\nTIER: book + QR to links. Photos, maps, PDF, and QR codes to videos the user uploads as they are. '
              'Install ffmpeg to also cut clips.')


if __name__ == '__main__':
    main()
