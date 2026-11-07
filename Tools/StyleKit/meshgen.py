"""Procedural meshes for the stand style kit (pure Python, no unreal import).

Writes OBJ files (centimeters, Z up) that build_smoke_room.py imports.
Every mesh is centered in Y, so the OBJ handedness convention does not matter.

Two primitives cover the whole kit:
  rounded_box - box with rounded edges and corners (outward or inward faces)
  sweep       - a 2D profile swept along a rounded-rectangle contour
                (frames, rings, pedestals, coffers)
"""

import math
import os


# ---------------------------------------------------------------- mesh core

class Mesh:
    def __init__(self):
        self.v = []      # positions
        self.n = []      # normals (one per position)
        self.uv = []     # uvs (one per position)
        self.faces = {}  # material -> list of (i, j, k)

    def add_vertex(self, p, n, uv=(0.0, 0.0)):
        self.v.append(tuple(p))
        self.n.append(_norm(n))
        self.uv.append(tuple(uv))
        return len(self.v) - 1

    def tri(self, mat, a, b, c):
        self.faces.setdefault(mat, []).append((a, b, c))

    def quad(self, mat, a, b, c, d):
        self.tri(mat, a, b, c)
        self.tri(mat, a, c, d)

    def smooth_normals(self, start=0):
        """Recompute normals of vertices >= start from their faces (area weighted)."""
        acc = [[0.0, 0.0, 0.0] for _ in range(len(self.v) - start)]
        for tris in self.faces.values():
            for a, b, c in tris:
                if a < start and b < start and c < start:
                    continue
                fn = _cross(_sub(self.v[b], self.v[a]), _sub(self.v[c], self.v[a]))
                for i in (a, b, c):
                    if i >= start:
                        s = acc[i - start]
                        s[0] += fn[0]; s[1] += fn[1]; s[2] += fn[2]
        for k, s in enumerate(acc):
            if s != [0.0, 0.0, 0.0]:
                self.n[start + k] = _norm(s)

    def transform(self, fn_pos, fn_dir):
        self.v = [fn_pos(p) for p in self.v]
        self.n = [_norm(fn_dir(n)) for n in self.n]

    def write_obj(self, path, header=""):
        lines = ["# " + l for l in header.splitlines()]
        lines += ["v %.4f %.4f %.4f" % p for p in self.v]
        lines += ["vt %.5f %.5f" % t for t in self.uv]
        lines += ["vn %.5f %.5f %.5f" % n for n in self.n]
        # one object, material slots via usemtl only ("g" would make Interchange split meshes)
        for mat, tris in self.faces.items():
            lines.append("usemtl %s" % mat)
            for a, b, c in tris:
                a, b, c = a + 1, b + 1, c + 1
                lines.append("f %d/%d/%d %d/%d/%d %d/%d/%d" % (a, a, a, b, b, b, c, c, c))
        with open(path, "w", newline="\n") as f:
            f.write("\n".join(lines) + "\n")


def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    l = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    return (0.0, 0.0, 1.0) if l < 1e-12 else (a[0] / l, a[1] / l, a[2] / l)


def _box_uv(p, n, scale=0.01):
    ax = max(range(3), key=lambda i: abs(n[i]))
    u, v = [(1, 2), (0, 2), (0, 1)][ax]
    return (p[u] * scale, p[v] * scale)


# ---------------------------------------------------------------- rounded box

def _axis_samples(half, radius, arc_steps, flat_steps):
    """Coordinates along one axis so corner arcs get uniform angular steps."""
    inner = half - radius
    arc = [radius * math.tan(math.radians(45.0 * k / arc_steps)) for k in range(arc_steps + 1)]
    pos = [inner + a for a in arc]                                   # inner .. half
    flat = [-inner + 2 * inner * k / flat_steps for k in range(1, flat_steps)] if inner > 0 else []
    neg = [-x for x in reversed(pos)]
    return neg + flat + pos


