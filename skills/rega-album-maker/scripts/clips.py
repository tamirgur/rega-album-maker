#!/usr/bin/env python3
"""Video tools (need ffmpeg): look at a video, cut a clip, or take a still frame for the book.

    python clips.py sheet VIDEO --work WORK                     16 frames with their times, to choose a moment
    python clips.py cut VIDEO --start 12 --end 27 --work WORK [--mute] [--name 03-gullfoss]
    python clips.py frame VIDEO --at 14.5 --work WORK           a still that joins the photos (new id in scan.json)

Clips are H.264 + AAC MP4 (at most 1920 px, sound evened out to -16 LUFS, ready to stream). iPhone HDR video is
converted to normal colors, so it does not look grey. The source video is only read.
VIDEO can be a path or a photo id from scan.json (for example 22).
"""
import argparse
import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load, parse_time, fmt_time, day_of, pil_font, save, tool, video_meta  # noqa: E402

TONEMAP = ('zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,'
           'zscale=t=bt709:m=bt709:r=tv,format=yuv420p')


def ffmpeg():
    exe = tool('ffmpeg')
    if not exe:
        sys.exit('ffmpeg is not installed. Without it, put QR codes to videos uploaded as they are '
                 '(see references/video.md), or install it: winget install Gyan.FFmpeg | brew install ffmpeg | sudo apt install ffmpeg')
    return exe


def has_zscale(exe):
    r = subprocess.run([exe, '-hide_banner', '-filters'], capture_output=True, text=True, errors='replace')
    return ' zscale ' in r.stdout


def resolve(video, work):
    if video.isdigit():
        scan = load(os.path.join(work, 'scan.json'))
        r = next((r for r in scan['items'] if r['id'] == int(video)), None)
        if not r or r['kind'] != 'video':
            sys.exit(f'#{video} is not a video in scan.json')
        return r['path'], r
    path = os.path.abspath(video)
    if not os.path.isfile(path):
        sys.exit(f'No such file: {video}')
    return path, None


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, errors='replace')
    if r.returncode:
        sys.exit('ffmpeg failed:\n' + r.stderr[-1500:])


