"""Route maps as SVG (vector in the PDF). Land: Natural Earth 1:50m via world-atlas (assets/land-50m.json).

route_svg(tracks, w, h) draws every day's path in a box of w x h mm; highlight= picks one day to stand out;
labels= puts day numbers at the start of each day. Maps are never mirrored for right-to-left books.
Limit: trips that cross the 180th meridian (Fiji, Alaska-Russia) are not unwrapped.
"""
import math
import os

from common import ASSETS, load

_RINGS = None


def land_rings():
    global _RINGS
    if _RINGS is None:
        topo = load(os.path.join(ASSETS, 'land-50m.json'))
        (sx, sy), (tx, ty) = topo['transform']['scale'], topo['transform']['translate']
        arcs = []
        for arc in topo['arcs']:
            x = y = 0
            pts = []
            for dx, dy in arc:
                x += dx
                y += dy
                pts.append((x * sx + tx, y * sy + ty))
            arcs.append(pts)
        obj = topo['objects']['land']
        geoms = obj.get('geometries', [obj])
        _RINGS = []
        for g in geoms:
            polys = g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']]
            for poly in polys:
                for ring in poly:
                    pts = []
                    for i in ring:
                        a = arcs[i] if i >= 0 else arcs[~i][::-1]
                        pts.extend(a if not pts else a[1:])
                    # a coast that crosses the 180th meridian (Russia, Fiji) jumps from +180 to -180: unwrap it so
                    # the ring stays continuous, or the jump is drawn as a band across the whole map
                    for j in range(1, len(pts)):
                        x, y = pts[j]
                        px = pts[j - 1][0]
                        while x - px > 180:
                            x -= 360
                        while x - px < -180:
                            x += 360
                        pts[j] = (x, y)
                    shift = -360 * math.floor((min(p[0] for p in pts) + 180) / 360)   # its west end within -180..180
                    if shift:
                        pts = [(x + shift, y) for x, y in pts]
                    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                    _RINGS.append((min(xs), min(ys), max(xs), max(ys), pts))
    return _RINGS


def _clip(poly, x0, y0, x1, y1):
    """Sutherland-Hodgman: a polygon clipped to a rectangle (a huge ring would otherwise flood the view)."""
    def inside(p, e):
        return (p[0] >= x0, p[0] <= x1, p[1] >= y0, p[1] <= y1)[e]

    def cut(p, q, e):
        if e < 2:
            X = x0 if e == 0 else x1
            return (X, p[1] + (X - p[0]) * (q[1] - p[1]) / (q[0] - p[0]))
        Y = y0 if e == 2 else y1
        return (p[0] + (Y - p[1]) * (q[0] - p[0]) / (q[1] - p[1]), Y)
    out = poly
    for e in range(4):
        inp, out = out, []
        if not inp:
            break
        s = inp[-1]
        for p in inp:
            if inside(p, e):
                if not inside(s, e):
                    out.append(cut(s, p, e))
                out.append(p)
            elif inside(s, e):
                out.append(cut(s, p, e))
            s = p
    return out


