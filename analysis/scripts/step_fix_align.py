"""Repair, align and finely tessellate the STEP files in STP/ with FreeCAD (OpenCASCADE).

For each STP/<model>.stp:
  1. Repair it with shape.fix() if it is not a valid solid.
  2. Move it to the common datum: origin at the nose (most forward point of the
     symmetry plane, i.e. the root LE), X aft, Y along the span, Z up. The
     symmetry plane is taken as the middle of the spanwise bounding box, which
     also removes the 5 mm sideways offset of the CC models.
  3. Write STP/fixed/<model>.stp (AP214, mm) and a fine binary STL for CFD,
     STL/cfd/<model>.stl (mm, same datum).

Inventor's exports use X = span, Y = forward, Z = up, so the rotation is +90 deg
about Z: new X = -old Y, new Y = old X.

Run (FreeCAD snap, which can only read and write under $HOME):
    cp analysis/scripts/step_fix_align.py ~/snap/freecad/common/
    freecad.cmd ~/snap/freecad/common/step_fix_align.py $PWD
"""
import glob
import os
import sys

import FreeCAD as App
import Mesh
import MeshPart
import Part

LINEAR_DEFLECTION = 0.02            # mm, max chordal error of the CFD STL
ANGULAR_DEFLECTION = 0.0873         # rad (5 deg) between neighbouring facets

args = [a for a in sys.argv[1:] if os.path.isdir(a)]
repo = args[-1] if args else os.getcwd()
stp_out = os.path.join(repo, "STP", "fixed")
stl_out = os.path.join(repo, "STL", "cfd")
os.makedirs(stp_out, exist_ok=True)
os.makedirs(stl_out, exist_ok=True)


def nose_point(shape, x_sym):
    """Most forward (max Y) point of the section at the symmetry plane."""
    best = None
    for edge in shape.slice(App.Vector(1, 0, 0), x_sym):
        for p in edge.discretize(Deflection=0.005):
            if best is None or p.y > best.y:
                best = p
    return best


print("| Model | Valid as exported | Repaired | dV repair [cm³] | Span offset [mm] | Nose (old y, z) [mm] | "
      "x aft [mm] | y span [mm] | z [mm] | Valid after | CFD STL triangles | STL solid / non-manifold / bad orientation | STL volume [L] |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for path in sorted(glob.glob(os.path.join(repo, "STP", "*.stp"))):
    name = os.path.splitext(os.path.basename(path))[0]
    shape = Part.Shape()
    shape.read(path)
    valid0 = shape.isValid()
    dv = 0.0
    if not valid0:
        v0 = shape.Volume
        shape.fix(1e-4, 1e-4, 1e-3)
        dv = (shape.Volume - v0) / 1e3
    solid = shape.Solids[0] if len(shape.Solids) == 1 else shape

    bb = solid.BoundBox
    x_sym = 0.5 * (bb.XMin + bb.XMax)
    nose = nose_point(solid, x_sym)

    aligned = solid.copy()
    aligned.translate(App.Vector(-x_sym, -nose.y, -nose.z))
    aligned.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 90)
    nb = aligned.BoundBox

    aligned.exportStep(os.path.join(stp_out, name + ".stp"))
    mesh = MeshPart.meshFromShape(Shape=aligned, LinearDeflection=LINEAR_DEFLECTION,
                                  AngularDeflection=ANGULAR_DEFLECTION, Relative=False)
    mesh.write(os.path.join(stl_out, name + ".stl"))

    print(f"| {name} | {'yes' if valid0 else 'no'} | {'–' if valid0 else 'fix()'} | {dv:+.2f} | "
          f"{x_sym:+.2f} | {nose.y:.2f}, {nose.z:.2f} | {nb.XMin:.1f} … {nb.XMax:.1f} | "
          f"{nb.YMin:.1f} … {nb.YMax:.1f} | {nb.ZMin:.1f} … {nb.ZMax:.1f} | "
          f"{'yes' if aligned.isValid() else '**no**'} | {mesh.CountFacets} | "
          f"{mesh.isSolid()} / {mesh.hasNonManifolds()} / {mesh.countNonUniformOrientedFacets()} | "
          f"{mesh.Volume / 1e6:.3f} |")
