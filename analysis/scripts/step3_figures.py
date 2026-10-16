"""Figures of the Step 3 results (stability, trim, drag, planform) into analysis/figures/step3_*.png.

Run after avl_build.py (both passes), xfoil_polars.py and drag_estimate.py.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avl_build import AVL_DIR, SHORT  # noqa: E402

FIG = AVL_DIR.parent / "figures"
ORDER = ["berkirkSiloute", "berkirkSilouteChangedWings", "berkirkSilouteReducedTail",
         "berkirkSilouteReducedTailChangedWings", "berkirkSilouteConstantCorners",
         "berkirkSilouteConstantCornersChangedWings", "berkirkSilouteConstantCornersReducedTail",
         "berkirkSilouteConstantCornersReducedTailChangedWings", "contourn"]
# reference palette (dataviz skill, light mode)
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
BAND = "#cde2fb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "font.size": 9.5, "axes.titlesize": 10.5, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
})

inv = json.loads((AVL_DIR / "results.json").read_text())
vis = json.loads((AVL_DIR / "results_visc.json").read_text())
drag = json.loads((AVL_DIR / "drag.json").read_text())
I, V, D = inv["models"], vis["models"], drag["models"]
xcg = vis["meta"]["xcg_mm"]
labels = [SHORT[m] for m in ORDER]
yy = np.arange(len(ORDER))[::-1]


def hbars(ax, vals, title, fmt, xlabel, band=None):
    if band:
        ax.axvspan(*band, color=BAND, lw=0, zorder=0)
    ax.barh(yy, vals, height=0.6, color=BLUE, edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(yy, labels)
    ax.grid(axis="y", visible=False)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    span = max(vals) - min(0, min(vals))
    for y, v in zip(yy, vals):
        ax.text(v + 0.01 * span, y, fmt.format(v), va="center", ha="left", color=INK2, fontsize=8.5)
    ax.set_xlim(min(0, min(vals)), max(vals) + 0.18 * span)


# 1. stability ----------------------------------------------------------------
fig, axs = plt.subplots(1, 3, figsize=(12, 4.2), sharey=True)
hbars(axs[0], [V[m]["SM_pct"] for m in ORDER], f"Pitch: static margin at CG {xcg:.0f} mm",
      "{:.1f}%", "% of MAC (shaded: 5–10% target)", band=(5, 10))
hbars(axs[1], [V[m]["Cnb"] for m in ORDER], "Yaw: weathercock stability Cnβ", "{:.4f}", "per rad (higher = more stable)")
hbars(axs[2], [-V[m]["Clb"] for m in ORDER], "Roll: dihedral effect −Clβ", "{:.3f}", "per rad (higher = more stable)")
fig.suptitle(f"Static stability of the 9 variants (AVL + XFoil, trimmed at 12 m/s, "
             f"{vis['meta']['mass_kg'] * 1000:.0f} g placeholder)", x=0.01, ha="left", fontsize=11, color=INK2)
fig.tight_layout()
fig.savefig(FIG / "step3_stability.png", dpi=150)
plt.close(fig)

# 2. trim ---------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(7.5, 4.2))
for y, m in zip(yy, ORDER):
    ev = next(t["elev"] for t in V[m]["trim"] if t["V"] == 12.0)
    ei = next(t["elev"] for t in I[m]["trim"] if t["V"] == 12.0)
    ax.plot([ei, ev], [y, y], color=AXIS, lw=2, zorder=1)
    ax.scatter([ev], [y], s=60, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3,
               label="viscous (AVL + XFoil)" if m == ORDER[0] else None)
    ax.scatter([ei], [y], s=60, color=ORANGE, edgecolor=SURFACE, linewidth=2, zorder=3,
               label="inviscid (AVL only)" if m == ORDER[0] else None)
    ax.text(ev + 0.3, y, f"{ev:+.1f}°", va="center", color=INK2, fontsize=8.5)
ax.axvline(0, color=INK2, lw=1)
ax.set_yticks(yy, labels)
ax.grid(axis="y", visible=False)
ax.set_xlabel("elevon angle to trim at 12 m/s [°]   (− = trailing edge up)")
ax.set_title("Elevon needed to fly level: the truth lies between the two models")
ax.legend(loc="lower right", frameon=False)
ax.set_xlim(-13, 2.5)
fig.tight_layout()
fig.savefig(FIG / "step3_trim.png", dpi=150)
plt.close(fig)

# 3. drag ---------------------------------------------------------------------
fig, axs = plt.subplots(1, 2, figsize=(12, 4.2), sharey=True, gridspec_kw={"width_ratios": [1.6, 1]})
parts = [("CDp", "wing profile", BLUE), ("CDi", "induced", ORANGE), ("CDbase", "tail-face base", AQUA),
         ("CDwl", "winglet friction", YELLOW)]
left = np.zeros(len(ORDER))
for key, name, col in parts:
    vals = np.array([next(r for r in D[m]["rows"] if r["V"] == 12.0)[key] for m in ORDER])
    axs[0].barh(yy, vals, left=left, height=0.6, color=col, edgecolor=SURFACE, linewidth=2, label=name)
    left += vals
for y, tot in zip(yy, left):
    axs[0].text(tot + 0.0003, y, f"{tot:.4f}", va="center", color=INK2, fontsize=8.5)
axs[0].set_yticks(yy, labels)
axs[0].grid(axis="y", visible=False)
axs[0].set_xlim(0, left.max() * 1.15)
axs[0].set_xlabel("drag coefficient CD at 12 m/s (trimmed)")
axs[0].set_title("Drag breakdown (low-order estimate)")
axs[0].legend(loc="lower center", bbox_to_anchor=(0.5, 1.07), ncol=4, frameon=False, fontsize=8.5)
hbars(axs[1], [D[m]["LD_max"] for m in ORDER], "Best lift-to-drag ratio", "{:.1f}", "L/D (higher = more efficient)")
fig.tight_layout()
fig.savefig(FIG / "step3_drag.png", dpi=150)
plt.close(fig)

# 4. planform with NP / CG / MAC / elevon ----------------------------------------
m = "berkirkSiloute"
secs = V[m]["sections"]
y = np.array([s["y"] for s in secs])
le = np.array([s["le"][0] for s in secs])
te = np.array([s["te"][0] for s in secs])
hinge = np.array([s["le"][0] + s["chord"] * s["x_hinge"] if s["elevon"] else np.nan for s in secs])
fig, ax = plt.subplots(figsize=(9, 4.6))
for sgn in (1, -1):
    ax.plot(sgn * y, le, color=INK, lw=1.5)
    ax.plot(sgn * y, te, color=INK, lw=1.5)
    ok = ~np.isnan(hinge)
    ax.fill_between(sgn * y[ok], hinge[ok], te[ok], color=BAND, lw=0)
    ax.plot(sgn * y[ok], hinge[ok], color=BLUE, lw=1, ls="--")
    ax.plot([sgn * y[-1]] * 2, [le[-1], te[-1]], color=INK, lw=1.5)
xnp, mac = V[m]["Xnp_mm"], V[m]["MAC_mm"]
ax.axhline(xnp, color=ORANGE, lw=2)
ax.axhline(xcg, color=BLUE, lw=2)
ax.axhspan(xnp - 0.10 * mac, xnp - 0.05 * mac, color=BAND, lw=0, zorder=0)
ax.text(700, xnp + 4, f"neutral point {xnp:.0f} mm", color=INK, va="top", fontsize=9)
ax.text(700, xcg - 4, f"CG {xcg:.0f} mm (plan)", color=INK, va="bottom", fontsize=9)
ax.text(-700, xnp - 0.10 * mac - 4, f"CG band for 5–10% margin: {xnp - 0.10 * mac:.0f}–{xnp - 0.05 * mac:.0f} mm",
        color=INK2, va="bottom", fontsize=8.5)
ax.text(470, 545, "elevon", color=BLUE, fontsize=9)
ax.set_ylim(660, -20)
ax.set_xlim(-720, 900)
ax.set_aspect("equal")
ax.set_xlabel("span y [mm]")
ax.set_ylabel("distance behind the nose x [mm]")
ax.set_title("Base: planform with neutral point, CG and elevon (viscous model)")
fig.tight_layout()
fig.savefig(FIG / "step3_planform.png", dpi=150)
plt.close(fig)
print("written:", *sorted(p.name for p in FIG.glob("step3_*.png")))
