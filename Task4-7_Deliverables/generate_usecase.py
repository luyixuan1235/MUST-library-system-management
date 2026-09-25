# -*- coding: utf-8 -*-
"""UML use-case diagram — high-DPI PNG + vector PDF/SVG.

Layout rules
------------
* Every ellipse sits fully inside the system rectangle (padding >= 0.5).
* Association lines meet an ellipse on the outward rim only.
* <<include>> / <<extend>> arrows travel in dedicated side corridors;
  their labels sit in empty space with a white boxed background.
* No relationship line is allowed to cross an ellipse.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, Rectangle, Circle, FancyArrowPatch
from matplotlib.lines import Line2D

BASE = os.path.dirname(os.path.abspath(__file__))
PNG = os.path.join(BASE, "use_case_diagram.png")
PDF = os.path.join(BASE, "use_case_diagram.pdf")
SVG = os.path.join(BASE, "use_case_diagram.svg")

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Calibri", "Segoe UI", "Arial", "DejaVu Sans"],
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "svg.fonttype": "none",
    "text.antialiased": True,
})

FIG_W, FIG_H, DPI = 18.0, 13.2, 300
fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
ax.set_xlim(0.0, 18.0)
ax.set_ylim(0.0, 13.2)
ax.set_aspect("equal")
ax.axis("off")
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
# System box. right = 15.25, top = 12.55
BOX_X, BOX_Y, BOX_W, BOX_H = 3.05, 1.95, 12.20, 10.60

EW, EH = 3.20, 0.90          # ellipse width / height
PAD = 0.55                   # ellipse-to-box padding

LX = BOX_X + PAD + EW / 2.0                 # 5.20
RX = BOX_X + BOX_W - PAD - EW / 2.0         # 13.05
# Wait: RX = 3.05+12.20-0.55-1.60 = 13.10. Recalculate below after constants.

LX = 5.20
RX = 12.40                                  # ellipse right rim = 14.00
# box right = 15.25  => 1.25 corridor for <<extend>> spine + label

# 7 student / 6 admin slots, 1.16 apart  (ellipse gap = 0.26 — too tight for
# arrows, so arrows never go through that gap)
YS = [11.85, 10.69, 9.53, 8.37, 7.21, 6.05, 4.89]
YA = [11.85, 10.69, 9.53, 8.37, 7.21, 6.05]
BY = 2.68                                   # bottom-row (system) y
BX = (5.20, 8.80, 12.40)

ucs = {
    "UC1":  (LX, YS[0], "Register Account"),
    "UC2":  (LX, YS[1], "Log In / Log Out"),
    "UC3":  (LX, YS[2], "View Floor Map\n& Seat Status"),
    "UC4":  (LX, YS[3], "View Seat Details"),
    "UC5":  (LX, YS[4], "Report Seat Issue"),
    "UC6":  (LX, YS[5], "Upload Photo Evidence"),
    "UC7":  (LX, YS[6], "Switch Language"),
    "UC8":  (RX, YA[0], "View Anomaly List"),
    "UC9":  (RX, YA[1], "View Report Details"),
    "UC10": (RX, YA[2], "Confirm / Dismiss\nAnomaly"),
    "UC11": (RX, YA[3], "Clear Anomaly"),
    "UC12": (RX, YA[4], "Lock Seat (5 min)"),
    "UC13": (RX, YA[5], "Trigger Floor Refresh"),
    "UC14": (BX[0], BY, "Detect Occupancy\n(YOLOv11)"),
    "UC15": (BX[1], BY, "Raise Auto-Alarm"),
    "UC16": (BX[2], BY, "Export Statistics"),
}

def rim(uc, side):
    x, y, _ = ucs[uc]
    return {
        "l": (x - EW / 2.0, y),
        "r": (x + EW / 2.0, y),
        "t": (x, y + EH / 2.0),
        "b": (x, y - EH / 2.0),
    }[side]

# ---------------------------------------------------------------------------
# System boundary
# ---------------------------------------------------------------------------
ax.add_patch(Rectangle(
    (BOX_X, BOX_Y), BOX_W, BOX_H,
    fill=False, lw=2.6, edgecolor="#111111", zorder=1,
))
ax.text(
    BOX_X + BOX_W / 2.0, BOX_Y + BOX_H + 0.22,
    "Library Seat Management System",
    ha="center", va="bottom", fontsize=17, fontweight="bold",
    color="#111111", zorder=8,
)

# ---------------------------------------------------------------------------
# Use-case ellipses
# ---------------------------------------------------------------------------
for x, y, label in ucs.values():
    ax.add_patch(Ellipse(
        (x, y), EW, EH,
        facecolor="#E7F0FB", edgecolor="#1A4F8A", lw=1.9, zorder=3,
    ))
    ax.text(
        x, y, label,
        ha="center", va="center",
        fontsize=11, color="#0C2744", linespacing=1.20, zorder=4,
    )

# ---------------------------------------------------------------------------
# Actors
# ---------------------------------------------------------------------------
def actor(x, y, title, subtitle=""):
    ax.add_patch(Circle((x, y + 0.70), 0.20, fill=False, lw=2.3, edgecolor="#111", zorder=6))
    ax.plot([x, x],                 [y + 0.50, y - 0.10], color="#111", lw=2.3, solid_capstyle="round", zorder=6)
    ax.plot([x - 0.36, x + 0.36],   [y + 0.28, y + 0.28], color="#111", lw=2.3, solid_capstyle="round", zorder=6)
    ax.plot([x, x - 0.28],          [y - 0.10, y - 0.58], color="#111", lw=2.3, solid_capstyle="round", zorder=6)
    ax.plot([x, x + 0.28],          [y - 0.10, y - 0.58], color="#111", lw=2.3, solid_capstyle="round", zorder=6)
    ax.text(x, y - 0.72, title, ha="center", va="top", fontsize=12.5, fontweight="bold", color="#111", zorder=6)
    if subtitle:
        ax.text(x, y - 1.05, subtitle, ha="center", va="top", fontsize=9, color="#555", zorder=6)

actor(1.40, 8.15, "Student", "(Library User)")
actor(16.60, 8.15, "Administrator", "(Library Staff)")
actor(1.40, 3.35, "Camera", "(Video Stream)")
actor(16.60, 3.35, "Scheduler", "(Timer)")

# ---------------------------------------------------------------------------
# Associations (solid, no arrow head)
# ---------------------------------------------------------------------------
def assoc(*pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ax.plot(xs, ys, color="#333333", lw=1.35, solid_capstyle="round", zorder=2)

STU = (1.76, 8.43)          # student's right hand
ADM = (16.24, 8.43)
CAM = (1.76, 3.63)
SCH = (16.24, 3.63)

for uc in ("UC1", "UC2", "UC3", "UC4", "UC5", "UC6", "UC7"):
    assoc(STU, rim(uc, "l"))
for uc in ("UC8", "UC9", "UC10", "UC11", "UC12", "UC13"):
    assoc(ADM, rim(uc, "r"))

# Camera -> Detect Occupancy (left rim of bottom-left ellipse)
assoc(CAM, rim("UC14", "l"))

# Scheduler -> Export Statistics (right rim of bottom-right ellipse)
assoc(SCH, rim("UC16", "r"))

# Scheduler -> Raise Auto-Alarm / Detect Occupancy, routed BELOW the box
# so the polyline never crosses an ellipse.
UNDER = 1.62                 # below box (box y = 1.95)
assoc(SCH, (SCH[0], UNDER), (BX[1], UNDER), rim("UC15", "b"))
assoc((BX[1], UNDER), (BX[0], UNDER), rim("UC14", "b"))

# ---------------------------------------------------------------------------
# <<include>> / <<extend>>  — side corridors only
# ---------------------------------------------------------------------------
PURPLE = "#6A1B9A"

def dashed(*pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ax.plot(xs, ys, color=PURPLE, lw=1.45, linestyle=(0, (5, 3.5)),
            solid_capstyle="round", zorder=5)

def arrow(p_from, p_to):
    ax.add_patch(FancyArrowPatch(
        p_from, p_to,
        arrowstyle="-|>", mutation_scale=13,
        linestyle=(0, (5, 3.5)), linewidth=1.45,
        color=PURPLE, zorder=5, shrinkA=0, shrinkB=1.5,
    ))

def tag(x, y, text):
    ax.text(
        x, y, text, ha="center", va="center",
        fontsize=9, color=PURPLE, style="italic", fontweight="bold",
        zorder=7,
        bbox=dict(boxstyle="round,pad=0.20", fc="white", ec=PURPLE, lw=0.7),
    )

# --- UC5 Report  <<include>>  UC6 Upload Photo -----------------------------
# Corridor just to the RIGHT of the student column, in the empty middle.
C_INC_L = LX + EW / 2.0 + 0.42          # 7.22
dashed(rim("UC5", "r"), (C_INC_L, YS[4]), (C_INC_L, YS[5]))
arrow((C_INC_L, YS[5]), rim("UC6", "r"))
tag(C_INC_L + 0.72, (YS[4] + YS[5]) / 2.0, "<<include>>")

# --- UC8 View Anomaly List  <<include>>  UC9 View Report Details -----------
# Corridor just to the LEFT of the admin column, in the empty middle.
C_INC_R = RX - EW / 2.0 - 0.42          # 10.38
dashed(rim("UC8", "l"), (C_INC_R, YA[0]), (C_INC_R, YA[1]))
arrow((C_INC_R, YA[1]), rim("UC9", "l"))
tag(C_INC_R - 0.72, (YA[0] + YA[1]) / 2.0, "<<include>>")

# --- UC10 / UC11 / UC12  <<extend>>  UC8 View Anomaly List -----------------
# Dedicated corridor to the RIGHT of the admin column, still inside the box.
# Admin right rim = 12.40 + 1.60 = 14.00
# Box right        = 15.25
# Spine at 14.55, label centred on the spine (white box ~1.1 wide => 14.00–15.10)
C_EXT = 14.50
for y in (YA[2], YA[3], YA[4]):
    dashed(rim("UC10" if y == YA[2] else "UC11" if y == YA[3] else "UC12", "r"),
           (C_EXT, y))
dashed((C_EXT, YA[4]), (C_EXT, YA[0]))
arrow((C_EXT, YA[0]), rim("UC8", "r"))
tag(C_EXT, (YA[1] + YA[2]) / 2.0, "<<extend>>")

# --- UC15 Raise Auto-Alarm  <<extend>>  UC14 Detect Occupancy --------------
# Horizontal band BETWEEN the user columns and the bottom row:
#   student last ellipse bottom = 4.89 - 0.45 = 4.44
#   bottom-row ellipse top      = 2.68 + 0.45 = 3.13
#   empty band ≈ 3.20 – 4.40. Put the arrow at y = 3.48.
BAND = 3.48
dashed(rim("UC15", "t"), (BX[1], BAND), (BX[0], BAND))
arrow((BX[0], BAND), rim("UC14", "t"))
tag((BX[0] + BX[1]) / 2.0, BAND + 0.28, "<<extend>>")

# ---------------------------------------------------------------------------
# Legend
# ---------------------------------------------------------------------------
LEG = 0.55
ax.add_line(Line2D([0.50, 1.45], [LEG, LEG], color="#333", lw=1.6, zorder=5))
ax.text(1.58, LEG, "association", fontsize=10, va="center", color="#333")

ax.add_patch(FancyArrowPatch(
    (3.70, LEG), (4.80, LEG),
    arrowstyle="-|>", mutation_scale=13,
    linestyle=(0, (5, 3.5)), linewidth=1.45, color=PURPLE,
    zorder=5, shrinkA=0, shrinkB=0,
))
ax.text(4.95, LEG, "<<include>>  /  <<extend>>  dependency",
        fontsize=10, va="center", color=PURPLE)

ax.text(
    0.50, 0.22,
    "Note: Detect Occupancy runs every 8 s per floor.  "
    "Auto-Alarm flags a seat occupied only by objects (no person) for more than 2 hours.",
    fontsize=9, va="center", color="#555555",
)

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
save_kw = dict(facecolor="white", edgecolor="none", bbox_inches="tight", pad_inches=0.30)
fig.savefig(PNG, dpi=DPI, **save_kw)
fig.savefig(PDF, **save_kw)
fig.savefig(SVG, **save_kw)
plt.close()
print("PNG", PNG)
print("PDF", PDF)
print("SVG", SVG)
