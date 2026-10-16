"""Slice the aligned STEP files (STP/fixed/) into wing and winglet sections (FreeCAD).

Datum of STP/fixed/: origin at the nose, X aft, Y along the span (right wing +Y), Z up, mm.
Writes analysis/avl/sections/<model>.json with, for the right half:
  "wing":     [{"y": y, "pts": [[x, z], ...]}, ...]   closed loops cut by planes y = const
  "winglet":  [{"z": z, "pts": [[x, y], ...]}, ...]   closed loops cut by planes z = const, y > 550

Run (FreeCAD snap):
    cp analysis/scripts/extract_sections.py ~/snap/freecad/common/
    freecad.cmd ~/snap/freecad/common/extract_sections.py $PWD
"""
import glob
import json
import os
import sys

import FreeCAD as App
import Part

args = [a for a in sys.argv[1:] if os.path.isdir(a)]
repo = args[-1] if args else os.getcwd()
out_dir = os.path.join(repo, "analysis", "avl", "sections")
os.makedirs(out_dir, exist_ok=True)

Y_STATIONS = [0, 15, 30, 45, 60, 75, 90, 110, 130, 150, 175, 200, 225, 250, 270, 285, 295,
              320, 350, 400, 450, 500, 550, 600, 620, 635, 645, 650, 655, 660]
DEFLECTION = 0.01                    # mm, max distance between the section curve and the polyline


def loops(shape, normal, d):
    """Closed loops of the section as point lists (largest first)."""
    res = []
    for w in shape.slice(normal, d):
        if not w.isClosed():
            continue
        pts = w.discretize(Deflection=DEFLECTION)
        try:
            area = Part.Face(w).Area
        except Exception:
            area = 0.0
        res.append((area, pts))
    res.sort(key=lambda r: -r[0])
    return res


for path in sorted(glob.glob(os.path.join(repo, "STP", "fixed", "*.stp"))):
    name = os.path.splitext(os.path.basename(path))[0]
    shape = Part.Shape()
    shape.read(path)
    bb = shape.BoundBox
    data = {"model": name, "bbox": [bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin, bb.ZMax],
            "wing": [], "winglet": []}
    for y in Y_STATIONS:
        ls = loops(shape, App.Vector(0, 1, 0), float(y) + 1e-3)
        if ls:
            area, pts = ls[0]
            data["wing"].append({"y": y, "area": area, "nloops": len(ls),
                                 "pts": [[round(p.x, 4), round(p.z, 4)] for p in pts]})
    z = bb.ZMin + 1.0
    while z < bb.ZMax:
        for area, pts in loops(shape, App.Vector(0, 0, 1), z):
            if min(p.y for p in pts) > 550:
                data["winglet"].append({"z": round(z, 2), "area": area,
                                        "pts": [[round(p.x, 4), round(p.y, 4)] for p in pts]})
        z += 2.0
    with open(os.path.join(out_dir, name + ".json"), "w") as f:
        json.dump(data, f)
    print(name, "wing stations", len(data["wing"]), "winglet slices", len(data["winglet"]), flush=True)