def main_region(pts):
    """Which points are the trip itself: a flight from home (one day far from all the others) is left out of the
    view, so a city or a region is not shrunk to a dot by the way there."""
    if len(pts) < 3:
        return [True] * len(pts)
    mlat = sorted(p[0] for p in pts)[len(pts) // 2]
    mlon = sorted(p[1] for p in pts)[len(pts) // 2]

    def dist(p):
        return math.hypot((p[0] - mlat) * 111.0, (p[1] - mlon) * 111.0 * math.cos(math.radians(mlat)))
    ds = [dist(p) for p in pts]
    typical = sorted(ds)[len(ds) // 2]
    far = max(250.0, 5 * typical)
    keep = [d <= far for d in ds]
    return keep if sum(keep) >= max(2, len(pts) // 2) else [True] * len(pts)


def route_svg(tracks, w, h, highlight=None, labels=False, min_span_km=40, places=()):
    """tracks: {day number: [[lat, lon], ...]}; highlight: the day numbers to show strong. Returns an <svg> w x h mm.

    The view always holds the whole trip, so a day's map shows where that day sits in the journey."""
    pts = [p for t in tracks.values() for p in t]
    if not pts:
        return ''
    keep = main_region(pts)
    focus = [p for p, k in zip(pts, keep) if k]
    inside = {tuple(p) for p in focus}
    if places:   # a place counts as in view when it is near the trip's own points
        flat = [(p['lat'], p['lon']) for p in places]
        pk = main_region(flat + [tuple(p) for p in focus])[:len(flat)]
        inside_pl = {f for f, ok in zip(flat, pk) if ok}
    else:
        inside_pl = set()
    lat0 = sum(p[0] for p in focus) / len(focus)
    k = math.cos(math.radians(lat0))
    fx = [p[1] * k for p in focus]
    fy = [-p[0] for p in focus]
    minx, maxx, miny, maxy = min(fx), max(fx), min(fy), max(fy)
    span = min_span_km / 111.0  # never zoom in closer than ~40 km, so the land around makes sense
    bw, bh = max(maxx - minx, span), max(maxy - miny, span)
    bw, bh = bw * 1.36, bh * 1.36  # 18% margin on each side
    if bw / bh < w / h:
        bw = bh * w / h
    else:
        bh = bw * h / w
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    vx0, vy0, vx1, vy1 = cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2
    s = w / bw

    def T(x, y):
        return (x - vx0) * s, (y - vy0) * s

    lon0, lon1 = vx0 / k, vx1 / k
    lat_lo, lat_hi = -vy1, -vy0
    parts = []
    for bx0, by0, bx1, by1, ring in land_rings():
        if bx1 < lon0 or bx0 > lon1 or by1 < lat_lo or by0 > lat_hi:
            continue
        poly = _clip([(x * k, -y) for x, y in ring], vx0, vy0, vx1, vy1)
        if len(poly) >= 3:
            parts.append('M' + 'L'.join('%.2f,%.2f' % T(x, y) for x, y in poly) + 'Z')
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.2f} {h:.2f}" preserveAspectRatio="xMidYMid meet">',
           f'<rect class="sea" width="{w:.2f}" height="{h:.2f}"/>']
    if parts:
        out.append('<path class="land" d="' + ''.join(parts) + '"/>')
    sw = max(0.45, w / 160)
    days = sorted(n for n in tracks if tracks[n])
    for a, b in zip(days, days[1:]):  # the way from one day's last place to the next day's first
        (x0, y0), (x1, y1) = T(tracks[a][-1][1] * k, -tracks[a][-1][0]), T(tracks[b][0][1] * k, -tracks[b][0][0])
        out.append(f'<line class="link" x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" stroke-width="{sw * 0.7:.2f}" '
                   f'stroke-dasharray="{sw * 1.6:.2f} {sw * 1.6:.2f}"/>')
    dots = []
    for n, t in tracks.items():
        if not t:
            continue
        cls = 'trk' if highlight is None or n in highlight else 'trk dim'
        xy = [T(p[1] * k, -p[0]) for p in t]
        if len(xy) > 1:
            out.append(f'<polyline class="{cls}" stroke-width="{sw:.2f}" points="' +
                       ' '.join('%.2f,%.2f' % q for q in xy) + '"/>')
        first = next((q for q, p in zip(xy, t) if tuple(p) in inside), None)   # the day's first place in view
        if first is None:
            continue
        r = sw * (2.2 if cls == 'trk' else 1.4)
        out.append(f'<circle class="dot{" dim" if "dim" in cls else ""}" cx="{first[0]:.2f}" cy="{first[1]:.2f}" r="{r:.2f}"/>')
        dots.append((first, r, n))
    if labels:   # days that start at one place share one label: "2·3·4"
        groups = []
        for q, r, n in dots:
            g = next((g for g in groups if math.hypot(g[0][0] - q[0], g[0][1] - q[1]) < 3 * r), None)
            if g:
                g[2].append(n)
            else:
                groups.append([q, r, [n]])
        for q, r, ns in groups:
            out.append(f'<text class="lbl" x="{q[0] + r * 1.6:.2f}" y="{q[1] - r * 1.2:.2f}" '
                       f'font-size="{max(2.4, w / 55):.2f}" style="direction:ltr;unicode-bidi:isolate">{"·".join(str(n) for n in sorted(ns))}</text>')
    if places:   # the names of the places in view, each once, never on top of another
        fs = max(2.2, w / 62)
        taken = [(q[0] - r * 2, q[1] - r * 2, r * 4 + fs * 2, r * 4) for q, r, n in dots]
        seen = set()
        for pl in places:
            name = (pl.get('name') or '').strip()
            if not name or name.casefold() in seen or (pl['lat'], pl['lon']) not in inside_pl:
                continue
            x, y = T(pl['lon'] * k, -pl['lat'])
            if not (0 <= x <= w and 0 <= y <= h):
                continue
            tw = len(name) * fs * 0.52
            box = (x - tw / 2, y + fs * 0.6, tw, fs * 1.1)
            if any(not (box[0] + box[2] < b[0] or b[0] + b[2] < box[0] or box[1] + box[3] < b[1] or b[1] + b[3] < box[1])
                   for b in taken):
                continue
            taken.append(box)
            seen.add(name.casefold())
            out.append(f'<circle class="dot dim" cx="{x:.2f}" cy="{y:.2f}" r="{sw * 1.1:.2f}"/>'
                       f'<text class="lbl" x="{x:.2f}" y="{y + fs * 1.4:.2f}" font-size="{fs:.2f}" text-anchor="middle">{name}</text>')
    out.append('</svg>')
    return ''.join(out)
