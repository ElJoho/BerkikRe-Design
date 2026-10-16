"""XFoil polars of the Berkirk section airfoils (written by avl_build.py) and the viscous corrections for AVL.

For each model and station: a viscous polar at the Reynolds number of the reference speed and an
inviscid Cm0. AVL only sees the camber line, so the difference (viscous - inviscid Cm0) is integrated
over the span as a correction to the aircraft Cm0. The polars also give CLmax and profile drag.

Output: analysis/avl/<model>/polar_y###.txt, analysis/avl/xfoil.json, analysis/avl/xfoil_dcm0.json
Usage:  python3 analysis/scripts/xfoil_polars.py [--v 12] [--rho 1.225]
Run avl_build.py first (it writes the airfoil files and results.json with the section chords).
"""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
AVL_DIR = REPO / "analysis" / "avl"
STATIONS = [75, 110, 150, 200, 250, 285, 320, 400, 500, 600, 645]
MU = 1.81e-5


def xfoil(cmds, cwd):
    # no PLOP/G F: it crashes the Ubuntu 6.99 build (SIGFPE); results are read from polar files
    try:
        r = subprocess.run(["xfoil"], input="\n".join(cmds + ["", "QUIT"]) + "\n",
                           capture_output=True, text=True, cwd=cwd, timeout=60)
        return r.stdout
    except subprocess.TimeoutExpired:          # hung on a non-converging point: keep what the polar file has
        return ""


def read_polar(path):
    rows = []
    for line in Path(path).read_text().splitlines():
        p = line.split()
        if len(p) >= 7:
            try:
                rows.append([float(v) for v in p[:7]])
            except ValueError:
                pass
    return np.array(rows).reshape(-1, 7)        # alpha CL CD CDp CM Top_Xtr Bot_Xtr


def cm_at_cl0(alpha, cl, cm):
    o = np.argsort(cl)
    return float(np.interp(0.0, cl[o], cm[o])) if cl.min() < 0 < cl.max() else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v", type=float, default=12.0, help="reference speed for the Reynolds number [m/s]")
    ap.add_argument("--rho", type=float, default=1.225)
    args = ap.parse_args()
    res = json.loads((AVL_DIR / "results.json").read_text())["models"]
    out, dcm0 = {}, {}
    for model, d in res.items():
        secs = {s["y"]: s for s in d["sections"]}
        rows = []
        for y in STATIONS:
            s = secs.get(float(y))
            if s is None:
                continue
            c = s["chord"] / 1000
            re_ = args.rho * args.v * c / MU
            af = s["file"]
            pol = f"polar_y{y:03d}.txt"
            (AVL_DIR / model / pol).unlink(missing_ok=True)
            base = [f"LOAD {af}", "PPAR", "N 220", "", "", "OPER", "ITER 150"]
            xfoil(base + [f"VISC {re_:.0f}", "PACC", pol, "", "ASEQ 0 -6 -0.5", "INIT", "ASEQ 0.5 14 0.5", "PACC"],
                  AVL_DIR / model)
            P = read_polar(AVL_DIR / model / pol)
            print(f"  {model} y={y}: {len(P)} viscous points", flush=True)
            ipol = f"polar_inv_y{y:03d}.txt"          # inviscid run prints nothing on this build: use PACC
            (AVL_DIR / model / ipol).unlink(missing_ok=True)
            xfoil(base + ["PACC", ipol, "", "ASEQ -8 4 1", "PACC"], AVL_DIR / model)
            Pi = read_polar(AVL_DIR / model / ipol)
            cm0_inv = cm_at_cl0(None, Pi[:, 1], Pi[:, 4]) if len(Pi) >= 2 else None
            a0_inv = cm_at_cl0(None, Pi[:, 1], Pi[:, 0]) if len(Pi) >= 2 else None   # alpha at CL = 0
            if len(P) < 6:
                rows.append({"y": y, "chord": s["chord"], "Re": re_, "ok": False})
                continue
            P = P[np.argsort(P[:, 0])]
            al, cl, cd, cm = P[:, 0], P[:, 1], P[:, 2], P[:, 4]
            cm0_v = cm_at_cl0(al, cl, cm)
            rows.append({"y": y, "chord": s["chord"], "Re": re_, "ok": True, "n": int(len(P)),
                         "alpha0": float(np.interp(0, cl, al)) if cl.min() < 0 < cl.max() else None,
                         "CLmax": float(cl.max()), "alpha_CLmax": float(al[np.argmax(cl)]),
                         "CDmin": float(cd.min()), "CL_CDmin": float(cl[np.argmin(cd)]),
                         "Cm0_visc": cm0_v, "Cm0_inv": cm0_inv, "alpha0_inv": a0_inv,
                         "dCm0": (cm0_v - cm0_inv) if (cm0_v is not None and cm0_inv is not None) else None,
                         "polar": P[:, [0, 1, 2, 4]].round(5).tolist()})
        out[model] = rows
        (AVL_DIR / model / ":00.bl").unlink(missing_ok=True)     # boundary-layer dump XFoil leaves behind
        # spanwise integration of the Cm0 change, weighted by c² (about each section's c/4)
        ok = [r for r in rows if r.get("dCm0") is not None]
        if len(ok) >= 3:
            ys = np.array([r["y"] for r in ok]) / 1000
            dc = np.array([r["dCm0"] for r in ok])
            yy = np.array([s["y"] for s in d["sections"]] + [d["b_mm"] / 2]) / 1000
            cc = np.array([s["chord"] for s in d["sections"]] + [d["sections"][-1]["chord"]]) / 1000
            S, cref = d["S_dm2"] / 100, d["MAC_mm"] / 1000
            dcm0[model] = float(2 / (S * cref) * np.trapezoid(np.interp(yy, ys, dc) * cc ** 2, yy))
        print(f"{model}: {sum(r['ok'] for r in rows)}/{len(rows)} polars, aircraft dCm0 = {dcm0.get(model, float('nan')):+.4f}",
              flush=True)
    (AVL_DIR / "xfoil.json").write_text(json.dumps({"v": args.v, "rho": args.rho, "models": out}, indent=1))
    (AVL_DIR / "xfoil_dcm0.json").write_text(json.dumps(dcm0, indent=1))


if __name__ == "__main__":
    main()