def rounded_box(size, radius, mat_fn, inward=False, arc_steps=6, flat_steps=1):
    """size=(X, Y, Z) full extents, centered at the origin.
    mat_fn(center, normal, face) -> material name for each quad; face = (axis, sign) of the cube side it came from."""
    hx, hy, hz = size[0] / 2.0, size[1] / 2.0, size[2] / 2.0
    radius = min(radius, hx, hy, hz)
    inner = (hx - radius, hy - radius, hz - radius)
    samples = [_axis_samples(h, radius, arc_steps, flat_steps) for h in (hx, hy, hz)]
    m = Mesh()

    def project(p, face_n):
        q = tuple(max(-inner[i], min(inner[i], p[i])) for i in range(3))
        d = _sub(p, q)
        if abs(d[0]) + abs(d[1]) + abs(d[2]) < 1e-9:
            return p, face_n
        n = _norm(d)
        return _add(q, _mul(n, radius)), n

    # each face: (normal axis, sign, u axis, v axis) with u x v = outward normal
    faces = [(0, 1, 1, 2), (0, -1, 2, 1), (1, 1, 2, 0), (1, -1, 0, 2), (2, 1, 0, 1), (2, -1, 1, 0)]
    half = (hx, hy, hz)
    for ax, sign, ua, va in faces:
        face_n = [0.0, 0.0, 0.0]; face_n[ax] = float(sign); face_n = tuple(face_n)
        us, vs = samples[ua], samples[va]
        grid = []
        for u in us:
            row = []
            for v in vs:
                p = [0.0, 0.0, 0.0]
                p[ax] = sign * half[ax]; p[ua] = u; p[va] = v
                pos, n = project(tuple(p), face_n)
                if inward:
                    n = _mul(n, -1.0)
                row.append(m.add_vertex(pos, n, _box_uv(pos, n)))
            grid.append(row)
        for i in range(len(us) - 1):
            for j in range(len(vs) - 1):
                a, b, c, d = grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]
                center = _mul(_add(_add(m.v[a], m.v[b]), _add(m.v[c], m.v[d])), 0.25)
                fn = _norm(_add(_add(m.n[a], m.n[b]), _add(m.n[c], m.n[d])))  # faces the visible side
                mat = mat_fn(center, fn, (ax, sign))
                if inward:
                    m.quad(mat, a, d, c, b)
                else:
                    m.quad(mat, a, b, c, d)
    return m


# ---------------------------------------------------------------- sweep

def rounded_rect_contour(w, h, r, arc_steps=10):
    """Closed CCW contour in the XY plane: list of (point, outward normal)."""
    r = min(r, w / 2.0, h / 2.0)
    hx, hy = w / 2.0 - r, h / 2.0 - r
    pts = []
    corners = [(hx, hy, 0), (-hx, hy, 90), (-hx, -hy, 180), (hx, -hy, 270)]
    for cx, cy, a0 in corners:
        for k in range(arc_steps + 1):
            a = math.radians(a0 + 90.0 * k / arc_steps)
            n = (math.cos(a), math.sin(a))
            p = (cx + r * n[0], cy + r * n[1])
            if pts and abs(pts[-1][0][0] - p[0]) < 1e-6 and abs(pts[-1][0][1] - p[1]) < 1e-6:
                continue  # straight edge of zero length (circle)
            pts.append((p, n))
    if abs(pts[-1][0][0] - pts[0][0][0]) < 1e-6 and abs(pts[-1][0][1] - pts[0][0][1]) < 1e-6:
        pts.pop()
    return pts


def arc(center, r, a0, a1, steps=4):
    """Profile arc in (offset, height) space, angles in degrees (0 = +offset, 90 = +height)."""
    return [(center[0] + r * math.cos(math.radians(a0 + (a1 - a0) * k / steps)),
             center[1] + r * math.sin(math.radians(a0 + (a1 - a0) * k / steps))) for k in range(steps + 1)]


def sweep(mesh, contour, parts):
    """parts: list of (material, [(offset, height), ...]).
    offset is along the contour's outward normal, height along +Z.
    Each part is smooth inside and has hard edges against other parts.
    Profile points run so that the surface faces 'left' of the walk direction
    when looking along the contour (outer side walked bottom -> top faces out)."""
    count = len(contour)
    for mat, prof in parts:
        start = len(mesh.v)
        rings = []
        for (c, nrm) in contour:
            ring = []
            for o, z in prof:
                p = (c[0] + nrm[0] * o, c[1] + nrm[1] * o, z)
                ring.append(mesh.add_vertex(p, (nrm[0], nrm[1], 0.0), (0.0, 0.0)))
            rings.append(ring)
        for i in range(count):
            r0, r1 = rings[i], rings[(i + 1) % count]
            for j in range(len(prof) - 1):
                mesh.quad(mat, r0[j], r1[j], r1[j + 1], r0[j + 1])
        mesh.smooth_normals(start)
        for k in range(start, len(mesh.v)):
            mesh.uv[k] = _box_uv(mesh.v[k], mesh.n[k])


