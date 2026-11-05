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


MODES = ('flight', 'train', 'car', 'bus', 'ferry', 'walk')


def journey_parts(journey):
    """The stops and the legs of a journey from selection.json, checked. Returns (stops, legs, problems)."""
    stops, problems = [], []
    for s in journey.get('stops') or []:
        try:
            stops.append({'name': str(s['name']).strip(), 'lat': float(s['lat']), 'lon': float(s['lon']),
                          'home': bool(s.get('home')), 'main': bool(s.get('main'))})
        except (KeyError, TypeError, ValueError):
            problems.append(f'journey: a stop needs a name, lat and lon: {s}')
    index = {s['name'].casefold(): i for i, s in enumerate(stops)}

    def find(x):
        if isinstance(x, int) and 0 <= x < len(stops):
            return x
        return index.get(str(x).strip().casefold())
    legs = []
    for leg in journey.get('legs') or []:
        a, b, by = find(leg.get('from')), find(leg.get('to')), leg.get('by')
        if a is None or b is None or a == b:
            problems.append(f'journey: a leg must go from one stop to another, by name: {leg}')
        elif by not in MODES:
            problems.append(f'journey: "by" is one of {", ".join(MODES)}: {leg}')
        else:
            legs.append((a, b, by))
    if len(stops) < 2:
        problems.append('journey: at least two stops')
    if stops and not any(s['main'] for s in stops):   # the destination: the stop that is not home with most legs
        cand = [i for i, s in enumerate(stops) if not s['home']] or [0]
        stops[max(cand, key=lambda i: sum(i in (a, b) for a, b, _ in legs))]['main'] = True
    return stops, legs, problems


