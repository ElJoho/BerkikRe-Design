#!/usr/bin/env python3
"""Measure the Berkirk 3 STL variants: mesh health, planform, sections and comparison figures."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
STL_DIR = REPO / "STL"
FIG_DIR = REPO / "analysis" / "figures"
PIXEL_MM = 0.25
STATIONS = [0, 60, 150, 250, 350, 450, 550, 640]
MODELS = {
    "berkirkSiloute": "Base",
    "berkirkSilouteChangedWings": "CW",
    "berkirkSilouteReducedTail": "RT",
    "berkirkSilouteReducedTailChangedWings": "RT+CW",
    "berkirkSilouteConstantCorners": "CC",
    "berkirkSilouteConstantCornersChangedWings": "CC+CW",
    "berkirkSilouteConstantCornersReducedTail": "CC+RT",
    "berkirkSilouteConstantCornersReducedTailChangedWings": "CC+RT+CW",
    "contourn": "contourn",
}


def load(path):
    data = path.read_bytes()
    n = int(np.frombuffer(data, "<u4", 1, 80)[0])
    tri = np.frombuffer(data, np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("a", "<u2")]), n, 84)
    verts, inv = np.unique(tri["v"].reshape(-1, 3), axis=0, return_inverse=True)
    P = verts.astype(np.float64)
    F = inv.reshape(-1, 3)
    cr = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    return {"P": P, "F": F, "cr": cr, "stored_n": tri["n"].astype(np.float64), "size_ok": len(data) == 84 + 50 * n}


def count_shells(nv, E):
    lab = np.arange(nv)
    while True:
        m = np.minimum(lab[E[:, 0]], lab[E[:, 1]])
        new = lab.copy()
        np.minimum.at(new, E[:, 0], m)
        np.minimum.at(new, E[:, 1], m)
        while not np.array_equal(new[new], new):
            new = new[new]
        if np.array_equal(new, lab):
            return len(np.unique(lab))
        lab = new


def mesh_health(m):
    P, F, cr = m["P"], m["F"], m["cr"]
    n = len(F)
    area = 0.5 * np.linalg.norm(cr, axis=1)
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    Es = np.sort(E, axis=1)
    key = Es[:, 0].astype(np.int64) * len(P) + Es[:, 1]
    order = np.argsort(key, kind="stable")
    _, first, count = np.unique(key[order], return_index=True, return_counts=True)
    _, dcount = np.unique(E[:, 0].astype(np.int64) * len(P) + E[:, 1], return_counts=True)
    pair = first[count == 2]
    na, nb = cr[order[pair] % n], cr[order[pair + 1] % n]
    cosang = np.einsum("ij,ij->i", na, nb) / np.maximum(np.linalg.norm(na, axis=1) * np.linalg.norm(nb, axis=1), 1e-30)
    dihedral = np.degrees(np.arccos(np.clip(cosang, -1, 1)))
    L = np.linalg.norm(P[F[:, [1, 2, 0]]] - P[F], axis=2)
    quality = 4 * np.sqrt(3) * area / np.maximum((L**2).sum(1), 1e-30)
    v0, v1, v2 = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    return {
        "tris": n, "verts": len(P), "shells": count_shells(len(P), E),
        "open": int((count == 1).sum()), "nonmanifold": int((count > 2).sum()), "flipped": int((dcount > 1).sum()),
        "degenerate": int((area < 1e-10).sum()),
        "normals_ok": float((np.einsum("ij,ij->i", m["stored_n"], cr) > 0).mean()),
        "sliver": float((quality < 0.1).mean()), "max_edge": float(L.max()),
        "dih90": float(np.percentile(dihedral, 90)), "dih99": float(np.percentile(dihedral, 99)),
        "wetted": float(area.sum()), "volume": float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6),
    }


def slice_loops(P, F, axis, val):
    s = P[:, axis] - val
    s = np.where(np.abs(s) < 1e-7, 1e-7, s)
    pos = s > 0
    c = pos[F].sum(1)
    T = F[(c == 1) | (c == 2)]
    S = pos[T]
    ea, eb = np.array([0, 1, 2]), np.array([1, 2, 0])
    k = np.argsort(~(S[:, ea] != S[:, eb]), axis=1, kind="stable")[:, :2]
    rows = np.arange(len(T))
    N = len(P)

    def edge_key(col):
        a, b = T[rows, ea[col]], T[rows, eb[col]]
        return np.minimum(a, b).astype(np.int64) * N + np.maximum(a, b)

    k1, k2 = edge_key(k[:, 0]), edge_key(k[:, 1])
    keys = np.unique(np.concatenate([k1, k2]))
    ka, kb = keys // N, keys % N
    t = s[ka] / (s[ka] - s[kb])
    pts = P[ka] + (P[kb] - P[ka]) * t[:, None]
    adj = [[] for _ in range(len(keys))]
    for u, v in zip(np.searchsorted(keys, k1), np.searchsorted(keys, k2)):
        adj[u].append(v)
        adj[v].append(u)
    seen = np.zeros(len(keys), bool)
    loops = []
    for start in range(len(keys)):
        if seen[start]:
            continue
        loop, prev, cur = [start], -1, start
        seen[start] = True
        while True:
            nb = adj[cur]
            nxt = nb[0] if nb[0] != prev else (nb[1] if len(nb) > 1 else -1)
            if nxt < 0 or nxt == start or seen[nxt]:
                break
            loop.append(nxt)
            seen[nxt] = True
            prev, cur = cur, nxt
        loops.append(pts[loop])
    return loops


def section_at(m, x):
    # small offset keeps the cutting plane off mesh vertices
    return max(slice_loops(m["P"], m["F"], 0, x + 0.0137), key=len)


def section_props(loop):
    y, z = loop[:, 1], loop[:, 2]
    te_mask = y < y.min() + 0.3
    te = np.array([y.min(), z[te_mask].mean()])
    ile = int(np.argmax(np.hypot(y - te[0], z - te[1])))
    le = np.array([y[ile], z[ile]])
    cvec = le - te
    c = float(np.linalg.norm(cvec))
    ch = cvec / c
    nrm = np.array([-ch[1], ch[0]])
    if nrm[1] < 0:
        nrm = -nrm
    rel = np.stack([y - le[0], z - le[1]], 1)
    u = -(rel @ ch) / c
    w = (rel @ nrm) / c
    ite = int(np.argmin(np.abs(u - 1) + 10 * (~te_mask)))
    n = len(loop)
    a = [(ile + i) % n for i in range((ite - ile) % n + 1)]
    b = [(ile - i) % n for i in range((ile - ite) % n + 1)]
    up, lo = (a, b) if w[a].mean() > w[b].mean() else (b, a)
    g = np.linspace(0, 1, 401)

    def on_grid(idx):
        o = np.argsort(u[idx])
        return np.interp(g, u[idx][o], w[idx][o])

    wu, wl = on_grid(up), on_grid(lo)
    th, cam = wu - wl, 0.5 * (wu + wl)
    return {
        "c": c, "inc": float(np.degrees(np.arctan2(cvec[1], cvec[0]))),
        "tc": float(th.max()), "xt": float(g[th.argmax()]), "camber": float(cam.max()), "xc": float(g[cam.argmax()]),
        "te_slope": float(np.polyfit(g[g > 0.9], cam[g > 0.9], 1)[0]),
        "te_mm": float(th[np.searchsorted(g, 0.97)] * c), "npts": n, "g": g, "wu": wu, "wl": wl,
    }


def elevon(m, step=2.0):
    # elevons are 5 mm flat plates aft of the wing TE; a slice shows them as a separate thin loop
    xs = np.arange(270, m["P"][:, 0].max(), step)
    chord = np.zeros(len(xs))
    for i, x in enumerate(xs):
        loops = [L for L in slice_loops(m["P"], m["F"], 0, x + 0.0137)
                 if len(L) > 8 and np.ptp(L[:, 1]) > 20 and abs(np.ptp(L[:, 2]) - 5) < 0.3]
        chord[i] = max((np.ptp(L[:, 1]) for L in loops), default=0)
    on = xs[chord > 0]
    if not len(on):
        return None
    return {"x0": on.min(), "x1": on.max(), "c_max": chord.max(), "c_min": chord[chord > 0].min(),
            "S_pair": 2 * chord.sum() * step}


def raster(P, F, ia, ib):
    a, b = P[:, ia], P[:, ib]
    a0, b0 = a.min(), b.min()
    size = (int(np.ceil((a.max() - a0) / PIXEL_MM)) + 3, int(np.ceil((b.max() - b0) / PIXEL_MM)) + 3)
    img = Image.new("1", size, 0)
    draw = ImageDraw.Draw(img)
    A = (a[F] - a0) / PIXEL_MM + 1
    B = (b[F] - b0) / PIXEL_MM + 1
    for i in range(len(F)):
        draw.polygon([(A[i, 0], B[i, 0]), (A[i, 1], B[i, 1]), (A[i, 2], B[i, 2])], fill=1)
    return np.array(img, dtype=bool), a0, b0


def planform(m):
    P, F, cr = m["P"], m["F"], m["cr"]
    top, x0, y0 = raster(P, F, 0, 1)
    xs = x0 + (np.arange(top.shape[1]) - 0.5) * PIXEL_MM
    filled = top.any(0)
    yle = y0 + (top.shape[0] - 1 - np.argmax(top[::-1], axis=0) - 0.5) * PIXEL_MM
    yte = y0 + (np.argmax(top, axis=0) - 0.5) * PIXEL_MM
    chord = top.sum(0) * PIXEL_MM
    tip = P[:, 0].max()
    nose = P[:, 1].max()
    wing = filled & (np.abs(xs) < tip - 8)
    s_wing = chord[wing].sum() * PIXEL_MM
    mac = (chord[wing] ** 2).sum() * PIXEL_MM / s_wing
    yle_mac = (chord[wing] * yle[wing]).sum() * PIXEL_MM / s_wing
    front, _, _ = raster(P, F, 0, 2)
    nrm = cr / np.linalg.norm(cr, axis=1, keepdims=True)
    aft_face = (nrm[:, 1] < -0.95) & (np.abs(P[F][:, :, 0]).max(1) < 120)
    winglet_z = P[np.abs(P[:, 0]) > tip - 12, 2]

    def at(x):
        i = int(np.argmin(np.abs(xs - x)))
        return nose - yle[i], chord[i]

    def sweep(xa, xb, yy):
        sel = filled & (xs > xa) & (xs < xb)
        return float(np.degrees(np.arctan(-np.polyfit(xs[sel], yy[sel], 1)[0])))

    return {
        "S": top.sum() * PIXEL_MM**2, "b": tip - P[:, 0].min(), "mac": mac,
        "y_mac": (chord[wing] * np.abs(xs[wing])).sum() * PIXEL_MM / s_wing,
        "mac_le_from_nose": nose - yle_mac, "qmac_from_nose": nose - (yle_mac - 0.25 * mac),
        "front": front.sum() * PIXEL_MM**2, "tail_face": float(0.5 * np.linalg.norm(cr[aft_face], axis=1).sum()),
        "winglet_h": float(winglet_z.max() - winglet_z.min()), "zmin": P[:, 2].min(), "nose_y": nose,
        "root": at(0), "kink": at(290), "tip": at(655),
        "le_sweep_in": sweep(95, 280, yle), "le_sweep_out": sweep(300, 640, yle),
        "te_sweep_in": sweep(95, 280, yte), "te_sweep_out": sweep(300, 640, yte),
    }


def render(ax, m, view, title):
    P, F, cr = m["P"], m["F"], m["cr"]
    if view == "top":
        R = np.eye(3)
    elif view == "front":
        R = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)
    elif view == "side":
        R = np.array([[0, 1, 0], [0, 0, 1], [1, 0, 0]], float)
    else:
        az, el = np.radians(-35), np.radians(30)
        Rz = np.array([[np.cos(az), -np.sin(az), 0], [np.sin(az), np.cos(az), 0], [0, 0, 1]])
        Rx = np.array([[1, 0, 0], [0, np.cos(el), -np.sin(el)], [0, np.sin(el), np.cos(el)]])
        R = Rx @ Rz
        R = np.array([R[0], R[2], -R[1]])
    Q = P @ R.T
    N = (cr / np.maximum(np.linalg.norm(cr, axis=1, keepdims=True), 1e-30)) @ R.T
    light = np.array([0.3, 0.5, 0.81]) / np.linalg.norm([0.3, 0.5, 0.81])
    shade = 0.25 + 0.75 * np.abs(N @ light)
    o = np.argsort(Q[F][:, :, 2].mean(1))
    colors = np.clip(np.stack([shade[o] * 0.55, shade[o] * 0.70, shade[o] * 0.95], 1), 0, 1)
    ax.add_collection(PolyCollection(Q[F][o][:, :, :2], facecolors=colors, edgecolors="none", antialiased=False))
    ax.set_xlim(Q[:, 0].min() - 10, Q[:, 0].max() + 10)
    ax.set_ylim(Q[:, 1].min() - 10, Q[:, 1].max() + 10)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=9)
    ax.tick_params(labelsize=6)


def save_figures(meshes):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for view in ("top", "iso", "side", "front"):
        fig, axs = plt.subplots(3, 3, figsize=(15, 9 if view != "front" else 5))
        for ax, (name, short) in zip(axs.flat, MODELS.items()):
            render(ax, meshes[name], view, f"{short}  ({name})")
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"views_{view}.png", dpi=110)
        plt.close(fig)

    compare = {"berkirkSiloute": "C0", "berkirkSilouteChangedWings": "C1",
               "berkirkSilouteConstantCorners": "C2", "contourn": "C3"}
    fig, axs = plt.subplots(len(STATIONS), 1, figsize=(13, 2.3 * len(STATIONS)))
    for ax, x in zip(axs, STATIONS):
        for name, col in compare.items():
            loop = section_at(meshes[name], x)
            loop = np.vstack([loop, loop[:1]])
            zb = meshes[name]["P"][:, 2].min()
            ax.plot(loop[:, 1], loop[:, 2] - zb, "-", color=col, lw=0.9, label=MODELS[name])
        ax.set_aspect("equal")
        ax.set_title(f"section at x = {x} mm from the centreline (nose to the right; z from each model's bottom)", fontsize=8)
        ax.tick_params(labelsize=6)
        ax.legend(fontsize=6, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "sections_compare.png", dpi=100)
    plt.close(fig)

    fig, axs = plt.subplots(2, 2, figsize=(14, 6))
    for ax, x in zip(axs.flat, [150, 350, 550, 640]):
        for name, col in compare.items():
            sp = section_props(section_at(meshes[name], x))
            ax.plot(sp["g"], sp["wu"], color=col, lw=0.9, label=MODELS[name])
            ax.plot(sp["g"], sp["wl"], color=col, lw=0.9)
            ax.plot(sp["g"], 0.5 * (sp["wu"] + sp["wl"]), "--", color=col, lw=0.6)
        ax.set_aspect("equal")
        ax.set_title(f"normalised section at x = {x} mm (x/c from the leading edge, dashed = camber line)", fontsize=8)
        ax.legend(fontsize=6)
        ax.tick_params(labelsize=6)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "sections_normalised.png", dpi=100)
    plt.close(fig)

    fig, axs = plt.subplots(2, 1, figsize=(14, 9))
    for (name, short), col in zip(MODELS.items(), [f"C{i}" for i in range(8)] + ["k"]):
        P, F = meshes[name]["P"], meshes[name]["F"]
        zb, yn, tip = P[:, 2].min(), P[:, 1].max(), P[:, 0].max()
        side = P[F[P[F][:, :, 0].min(1) > tip - 15]]
        axs[0].add_collection(PolyCollection(np.stack([side[:, :, 1] - yn, side[:, :, 2] - zb], -1),
                                             facecolors="none", edgecolors=col, lw=0.15, alpha=0.6))
        axs[0].plot([], [], color=col, label=short)
        front = P[F[P[F][:, :, 0].min(1) > tip - 60]]
        axs[1].add_collection(PolyCollection(np.stack([front[:, :, 0] - tip, front[:, :, 2] - zb], -1),
                                             facecolors="none", edgecolors=col, lw=0.15, alpha=0.6))
    for ax in axs:
        ax.autoscale()
        ax.set_aspect("equal")
    axs[0].legend(fontsize=7)
    axs[0].set_title("winglet / tip region, side view (y from the nose, z from the bottom)")
    axs[1].set_title("winglet / tip region, front view (x from the tip, z from the bottom)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "winglets.png", dpi=100)
    plt.close(fig)


def main():
    meshes = {name: load(STL_DIR / f"{name}.stl") for name in MODELS}
    health = {name: mesh_health(m) for name, m in meshes.items()}
    plan = {name: planform(m) for name, m in meshes.items()}

    print("## Mesh health\n")
    print("| Model | Triangles | Shells | Open edges | Non-manifold | Flipped | Degenerate | Normals OK | Slivers | Max edge [mm] | Facet angle p90/p99 [deg] |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, h in health.items():
        print(f"| {MODELS[name]} | {h['tris']} | {h['shells']} | {h['open']} | {h['nonmanifold']} | {h['flipped']} | "
              f"{h['degenerate']} | {100 * h['normals_ok']:.0f}% | {100 * h['sliver']:.0f}% | {h['max_edge']:.0f} | "
              f"{h['dih90']:.1f} / {h['dih99']:.1f} |")

    print("\n## Planform and global geometry\n")
    print("| Model | S [dm²] | b [mm] | AR | MAC [mm] | MAC at y [mm] | MAC LE / 25% MAC from nose [mm] | Frontal [cm²] | "
          "Tail face [cm²] | Wetted [dm²] | Volume [L] | Winglet h [mm] | Bottom z [mm] | Nose y [mm] |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, p in plan.items():
        h = health[name]
        print(f"| {MODELS[name]} | {p['S'] / 1e4:.2f} | {p['b']:.0f} | {p['b'] ** 2 / p['S']:.2f} | {p['mac']:.1f} | "
              f"{p['y_mac']:.0f} | {p['mac_le_from_nose']:.0f} / {p['qmac_from_nose']:.0f} | {p['front'] / 100:.0f} | "
              f"{p['tail_face'] / 100:.1f} | {h['wetted'] / 1e4:.2f} | {h['volume'] / 1e6:.3f} | {p['winglet_h']:.1f} | "
              f"{p['zmin']:.2f} | {p['nose_y']:.2f} |")

    print("\n## Planform breakpoints (LE distance behind the nose, chord) and sweep\n")
    print("| Model | Root x=0 | Kink x=290 | Tip x=655 | LE sweep in/out [deg] | TE sweep in/out [deg] |")
    print("|---|---|---|---|---|---|")
    for name, p in plan.items():
        f = lambda v: f"{np.round(v[0]) + 0.0:.0f} / {v[1]:.0f}"
        print(f"| {MODELS[name]} | {f(p['root'])} | {f(p['kink'])} | {f(p['tip'])} | "
              f"{p['le_sweep_in']:.1f} / {p['le_sweep_out']:.1f} | {p['te_sweep_in']:.1f} / {p['te_sweep_out']:.1f} |")

    print("\n## Elevons (separate 5 mm loop aft of the wing TE; '-' = fused into the wing loop, not separable)\n")
    print("| Model | Span x from / to [mm] | Chord max / min [mm] | Area, both [dm²] |")
    print("|---|---|---|---|")
    for name, m in meshes.items():
        e = elevon(m)
        print(f"| {MODELS[name]} | " + ("- | - | - |" if e is None else
              f"{e['x0']:.0f} / {e['x1']:.0f} | {e['c_max']:.1f} / {e['c_min']:.1f} | {e['S_pair'] / 1e4:.2f} |"))

    print("\n## Sections (x = distance from the centreline)\n")
    print("| Model | x [mm] | Chord [mm] | Incidence [deg] | t/c [%] @ x/c | Camber [%] @ x/c | Camber slope near TE | TE thickness [mm] | Points |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, m in meshes.items():
        for x in STATIONS:
            sp = section_props(section_at(m, x))
            print(f"| {MODELS[name]} | {x} | {sp['c']:.1f} | {sp['inc']:.2f} | {100 * sp['tc']:.1f} @ {sp['xt']:.2f} | "
                  f"{100 * sp['camber']:.2f} @ {sp['xc']:.2f} | {sp['te_slope']:.3f} | {sp['te_mm']:.1f} | {sp['npts']} |")

    save_figures(meshes)
    print(f"\nFigures written to {FIG_DIR}")


if __name__ == "__main__":
    main()