def cap(mesh, contour, offset, height, mat, up=True):
    """Flat fill of the contour (convex) at a given offset and height."""
    n = (0.0, 0.0, 1.0 if up else -1.0)
    center = mesh.add_vertex((0.0, 0.0, height), n, (0.0, 0.0))
    ring = []
    for c, nrm in contour:
        p = (c[0] + nrm[0] * offset, c[1] + nrm[1] * offset, height)
        ring.append(mesh.add_vertex(p, n, _box_uv(p, n)))
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        if up:
            mesh.tri(mat, center, a, b)
        else:
            mesh.tri(mat, center, b, a)


# ---------------------------------------------------------------- kit pieces

ROOM = dict(x0=-800.0, x1=800.0, y=650.0, z0=-24.0, z1=540.0, radius=110.0)
BOOTH = dict(back=ROOM["radius"] + 12.0, open_depth=118.0)  # back panel offset from the wall, open part
STAGE = dict(size=440.0, radius=90.0, height=24.0, rim=22.0, groove=8.0)


def room_shell():
    """Inward rounded box: glossy floor slot on the bottom, walls/ceiling elsewhere.
    The floor material is the whole bottom side of the rounded box: it runs up the lower half of
    the coves and its outline follows the rounded room corners on smooth vertex rows."""
    sx = ROOM["x1"] - ROOM["x0"]
    sy = ROOM["y"] * 2
    sz = ROOM["z1"] - ROOM["z0"]

    def mat(center, n, face):
        return "Floor" if face == (2, -1) else "Wall"

    m = rounded_box((sx, sy, sz), ROOM["radius"], mat, inward=True, arc_steps=12, flat_steps=2)
    cx = (ROOM["x0"] + ROOM["x1"]) / 2.0
    cz = (ROOM["z0"] + ROOM["z1"]) / 2.0
    m.transform(lambda p: (p[0] + cx, p[1], p[2] + cz), lambda n: n)
    return m


def booth():
    """Wall-mounted alcove opening to -X (the camera side). Pivot: wall plane, floor level."""
    w, h, r = 440.0, 480.0, 70.0
    lip, frame = 7.0, 42.0
    # the sides run back to the wall, the dark back panel sits in front of the floor cove,
    # so the room's rounded wall/floor joint never shows inside the alcove
    back = BOOTH["back"]
    depth = back + BOOTH["open_depth"]
    contour = rounded_rect_contour(w, h, r, arc_steps=12)
    prof = [(0.0, 0.0), (0.0, depth - lip)]
    prof += arc((-lip, depth - lip), lip, 0, 90, 5)[1:]
    prof += [(-(frame - lip), depth)]
    prof += arc((-(frame - lip), depth - lip), lip, 90, 180, 5)[1:]
    prof += [(-frame, back)]
    m = Mesh()
    sweep(m, contour, [("Frame", prof)])
    cap(m, contour, -frame, back, "Back", up=True)
    # sweep axis +Z -> world -X (out of the wall), contour X -> world -Y, contour Y -> world Z (+ h/2)
    # (a proper rotation, so triangle winding stays valid)
    m.transform(lambda p: (-p[2], -p[0], p[1] + h / 2.0), lambda n: (-n[2], -n[0], n[1]))
    return m


def pedestal():
    """Round vent pedestal: accent ring at the base, dark body, glowing vent recess. Top at Z=32."""
    R = 50.0
    contour = rounded_rect_contour(2 * R, 2 * R, R, arc_steps=16)
    ring = [(2.0, 0.0), (2.0, 5.0)] + arc((-1.0, 5.0), 3.0, 0, 90, 4)[1:] + [(-16.0, 8.0)]
    body = [(-14.0, 7.0), (-14.0, 28.0)] + arc((-18.0, 28.0), 4.0, 0, 90, 4)[1:] + [(-28.0, 32.0)]
    body += arc((-28.0, 30.0), 2.0, 90, 180, 3)[1:] + [(-30.0, 24.0)]
    m = Mesh()
    sweep(m, contour, [("Ring", ring), ("Body", body)])
    cap(m, contour, -30.0, 24.0, "Glow", up=True)
    return m