def journey_svg(journey, w, h, words, min_span_km=60):
    """The whole journey, from home to the destination, as told in the story: each stop named, each leg drawn by how
    it was travelled (a flight as an arc, a train as a line, a drive as dots), with a small legend.

    journey: {"stops": [{"name", "lat", "lon", "home"?, "main"?}], "legs": [{"from", "to", "by"}]};
    words: the legend's words by mode. Returns an <svg> w x h mm, coloured by the book's CSS."""
    stops, legs, _ = journey_parts(journey)
    if len(stops) < 2:
        return ''
    lat0 = sum(s['lat'] for s in stops) / len(stops)
    k = math.cos(math.radians(lat0))
    xs, ys = [s['lon'] * k for s in stops], [-s['lat'] for s in stops]
    span = min_span_km / 111.0
    bw, bh = max(max(xs) - min(xs), span), max(max(ys) - min(ys), span)
    bw, bh = bw * 1.3 + span * 0.6, bh * 1.3 + span * 0.6   # room for the names around the edge
    legend_h = 0.09   # the bottom strip of the map keeps the legend clear of the route
    if bw / bh < w / (h * (1 - legend_h)):
        bw = bh * w / (h * (1 - legend_h))
    else:
        bh = bw * h * (1 - legend_h) / w
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    vx0, vy0 = cx - bw / 2, cy - bh / 2
    s_ = w / bw
    vy1 = vy0 + h / s_
    vx1 = vx0 + bw

    def T(lat, lon):
        return (lon * k - vx0) * s_, (-lat - vy0) * s_

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.2f} {h:.2f}" preserveAspectRatio="xMidYMid meet">',
           f'<rect class="jsea" width="{w:.2f}" height="{h:.2f}"/>']
    parts = []
    lon0, lon1, lat_lo, lat_hi = vx0 / k, vx1 / k, -vy1, -vy0
    for bx0, by0, bx1, by1, ring in land_rings():
        if bx1 < lon0 or bx0 > lon1 or by1 < lat_lo or by0 > lat_hi:
            continue
        poly = _clip([(x * k, -y) for x, y in ring], vx0, vy0, vx1, vy1)
        if len(poly) >= 3:
            parts.append('M' + 'L'.join('%.2f,%.2f' % ((x - vx0) * s_, (y - vy0) * s_) for x, y in poly) + 'Z')
    if parts:
        out.append('<path class="jland" d="' + ''.join(parts) + '"/>')

    sw = max(0.45, w / 190)
    style = {'flight': f'stroke-width="{sw * 0.9:.2f}" stroke-dasharray="{sw * 3:.2f} {sw * 2.3:.2f}"',
             'train': f'stroke-width="{sw * 1.15:.2f}"',
             'car': f'stroke-width="{sw * 1.1:.2f}" stroke-dasharray="0.01 {sw * 2.2:.2f}"',
             'bus': f'stroke-width="{sw * 1.1:.2f}" stroke-dasharray="0.01 {sw * 2.2:.2f}"',
             'ferry': f'stroke-width="{sw * 0.9:.2f}" stroke-dasharray="{sw * 1.2:.2f} {sw * 1.6:.2f}"',
             'walk': f'stroke-width="{sw * 0.8:.2f}" stroke-dasharray="0.01 {sw * 1.6:.2f}"'}
    bow = {'flight': 0.2, 'car': 0.14, 'bus': 0.14, 'ferry': 0.1, 'walk': 0.1, 'train': 0}
    drawn = set()
    for a, b, by in legs:
        key = (min(a, b), max(a, b), by)   # there and back the same way: one line
        if key in drawn:
            continue
        drawn.add(key)
        (x0, y0), (x1, y1) = T(stops[a]['lat'], stops[a]['lon']), T(stops[b]['lat'], stops[b]['lon'])
        L = math.hypot(x1 - x0, y1 - y0) or 1
        if bow[by]:   # a curve, bowing up (north), so a drive beside a train line stays visible
            nx, ny = (y1 - y0) / L, -(x1 - x0) / L
            if ny > 0:
                nx, ny = -nx, -ny
            qx, qy = (x0 + x1) / 2 + nx * bow[by] * L, (y0 + y1) / 2 + ny * bow[by] * L
            d = f'M{x0:.2f},{y0:.2f} Q{qx:.2f},{qy:.2f} {x1:.2f},{y1:.2f}'
        else:
            d = f'M{x0:.2f},{y0:.2f} L{x1:.2f},{y1:.2f}'
        out.append(f'<path class="jleg" d="{d}" {style[by]}/>')

    fs = max(2.6, w / 44)
    boxes = []   # what is already on the map: dots and names, so a name never lands on another
    pts = []
    for i, st in enumerate(stops):
        x, y = T(st['lat'], st['lon'])
        r = sw * (3.4 if st['main'] else 2.0)
        pts.append((x, y, r))
        boxes.append((x - r, y - r, 2 * r, 2 * r))
    for i, st in enumerate(stops):
        x, y, r = pts[i]
        cls = 'jdot jmain' if st['main'] else 'jdot'
        extra = f' stroke-width="{sw * 1.1:.2f}"' if st['main'] else ''
        out.append(f'<circle class="{cls}" cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}"{extra}/>')
    order = sorted(range(len(stops)), key=lambda i: not stops[i]['main'])   # the destination's name first

    def clear(b):
        return (0 <= b[0] and b[0] + b[2] <= w and 0 <= b[1] and b[1] + b[3] <= h * (1 - legend_h) and
                all(b[0] + b[2] < o[0] or o[0] + o[2] < b[0] or b[1] + b[3] < o[1] or o[1] + o[3] < b[1] for o in boxes))
    for i in order:
        st, (x, y, r) = stops[i], pts[i]
        f = fs * (1.35 if st['main'] else 1.0)
        tw = len(st['name']) * f * 0.55
        cands = [(x - r - 1.2 - tw / 2, y + f * 0.35), (x + r + 1.2 + tw / 2, y + f * 0.35),   # beside
                 (x, y + r + f * 1.05), (x, y - r - f * 0.45)]                                  # below, above
        for tx, ty in cands:
            b = (tx - tw / 2, ty - f * 0.85, tw, f * 1.05)
            if clear(b):
                break
        else:
            tx, ty = cands[0]
            b = (tx - tw / 2, ty - f * 0.85, tw, f * 1.05)
        boxes.append(b)
        out.append(f'<text class="jlbl{" jmainlbl" if st["main"] else ""}" x="{tx:.2f}" y="{ty:.2f}" '
                   f'font-size="{f:.2f}" text-anchor="middle">{_esc(st["name"])}</text>')

    used = [m for m in MODES if any(by == m for _, _, by in legs)]
    if used:   # the legend: a sample of each line, and its word
        lf, sample, gap = fs * 0.78, fs * 2.2, fs * 0.6
        rtl = any('֐' <= ch <= 'ࣿ' for m in used for ch in words.get(m, ''))
        y = h - lf * 0.9
        cur = w - fs * 0.8 if rtl else fs * 0.8
        for m in used:   # words centred on their own box: right-to-left text flips "start" and "end"
            word = words.get(m, m)
            tw = len(word) * lf * 0.6
            if rtl:   # from the right: the word, then its line to the left of it
                out.append(f'<text class="jlg" x="{cur - tw / 2:.2f}" y="{y:.2f}" font-size="{lf:.2f}" '
                           f'text-anchor="middle">{_esc(word)}</text>')
                x1 = cur - tw - gap
                out.append(f'<path class="jleg" d="M{x1 - sample:.2f},{y - lf * 0.32:.2f} L{x1:.2f},{y - lf * 0.32:.2f}" {style[m]}/>')
                cur = x1 - sample - fs * 1.4
            else:
                out.append(f'<path class="jleg" d="M{cur:.2f},{y - lf * 0.32:.2f} L{cur + sample:.2f},{y - lf * 0.32:.2f}" {style[m]}/>')
                out.append(f'<text class="jlg" x="{cur + sample + gap + tw / 2:.2f}" y="{y:.2f}" font-size="{lf:.2f}" '
                           f'text-anchor="middle">{_esc(word)}</text>')
                cur += sample + gap + tw + fs * 1.4
    out.append('</svg>')
    return ''.join(out)


def _esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


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