def sheet(a):
    from PIL import Image, ImageDraw
    exe = ffmpeg()
    path, _ = resolve(a.video, a.work)
    m = video_meta(path)
    dur = m.get('duration') or 0
    if not dur:
        sys.exit('Could not read the length of this video.')
    out = os.path.join(a.work, 'clips')
    os.makedirs(out, exist_ok=True)
    tmp = os.path.join(out, '_frame.jpg')
    cells, times = [], [dur * (i + 0.5) / 16 for i in range(16)]
    vf = (TONEMAP + ',' if m.get('hdr') and has_zscale(exe) else '') + 'scale=320:-2'
    for t in times:
        run([exe, '-y', '-loglevel', 'error', '-ss', f'{t:.2f}', '-i', path, '-frames:v', '1', '-vf', vf, tmp])
        cells.append(Image.open(tmp).convert('RGB'))
    w, h = cells[0].size
    img = Image.new('RGB', (4 * w, 4 * (h + 24)), (246, 245, 242))
    d = ImageDraw.Draw(img)
    f = pil_font(18, 600)
    for i, (c, t) in enumerate(zip(cells, times)):
        x, y = (i % 4) * w, (i // 4) * (h + 24)
        img.paste(c, (x, y))
        d.text((x + 6, y + h + 2), f'{int(t // 60)}:{t % 60:04.1f}', fill=(30, 30, 30), font=f)
    os.remove(tmp)
    dst = os.path.join(out, os.path.splitext(os.path.basename(path))[0] + '-sheet.jpg')
    img.save(dst, quality=82)
    print(f'{dst}\nLength {dur:.1f} s' + (' · HDR' if m.get('hdr') else '') + '. Times under each frame (minutes:seconds).')


def cut(a):
    exe = ffmpeg()
    path, _ = resolve(a.video, a.work)
    m = video_meta(path)
    if a.end <= a.start:
        sys.exit('--end must be after --start')
    out = os.path.join(a.work, 'clips')
    os.makedirs(out, exist_ok=True)
    n = len([f for f in os.listdir(out) if f.endswith('.mp4')]) + 1
    name = a.name or f'{n:02d}-{os.path.splitext(os.path.basename(path))[0]}'
    dst = os.path.join(out, name + '.mp4')
    vf = []
    if m.get('hdr'):
        if has_zscale(exe):
            vf.append(TONEMAP)
        else:
            print('Note: this is HDR video and this ffmpeg has no zscale filter, so colors may look flat.')
    vf += ["scale='if(gte(iw,ih),min(1920,iw),-2)':'if(gte(iw,ih),-2,min(1920,ih))'", 'fps=30', 'format=yuv420p']
    cmd = [exe, '-y', '-loglevel', 'error', '-ss', f'{a.start:.3f}', '-i', path, '-t', f'{a.end - a.start:.3f}',
           '-vf', ','.join(vf), '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-profile:v', 'high',
           '-movflags', '+faststart']
    cmd += ['-an'] if a.mute else ['-c:a', 'aac', '-b:a', '128k', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11']
    run(cmd + [dst])
    print(f'{dst} ({os.path.getsize(dst) / 1e6:.1f} MB, {a.end - a.start:.1f} s{", no sound" if a.mute else ""})')
    print('Next: the user uploads it (YouTube "unlisted", Google Drive or OneDrive with "anyone with the link can view") '
          'and gives you the link for the QR code.')


def frame(a):
    from PIL import Image
    exe = ffmpeg()
    path, rec = resolve(a.video, a.work)
    m = video_meta(path)
    out = os.path.join(a.work, 'frames')
    os.makedirs(out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    dst = os.path.join(out, f'{stem}-{a.at:.1f}s.jpg')
    vf = [TONEMAP] if m.get('hdr') and has_zscale(exe) else []
    run([exe, '-y', '-loglevel', 'error', '-ss', f'{a.at:.3f}', '-i', path, '-frames:v', '1', '-q:v', '2']
        + (['-vf', ','.join(vf)] if vf else []) + [dst])
    scan_path = os.path.join(a.work, 'scan.json')
    scan = load(scan_path)
    from datetime import timedelta
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from scan import photo_info
    key = hashlib.sha1(dst.encode('utf-8')).hexdigest()[:12]
    thumb = os.path.join(a.work, 'thumbs', key + '.jpg')
    info = photo_info(dst, thumb)
    r = {'path': dst, 'name': os.path.basename(dst), 'key': key, 'kind': 'photo', 'thumb': thumb, 'flags': ['from_video'],
         'size': os.path.getsize(dst), 'mtime': int(os.path.getmtime(dst)), 'in_range': True, 'date_source': 'video'}
    r.update(info)
    if rec:
        t = parse_time(rec['taken']) + timedelta(seconds=a.at)
        r.update(taken=fmt_time(t), day=day_of(t).isoformat(), lat=rec.get('lat'), lon=rec.get('lon'), from_id=rec['id'])
    else:
        r.update(taken=None, day=None)
    r['id'] = max(x['id'] for x in scan['items']) + 1
    r['score'] = 0
    scan['items'].append(r)
    save(scan_path, scan)
    with Image.open(dst) as im:
        print(f'{dst}\nAdded as photo #{r["id"]} ({im.width} x {im.height} px). A video frame has fewer pixels than a photo: '
              f'layout.py reports its print resolution, so give it a small frame if it is low.')
    if not rec:
        print('This video is not in scan.json, so the frame has no date: pass the video as its id to keep the date.')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    for name in ('sheet', 'cut', 'frame'):
        p = sp.add_parser(name)
        p.add_argument('video')
        p.add_argument('--work', required=True)
        if name == 'cut':
            p.add_argument('--start', type=float, required=True)
            p.add_argument('--end', type=float, required=True)
            p.add_argument('--mute', action='store_true')
            p.add_argument('--name')
        if name == 'frame':
            p.add_argument('--at', type=float, required=True)
    a = ap.parse_args()
    {'sheet': sheet, 'cut': cut, 'frame': frame}[a.cmd](a)


if __name__ == '__main__':
    main()