def ceiling_light(w=640.0, h=600.0, r=110.0, frame=70.0):
    """Recessed light coffer: emissive panel w x h, dark frame around it.
    Pivot at the ceiling plane, hangs 30 cm down (-Z)."""
    contour = rounded_rect_contour(w, h, r, arc_steps=12)
    # built upside down (+Z = down), flipped at the end
    prof = [(frame, 0.0), (frame, 18.0)] + arc((frame - 12.0, 18.0), 12.0, 0, 90, 4)[1:]
    prof += [(12.0, 30.0)] + arc((12.0, 18.0), 12.0, 90, 180, 4)[1:] + [(0.0, 4.0)]
    m = Mesh()
    sweep(m, contour, [("Frame", prof)])
    cap(m, contour, 0.0, 4.0, "Panel", up=True)
    m.transform(lambda p: (p[0], -p[1], -p[2]), lambda n: (n[0], -n[1], -n[2]))
    return m


def stage():
    """Central dais: dark glossy body, glowing groove along the top edge, marked top (own material).
    Pivot at the bottom center, top at Z=height."""
    s, r, h = STAGE["size"], STAGE["radius"], STAGE["height"]
    rim, groove = STAGE["rim"], STAGE["groove"]
    contour = rounded_rect_contour(s, s, r, arc_steps=14)
    body = [(0.0, 0.0), (0.0, h - 6.0)] + arc((-6.0, h - 6.0), 6.0, 0, 90, 4)[1:]
    body += [(-rim, h), (-rim, h - 3.0)]
    glow = [(-rim, h - 3.0), (-(rim + groove), h - 3.0)]
    inner = [(-(rim + groove), h - 3.0), (-(rim + groove), h)]
    m = Mesh()
    sweep(m, contour, [("Body", body), ("Glow", glow), ("Body", inner)])
    cap(m, contour, -(rim + groove), h, "Top", up=True)
    return m


def soft_box(size, radius, mat="Surface", arc_steps=4):
    """Rounded box sitting on Z=0."""
    m = rounded_box(size, radius, lambda c, n, f: mat, arc_steps=arc_steps)
    m.transform(lambda p: (p[0], p[1], p[2] + size[2] / 2.0), lambda n: n)
    return m


PIECES = {
    "SM_Style_RoomShell": (room_shell, "Inward room shell %(x0)s..%(x1)s x +-%(y)s x %(z0)s..%(z1)s cm, cove radius %(radius)s" % ROOM),
    "SM_Style_Booth": (booth, "Wall alcove 440x480 cm, 130 cm deep, 42 cm frame, opens to -X, pivot at wall/floor"),
    "SM_Style_Stage": (stage, "Central dais %(size)sx%(size)s cm, %(height)s cm high, glowing groove, marked top" % STAGE),
    "SM_Style_Pedestal": (pedestal, "Vent pedestal R50, accent ring, glowing vent, top at Z=32"),
    "SM_Style_CeilingLight": (ceiling_light, "Recessed ceiling light, panel 640x600 cm, hangs 30 cm below pivot"),
    "SM_Style_CeilingBar": (lambda: ceiling_light(140.0, 520.0, 50.0, 40.0),
                            "Recessed ceiling light bar, panel 140x520 cm, hangs 30 cm below pivot"),
    "SM_Style_Crate": (lambda: soft_box((180.0, 110.0, 100.0), 10.0), "Rounded crate 180x110x100 cm on Z=0"),
    "SM_Style_Banner": (lambda: soft_box((1300.0, 16.0, 230.0), 6.0), "Wall banner panel 1300x16x230 cm on Z=0"),
    "SM_Style_Strip": (lambda: soft_box((100.0, 100.0, 100.0), 2.0, arc_steps=2), "1 m rounded cube, scaled into light strips"),
}


def write_all(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for name, (fn, desc) in PIECES.items():
        path = os.path.join(out_dir, name + ".obj")
        fn().write_obj(path, "%s: %s\nGenerated by Tools/StyleKit/meshgen.py" % (name, desc))
        written.append(path)
    return written


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", "DCC")
    for p in write_all(os.path.abspath(target)):
        print(p)
