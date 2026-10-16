"""Low-order drag and L/D estimate of the trimmed Berkirk variants (AVL strips + XFoil polars).

CD = profile drag of the wing  (XFoil cd at each AVL strip's trimmed cl, interpolated between stations)
   + winglet friction          (flat plate, cd = CD_WINGLET on the winglet strips)
   + induced drag              (AVL CDind, trimmed, includes the elevon deflection)
   + base drag of the tail face (CD_BASE_COEF x tail-face area / S)

Run after avl_build.py --visc and xfoil_polars.py. Writes analysis/avl/drag.json and prints Markdown tables.
Rough by design: polars at one Reynolds number (scaled by (V/12)^-0.2), no prop wake, no
interference. Use it to rank the variants, not as absolute numbers; CFD (Step 4) replaces it.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avl_build import AVL_DIR, G, NUM, SHORT  # noqa: E402

SPEEDS = [8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 24.0]
CD_WINGLET = 0.010              # flat 5 mm plate, both sides, Re ~ 1e5
CD_BASE_COEF = 0.15             # base-pressure drag of a blunt face behind a thick boundary layer
# blunt tail face of the centre body [cm²], from stl_geometry.py ("Tail face", report §4.6)
TAIL_FACE_CM2 = {"berkirkSiloute": 48.7, "berkirkSilouteChangedWings": 48.7, "berkirkSilouteReducedTail": 17.1,
                 "berkirkSilouteReducedTailChangedWings": 17.1, "berkirkSilouteConstantCorners": 48.3,
                 "berkirkSilouteConstantCornersChangedWings": 48.3,
                 "berkirkSilouteConstantCornersReducedTail": 17.9,
                 "berkirkSilouteConstantCornersReducedTailChangedWings": 17.9, "contourn": 50.0}


def cd_of_cl(polar):
    """cd(cl) on the attached branch of a polar [alpha, CL, CD, CM]."""
    P = np.array(polar)
    P = P[np.argsort(P[:, 0])]
    P = P[: int(np.argmax(P[:, 1])) + 1]                   # up to CLmax
    o = np.argsort(P[:, 1])
    cl, cd = P[o, 1], P[o, 2]
    return lambda c: float(np.interp(c, cl, cd)), float(cl.min()), float(cl.max())


def strips(block):
    """(surface name, y, area, cl) of every strip in an FS printout."""
    out, surf = [], None
    for line in block.splitlines():
        m = re.match(r"\s*Surface #\s*\d+\s+(\S+)", line)
        if m:
            surf = m.group(1)
            continue
        p = line.split()
        if surf and len(p) >= 15 and p[0].isdigit():
            try:
                out.append((surf, float(p[2]), float(p[5]), float(p[9])))
            except ValueError:
                pass
    return out


def main():
    res = json.loads((AVL_DIR / "results_visc.json").read_text())
    meta, models = res["meta"], res["models"]
    xf = json.loads((AVL_DIR / "xfoil.json").read_text())["models"]
    W, rho = meta["mass_kg"] * G, meta["rho"]
    out = {}
    for model, d in models.items():
        S = d["S_dm2"] / 100
        st = [(r["y"],) + cd_of_cl(r["polar"]) for r in xf[model] if r.get("ok")]
        ys = np.array([s[0] for s in st], float)
        cmds = [f"LOAD {model}_visc.avl", "OPER"]
        for v in SPEEDS:
            cl = 2 * W / (rho * v ** 2 * S)
            cmds += [f"A C {cl:.5f}", f"D1 PM {-d['dCm0_visc']:.5f}", "X", "FS", ""]
        cmds += ["", "QUIT"]
        r = subprocess.run(["avl"], input="\n".join(cmds) + "\n", capture_output=True, text=True,
                           cwd=AVL_DIR / model, timeout=900)
        blocks = r.stdout.split("Vortex Lattice Output -- Total Forces")[1:]
        rows = []
        for v, blk in zip(SPEEDS, blocks):
            cl_tot = float(re.search(r"CLtot\s*=\s*" + NUM, blk).group(1))
            cdi = float(re.search(r"CDind\s*=\s*" + NUM, blk).group(1))
            elev = float(re.search(r"elevator\s*=\s*" + NUM, blk).group(1))
            re_fac = (v / 12.0) ** -0.2
            cdp = cdw = 0.0
            clipped = 0
            for surf, y, area, cl in strips(blk):
                if surf.startswith("Winglet"):
                    cdw += CD_WINGLET * area / S
                    continue
                ay = abs(y) * 1000
                i = int(np.clip(np.searchsorted(ys, ay), 1, len(ys) - 1))
                w = float(np.clip((ay - ys[i - 1]) / (ys[i] - ys[i - 1]), 0, 1))
                cds = []
                for k in (i - 1, i):
                    f, lo, hi = st[k][1], st[k][2], st[k][3]
                    clipped += not (lo <= cl <= hi)
                    cds.append(f(cl))
                cdp += ((1 - w) * cds[0] + w * cds[1]) * re_fac * area / S
            cdb = CD_BASE_COEF * TAIL_FACE_CM2[model] * 1e-4 / S
            cd = cdp + cdw + cdi + cdb
            rows.append({"V": v, "CL": cl_tot, "elev": elev, "CDp": cdp, "CDwl": cdw, "CDi": cdi, "CDbase": cdb,
                         "CD": cd, "LD": cl_tot / cd, "P_W": 0.5 * rho * v ** 3 * S * cd, "clipped": clipped})
        if len(rows) != len(SPEEDS):
            raise RuntimeError(f"{model}: AVL returned {len(rows)} of {len(SPEEDS)} cases")
        best = max(rows, key=lambda q: q["LD"])
        out[model] = {"rows": rows, "LD_max": best["LD"], "V_LDmax": best["V"],
                      "P_min": min(q["P_W"] for q in rows)}
    (AVL_DIR / "drag.json").write_text(json.dumps({"meta": meta, "cd_winglet": CD_WINGLET,
                                                   "cd_base_coef": CD_BASE_COEF, "models": out}, indent=1))
    print("| Model | CD at 12 m/s: profile + winglets + induced + base = total | L/D at 12 m/s | "
          "Best L/D (at m/s) | Min. power for level flight [W] |")
    print("|---|---|---|---|---|")
    for m, d in out.items():
        q = next(r for r in d["rows"] if r["V"] == 12.0)
        print(f"| {SHORT[m]} | {q['CDp']:.4f} + {q['CDwl']:.4f} + {q['CDi']:.4f} + {q['CDbase']:.4f} = "
              f"**{q['CD']:.4f}** | {q['LD']:.1f} | {d['LD_max']:.1f} ({d['V_LDmax']:.0f}) | {d['P_min']:.1f} |")
    print("\nStrip cl outside a polar's range (clamped):",
          {SHORT[m]: sum(r["clipped"] for r in d["rows"]) for m, d in out.items()})


if __name__ == "__main__":
    main()
