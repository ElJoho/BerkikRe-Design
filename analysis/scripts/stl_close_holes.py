"""Close small holes in binary STLs (in place) by fan-filling each boundary loop.

OpenCASCADE leaves a few sub-millimetre gaps where it tessellates the tiny fillet
faces at the winglet root, so some files written by step_fix_align.py aren't
watertight. Each open loop is filled with a fan of triangles around its centroid,
oriented to match the surrounding surface.

    python3 analysis/scripts/stl_close_holes.py STL/cfd/*.stl
"""
import sys
from collections import Counter, defaultdict

import numpy as np

DTYPE = np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("a", "<u2")])


def read(path):
    data = open(path, "rb").read()
    n = int(np.frombuffer(data, "<u4", 1, 80)[0])
    tri = np.frombuffer(data, DTYPE, n, 84)
    P, inv = np.unique(tri["v"].reshape(-1, 3), axis=0, return_inverse=True)
    return P.astype(np.float64), inv.reshape(-1, 3)


def write(path, P, F):
    v = P[F]
    nrm = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-30)
    out = np.zeros(len(F), DTYPE)
    out["n"], out["v"] = nrm, v
    with open(path, "wb") as f:
        f.write(b"Berkirk CFD surface, mm".ljust(80, b"\0"))
        f.write(np.uint32(len(F)).tobytes())
        f.write(out.tobytes())


def directed_edges(F):
    return np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])


def check(F):
    """Return (open edges, edges used >2 times, edges with the same direction twice)."""
    E = directed_edges(F)
    und = Counter(map(tuple, np.sort(E, axis=1)))
    dirc = Counter(map(tuple, E))
    return (sum(1 for c in und.values() if c == 1), sum(1 for c in und.values() if c > 2),
            sum(1 for c in dirc.values() if c > 1))


def volume(P, F):
    v = P[F]
    return np.einsum("ij,ij->i", v[:, 0], np.cross(v[:, 1], v[:, 2])).sum() / 6.0


for path in sys.argv[1:]:
    P, F = read(path)
    E = directed_edges(F)
    und = Counter(map(tuple, np.sort(E, axis=1)))
    # boundary edges, kept in the direction their face uses them
    nxt = defaultdict(list)
    for a, b in E:
        if und[(min(a, b), max(a, b))] == 1:
            nxt[a].append(b)
    if not nxt:
        print(f"{path}: already closed, {len(F)} triangles")
        continue
    loops, used = [], set()
    for start in list(nxt):
        for b0 in nxt[start]:
            if (start, b0) in used:
                continue
            loop, a, b = [start], start, b0
            while True:
                used.add((a, b))
                if b == start:
                    break
                loop.append(b)
                cand = [c for c in nxt[b] if (b, c) not in used]
                if not cand:
                    loop = None
                    break
                a, b = b, cand[0]
            if loop:
                loops.append(loop)
    v0 = volume(P, F)
    newP, newF = [P], [F]
    nP = len(P)
    for loop in loops:
        c = P[loop].mean(axis=0)
        newP.append(c[None])
        ring = loop + [loop[0]]
        # boundary edge a->b belongs to a face; the fill face must use b->a
        newF.append(np.array([[ring[i + 1], ring[i], nP] for i in range(len(loop))]))
        nP += 1
    P2, F2 = np.vstack(newP), np.vstack(newF)
    open_e, nonman, flipped = check(F2)
    write(path, P2, F2)
    print(f"{path}: {len(loops)} loops ({sum(map(len, loops))} edges) filled; "
          f"open {open_e}, non-manifold {nonman}, flipped {flipped}; "
          f"volume {v0 / 1e6:.4f} -> {volume(P2, F2) / 1e6:.4f} L; {len(F2)} triangles")
