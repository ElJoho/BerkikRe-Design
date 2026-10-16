"""Build AVL models of the Berkirk variants from the sliced sections and run the stability / trim study.

Input:  analysis/avl/sections/<model>.json   (from extract_sections.py, datum of STP/fixed/)
Output: analysis/avl/<model>/<model>.avl     AVL geometry (metres)
        analysis/avl/<model>/af_y###.dat     section airfoils (Selig format, unit chord)
        analysis/avl/results.json            numbers for the report
        Markdown tables on stdout

Placeholders until the real masses are known: 700 g, CG 260 mm behind the nose (plan values).
Usage:  python3 analysis/scripts/avl_build.py [--mass 0.70] [--xcg 260] [--rho 1.225] [--xfoil-cm analysis/avl/xfoil_cm0.json]
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
AVL_DIR = REPO / "analysis" / "avl"
SHORT = {
    "berkirkSiloute": "Base", "berkirkSilouteChangedWings": "CW", "berkirkSilouteReducedTail": "RT",
    "berkirkSilouteReducedTailChangedWings": "RT+CW", "berkirkSilouteConstantCorners": "CC",
    "berkirkSilouteConstantCornersChangedWings": "CC+CW", "berkirkSilouteConstantCornersReducedTail": "CC+RT",
    "berkirkSilouteConstantCornersReducedTailChangedWings": "CC+RT+CW", "contourn": "contourn",
}
Y_MAX_SECTION = 655.0          # mm; outboard of this the winglet fillet distorts the slices
Y_BODY = 75.0                  # mm; inboard of this the section is the centre body + cowl + tail face (clean from 75 in all 9)
ELEVON_T = 5.3                 # mm; the elevon is a 5 mm plate: the hinge is where the section gets this thin
SPEEDS = [10.0, 12.0, 14.0, 16.0, 20.0]
REF_SPEED = 12.0               # m/s; stability derivatives are taken at this trimmed point
G = 9.81


# ---------------------------------------------------------------- sections
def analyse_section(P):
    """LE/TE, chord, incidence and the unit-chord Selig airfoil of one closed loop (x aft, z up, mm)."""
    P = np.asarray(P, float)
    if np.allclose(P[0], P[-1]):
        P = P[:-1]
    xmax = P[:, 0].max()
    te = P[P[:, 0] > xmax - 0.3].mean(axis=0)
    i_le = int(np.argmax(np.hypot(*(P - te).T)))
    le = P[i_le]
    chord = float(np.hypot(*(te - le)))
    inc = float(np.degrees(np.arctan2(le[1] - te[1], te[0] - le[0])))   # + = nose up
    # unit-chord frame: LE at 0, TE at (1, 0)
    ang = np.arctan2(te[1] - le[1], te[0] - le[0])
    R = np.array([[np.cos(-ang), -np.sin(-ang)], [np.sin(-ang), np.cos(-ang)]])
    Q = (P - le) @ R.T / chord
    # start the loop at the most aft point, then go upper surface -> LE -> lower surface
    i_te = int(np.argmax(Q[:, 0]))
    Q = np.roll(Q, -i_te, axis=0)
    i_le2 = int(np.argmin(np.hypot(Q[:, 0], Q[:, 1])))
    if Q[1:i_le2, 1].mean() < 0:                     # first half is the lower surface: reverse
        Q = np.vstack([Q[:1], Q[1:][::-1]])
        i_le2 = int(np.argmin(np.hypot(Q[:, 0], Q[:, 1])))
    Q = np.vstack([Q, Q[:1]])        # close the loop: the flat lower surface ends with a segment back to the TE
    up, lo = Q[: i_le2 + 1], Q[i_le2:]
    ou, ol = np.argsort(up[:, 0]), np.argsort(lo[:, 0])

    def surfaces(xs):
        return np.interp(xs, up[ou, 0], up[ou, 1]), np.interp(xs, lo[ol, 0], lo[ol, 1])

    # thickness along the chord, for the hinge line
    xs = np.linspace(0.002, 0.998, 499)
    zu, zl = surfaces(xs)
    t = (zu - zl) * chord
    i_tmax = int(np.argmax(t))
    thin = np.nonzero(t[i_tmax:] <= ELEVON_T)[0]
    x_hinge = float(xs[i_tmax + thin[0]]) if len(thin) else None
    # smooth airfoil rebuilt from the measured camber line and thickness on a cosine grid. The raw
    # loops have sub-mm corners (rounded wing TE, elevon joint and bevel) that break XFoil's spline
    # and AVL's camber-slope fit.
    xc = 0.5 * (1 - np.cos(np.linspace(0, np.pi, 121)))
    zuc, zlc = surfaces(xc)
    cam, th = (zuc + zlc) / 2, np.maximum(zuc - zlc, 0.0)
    cam -= cam[0] * (1 - xc) + cam[-1] * xc               # chord line through LE and TE exactly
    th[-1] = max(th[-1], 0.0005)
    upper = np.c_[xc, cam + th / 2][::-1]
    lower = np.c_[xc, cam - th / 2][1:]
    return {"le": le, "te": te, "chord": chord, "inc": inc, "airfoil": np.vstack([upper, lower]),
            "t_max": float(t.max()), "x_tmax": float(xs[i_tmax]), "x_hinge": x_hinge,
            "camber_max": float(cam.max()), "x_camber_max": float(xc[np.argmax(cam)]),
            "camber_te": float(np.degrees(np.arctan2(cam[-2] - cam[-1], xc[-1] - xc[-2])))}


def write_dat(path, name, Q):
    with open(path, "w") as f:
        f.write(name + "\n")
        for x, z in Q:
            f.write(f"{x:10.6f} {z:10.6f}\n")


def winglet_sections(slices, z_wing_top):
    """Root / mid / top LE, chord and y of the winglet plate from z-slices (mm)."""
    rows = []
    for s in slices:
        P = np.asarray(s["pts"], float)
        if s["z"] < z_wing_top + 4 or P[:, 1].max() - P[:, 1].min() > 8:   # still in the wing or fillet
            continue
        rows.append((s["z"], P[:, 0].min(), P[:, 0].max() - P[:, 0].min(), P[:, 1].mean()))
    rows = np.array(rows)
    pick = [0, len(rows) // 2, len(rows) - 1]
    return rows[pick], rows


# ---------------------------------------------------------------- AVL model
def build(model, data, xcg, dalpha=None, tag=""):
    """dalpha(y_mm) -> incidence change [deg] (viscous zero-lift angle shift), or None."""
    out = AVL_DIR / model
    out.mkdir(parents=True, exist_ok=True)
    secs = []
    for s in data["wing"]:
        if s["y"] > Y_MAX_SECTION:
            continue
        a = analyse_section(s["pts"])
        a["y"] = float(s["y"])
        a["file"] = f"af_y{s['y']:03d}.dat"
        write_dat(out / a["file"], f"{SHORT[model]} y={s['y']} mm", a["airfoil"])
        secs.append(a)
    # A thin-surface model reads the centre body's cowl / tail-face shape as camber and gives it
    # strong local down-load. Model y < Y_BODY as an extension of the root airfoil instead (real
    # chord and LE kept); the body's own effects go to the base-drag estimate and the CFD.
    root = next(a for a in secs if a["y"] >= Y_BODY)
    for a in secs:
        if a["y"] < Y_BODY:
            a["inc"], a["airfoil"] = root["inc"], root["airfoil"]
            write_dat(out / a["file"], f"{SHORT[model]} y={a['y']:.0f} mm (root airfoil y={root['y']:.0f})",
                      a["airfoil"])
    y_tip = data["bbox"][3]
    # elevon: sections from the first one aft of the kink whose hinge is found
    kink_te = next(a["te"][0] for a in secs if a["y"] >= 285)
    for a in secs:
        a["elevon"] = bool(a["y"] >= 290 and a["x_hinge"] is not None and a["te"][0] > kink_te + 20)

    # reference values: projected planform up to the tip (last section extended to y_tip)
    y = np.array([a["y"] for a in secs] + [y_tip])
    c = np.array([a["chord"] for a in secs] + [secs[-1]["chord"]]) / 1000
    y_m = y / 1000
    S = 2 * np.trapezoid(c, y_m)
    cref = 2 / S * np.trapezoid(c ** 2, y_m)
    b = 2 * y_tip / 1000

    z_top = max(np.asarray(data["wing"][-1]["pts"])[:, 1])
    wl_pick, wl_all = winglet_sections(data["winglet"], z_top)

    L = []
    L += [SHORT[model], "0.0                      | Mach",
          "0 0 0.0                  | iYsym iZsym Zsym",
          f"{S:.5f} {cref:.5f} {b:.5f}  | Sref Cref Bref",
          f"{xcg / 1000:.4f} 0.0 0.0         | Xref Yref Zref (CG)",
          "0.0                      | CDp (profile drag added separately)", "",
          "SURFACE", "Wing", "14 1.0                  | Nchord Cspace (Nspan per section)",
          "YDUPLICATE", "0.0", "ANGLE", "0.0", ""]
    for i, a in enumerate(secs):
        dy = (secs[i + 1]["y"] if i + 1 < len(secs) else y_tip) - a["y"]
        nspan = max(2, round(dy / 8.0))                    # ~8 mm spanwise panels
        L += ["SECTION", f"{a['le'][0] / 1000:.5f} {a['y'] / 1000:.5f} {a['le'][1] / 1000:.5f} "
                         f"{a['chord'] / 1000:.5f} {a['inc'] + (dalpha(a['y']) if dalpha else 0.0):.3f} {nspan} 1.0",
              "AFILE", a["file"]]
        if a["elevon"]:
            L += ["CONTROL", f"elevator 1.0 {a['x_hinge']:.4f} 0 0 0 1.0",
                  "CONTROL", f"aileron 1.0 {a['x_hinge']:.4f} 0 0 0 -1.0"]
        L.append("")
    L += ["SURFACE", "Winglet", "8 1.0 10 1.0", "YDUPLICATE", "0.0", ""]
    for z, xle, ch, yy in wl_pick:
        L += ["SECTION", f"{xle / 1000:.5f} {yy / 1000:.5f} {z / 1000:.5f} {ch / 1000:.5f} 0.0", ""]
    L = [l.split("|")[0].rstrip() if "|" in l else l for l in L]     # AVL has no inline comments
    (out / f"{model}{tag}.avl").write_text("\n".join(L) + "\n")
    hinge = [(a["y"], a["chord"] * (1 - a["x_hinge"])) for a in secs if a["elevon"]]
    return {"S": S, "cref": cref, "b": b, "sections": secs, "winglet": wl_pick.tolist(),
            "winglet_h": float(wl_all[-1][0] - z_top), "elevon_chord": hinge}


# ---------------------------------------------------------------- AVL runs
NUM = r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)"


def run_avl(avl_file, cases):
    """cases: list of OPER command lists; returns the parsed totals of each case."""
    cmds = [f"LOAD {avl_file.name}", "OPER"]
    for c in cases:
        cmds += c + ["X", "ST", ""]        # X runs the case; ST prints forces + derivatives ("" = to screen)
    cmds += ["", "QUIT"]
    r = subprocess.run(["avl"], input="\n".join(cmds) + "\n", capture_output=True, text=True,
                       cwd=avl_file.parent, timeout=600)
    blocks = r.stdout.split("Vortex Lattice Output -- Total Forces")[2::2]   # the ST block of each case
    res = []
    for blk in blocks:
        def get(key):
            m = re.search(r"(?<![A-Za-z0-9])" + re.escape(key) + r"\s*=\s*" + NUM, blk)
            return float(m.group(1)) if m else None
        res.append({"alpha": get("Alpha"), "CL": get("CLtot"), "CDi": get("CDind"), "Cm": get("Cmtot"),
                    "e": get("e"), "elev": get("elevator"), "Xnp": get("Xnp"),
                    "CLa": get("CLa"), "Cma": get("Cma"), "Cnb": get("Cnb"), "Clb": get("Clb"),
                    "Cmd1": get("Cmd01")})
    if len(res) != len(cases):
        raise RuntimeError(f"AVL returned {len(res)} of {len(cases)} cases for {avl_file}:\n{r.stdout[-3000:]}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mass", type=float, default=0.700)
    ap.add_argument("--xcg", type=float, default=260.0, help="mm behind the nose")
    ap.add_argument("--rho", type=float, default=1.225)
    ap.add_argument("--visc", action="store_true",
                    help="apply the XFoil corrections (xfoil.json, xfoil_dcm0.json from xfoil_polars.py)")
    ap.add_argument("--only", nargs="*", help="model names (default: all)")
    args = ap.parse_args()
    dcm0, xf = {}, {}
    if args.visc:
        dcm0 = json.loads((AVL_DIR / "xfoil_dcm0.json").read_text())
        xf = json.loads((AVL_DIR / "xfoil.json").read_text())["models"]
    W = args.mass * G
    results = {}
    for js in sorted((AVL_DIR / "sections").glob("*.json")):
        model = js.stem
        if args.only and model not in args.only:
            continue
        dalpha, tag, dcm = None, "", dcm0.get(model, 0.0)
        if args.visc:
            ok = [r for r in xf[model] if r.get("alpha0") is not None and r.get("alpha0_inv") is not None]
            ys = np.array([r["y"] for r in ok], float)
            # lift ~ (alpha + inc - alpha0): matching the viscous section needs inc + (alpha0_inv - alpha0_visc)
            da = np.array([r["alpha0_inv"] - r["alpha0"] for r in ok])   # - = the viscous section lifts less
            dalpha, tag = (lambda y, ys=ys, da=da: float(np.interp(y, ys, da))), "_visc"
        geo = build(model, json.loads(js.read_text()), args.xcg, dalpha, tag)
        S, cref = geo["S"], geo["cref"]
        avl_file = AVL_DIR / model / f"{model}{tag}.avl"
        cl_v = [2 * W / (args.rho * v ** 2 * S) for v in SPEEDS]
        cases = [["A A 0", "D1 D1 0", "D2 D2 0"],             # spare (alpha 0)
                 ["A C 0", "D1 D1 0"],                        # Cm0 at zero lift
                 [f"A PM {-dcm:.5f}", "D1 D1 0"]]             # trimmed with elevons at 0 (AVL Cm + dcm = 0)
        cases += [[f"A C {cl:.5f}", f"D1 PM {-dcm:.5f}"] for cl in cl_v]   # trim at each speed
        r = run_avl(avl_file, cases)
        ref = r[3 + SPEEDS.index(REF_SPEED)]                  # derivatives at the trimmed reference speed
        xnp = ref["Xnp"] * 1000
        cm0 = r[1]["Cm"] + dcm
        cla, cma, cmd = ref["CLa"], ref["Cma"], ref["Cmd1"]
        cl_trim0 = r[2]["CL"]
        v0 = (2 * W / (args.rho * S * cl_trim0)) ** 0.5 if cl_trim0 > 0 else None
        results[model] = {
            "S_dm2": S * 100, "MAC_mm": cref * 1000, "b_mm": geo["b"] * 1000,
            "winglet_h": geo["winglet_h"], "Xnp_mm": xnp, "SM_pct": (xnp - args.xcg) / (cref * 1000) * 100,
            "CLa": cla, "Cma": cma, "Cm0": cm0, "Cmd_elev": cmd, "Cnb": ref["Cnb"], "Clb": ref["Clb"],
            "dCm0_visc": dcm, "CL_trim0": cl_trim0, "alpha_trim0": r[2]["alpha"], "V_trim0": v0,
            "trim": [{"V": v, "CL": rr["CL"], "alpha": rr["alpha"], "elev": rr["elev"], "CDi": rr["CDi"],
                      "e": rr["e"]} for v, rr in zip(SPEEDS, r[3:])],
            "elevon_chord_mm": [geo["elevon_chord"][0], geo["elevon_chord"][-1]],
            "sections": [{k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in a.items()
                          if k not in ("airfoil",)} for a in geo["sections"]],
        }
    meta = {"mass_kg": args.mass, "xcg_mm": args.xcg, "rho": args.rho, "speeds": SPEEDS,
            "viscous": args.visc}
    tag = "_visc" if args.visc else ""
    (AVL_DIR / f"results{tag}.json").write_text(json.dumps({"meta": meta, "models": results}, indent=1))

    print(f"Mass {args.mass * 1000:.0f} g, CG {args.xcg:.0f} mm behind the nose, rho {args.rho} kg/m³"
          f"{', with XFoil viscous corrections' if args.visc else ', inviscid AVL'}\n")
    print(f"Derivatives at the trimmed {REF_SPEED:.0f} m/s point.\n")
    print("| Model | S [dm²] | MAC [mm] | Xnp [mm] | Static margin [% MAC] | CLα [/rad] | Cmα [/rad] | Cm0 | "
          "Cm_δe [/deg] | Cnβ | Clβ | Trim, elevons 0°: CL / α [°] / V [m/s] |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for m, d in results.items():
        v0 = f"{d['V_trim0']:.1f}" if d["V_trim0"] else "no trim"
        print(f"| {SHORT[m]} | {d['S_dm2']:.2f} | {d['MAC_mm']:.1f} | {d['Xnp_mm']:.1f} | {d['SM_pct']:.1f} | "
              f"{d['CLa']:.3f} | {d['Cma']:.3f} | {d['Cm0']:+.4f} | {d['Cmd_elev']:.5f} | {d['Cnb']:.4f} | "
              f"{d['Clb']:.4f} | {d['CL_trim0']:.3f} / {d['alpha_trim0']:.2f} / {v0} |")
    print("\nElevon angle to trim (+ = trailing edge down) / α [°] at each speed:\n")
    print("| Model | " + " | ".join(f"{v:.0f} m/s" for v in SPEEDS) + " |")
    print("|---|" + "---|" * len(SPEEDS))
    for m, d in results.items():
        print(f"| {SHORT[m]} | " + " | ".join(f"{t['elev']:+.2f} / {t['alpha']:.1f}" for t in d["trim"]) + " |")


if __name__ == "__main__":
    main()
