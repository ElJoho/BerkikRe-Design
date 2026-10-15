"""Check the STEP files in STP/ with FreeCAD (OpenCASCADE).

For each file: solid count, validity (and validity after fix()), volume, area,
tight bounding box and the root-LE / tail / bottom datum.

Run (FreeCAD snap):
    cp analysis/scripts/step_check.py ~/snap/freecad/common/
    freecad.cmd ~/snap/freecad/common/step_check.py <repo>/STP
The snap can only read files under $HOME, so pass the absolute STP path.
"""
import glob
import os
import sys

import Part

stp_dir = [a for a in sys.argv[1:] if a.endswith("STP") or os.path.isdir(a)]
stp_dir = stp_dir[-1] if stp_dir else os.path.join(os.getcwd(), "STP")

print("| File | Solids | Shells | Valid | Valid after fix() | Volume [L] | Area [dm²] | "
      "x span [mm] | y nose / tail [mm] | z min / max [mm] |")
print("|---|---|---|---|---|---|---|---|---|---|")
for path in sorted(glob.glob(os.path.join(stp_dir, "*.stp"))):
    name = os.path.splitext(os.path.basename(path))[0]
    shape = Part.Shape()
    shape.read(path)
    valid = shape.isValid()
    fixed = "–"
    if not valid:
        s2 = shape.copy()
        s2.fix(1e-4, 1e-4, 1e-3)
        fixed = "yes" if s2.isValid() else "**no**"
    bb = shape.BoundBox
    # tight bounding box (optimal)
    try:
        bb = shape.optimalBoundingBox()
    except Exception:
        pass
    print(f"| {name} | {len(shape.Solids)} | {len(shape.Shells)} | "
          f"{'yes' if valid else '**no**'} | {fixed} | {shape.Volume / 1e6:.2f} | "
          f"{shape.Area / 1e4:.2f} | {bb.XMin:.1f} … {bb.XMax:.1f} | "
          f"{bb.YMax:.1f} / {bb.YMin:.1f} | {bb.ZMin:.1f} / {bb.ZMax:.1f} |")
