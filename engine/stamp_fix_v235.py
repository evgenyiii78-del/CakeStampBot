"""CakeStampBot v2.3.5 stamp-only geometry fixes.

Keeps topper untouched.  Applied to the Blender text stamp engine at import time.
"""
from __future__ import annotations

import math
import numpy as np
from shapely.geometry import LineString, Point
from shapely.ops import unary_union


def _shortened_segment(a, b, trim_a=0.0, trim_b=0.0):
    ax, ay = a; bx, by = b
    dx, dy = bx-ax, by-ay
    ln = max(1e-9, math.hypot(dx, dy))
    ux, uy = dx/ln, dy/ln
    return LineString([(ax+ux*trim_a, ay+uy*trim_a),
                       (bx-ux*trim_b, by-uy*trim_b)])


def _points(width, height, yoff=0.0):
    """Crown proportions matched to the user's approved reference.

    Important differences from the previous crown:
    - shallower V valleys;
    - lower centre peak;
    - smaller tip rings;
    - narrower upper silhouette and slightly tapered sides;
    - almost-straight shallow arched base.
    """
    w = float(width); h = float(height); y = float(yoff)
    return {
        "BL": (-w*.43, y-h*.34),
        "L":  (-w*.32, y+h*.22),
        "VL": (-w*.13, y+h*.015),
        "C":  (0.0,    y+h*.40),
        "VR": ( w*.13, y+h*.015),
        "R":  ( w*.32, y+h*.22),
        "BR": ( w*.43, y-h*.34),
    }


def crown_geometry(width=28.0, height_mm=13.4, line_width=.35):
    w=float(width); h=float(height_mm); lw=float(line_width)
    # The reference has small jewellery-like rings, not large circles.
    r=max(.82, lw*2.45)
    p=_points(w,h)
    BL,L,VL,C,VR,R,BR=(p[k] for k in ("BL","L","VL","C","VR","R","BR"))
    trim=max(0.0, r-lw*.38)
    segs=[
        _shortened_segment(BL,L,0,trim),
        _shortened_segment(L,VL,trim,0),
        _shortened_segment(VL,C,0,trim),
        _shortened_segment(C,VR,trim,0),
        _shortened_segment(VR,R,0,trim),
        _shortened_segment(R,BR,trim,0),
    ]
    # Very shallow upward arch, visually close to a straight base.
    xs=np.linspace(BL[0],BR[0],160)
    arch=max(.18, min(.36, w*.0105))
    ys=BL[1] + arch*(1-(xs/(w*.43))**2)
    segs.append(LineString(np.c_[xs,ys]))
    parts=[s.buffer(lw/2,cap_style=1,join_style=1,resolution=96) for s in segs]
    for x,y in (L,C,R):
        outer=Point(x,y).buffer(r,resolution=128)
        inner=Point(x,y).buffer(max(.22,r-lw),resolution=128)
        parts.append(outer.difference(inner))
    return unary_union(parts).buffer(0)


def crown_preview_paths(nominal, base_shape):
    # Keep the crown compact like the reference instead of stretching it vertically.
    w=min(29.0,float(nominal)*.295)
    h=w*.46
    y=float(nominal)*(.315 if base_shape!="rect" else .255)
    lw=.35; r=max(.82,lw*2.45)
    p=_points(w,h,y)
    BL,L,VL,C,VR,R,BR=(p[k] for k in ("BL","L","VL","C","VR","R","BR"))
    trim=max(0.0,r-lw*.38)
    paths=[]
    for a,b,ta,tb in ((BL,L,0,trim),(L,VL,trim,0),(VL,C,0,trim),
                      (C,VR,trim,0),(VR,R,0,trim),(R,BR,trim,0)):
        paths.append(list(_shortened_segment(a,b,ta,tb).coords))
    xs=np.linspace(BL[0],BR[0],160)
    arch=max(.18,min(.36,w*.0105))
    ys=BL[1]+arch*(1-(xs/(w*.43))**2)
    paths.append(list(zip(xs,ys)))
    for x,yy in (L,C,R):
        t=np.linspace(0,2*np.pi,192)
        paths.append([(x+r*math.cos(a),yy+r*math.sin(a)) for a in t])
    return paths


def apply_fixes(engine):
    """Patch only the stamp Blender engine. Topper engine is intentionally untouched."""
    # Crown used for STL/3MF.
    engine._crown_geometry = crown_geometry
    engine._crown_preview_paths = crown_preview_paths

    original_mesh = engine._crown_mesh
    def crown_mesh(line_width, height, y, width=28.0, height_mm=15.0):
        # Ignore the old overly-tall requested ratio and use reference ratio.
        return original_mesh(line_width, height, y, width=width, height_mm=float(width)*.46)
    engine._crown_mesh = crown_mesh

    # Serif TTF skeletons produce short terminal branches that look like
    # accidental "tails" after buffering.  Remove them AFTER final fitting,
    # when thresholds are real millimetres.  This leaves long structural
    # strokes (including Cyrillic descenders) intact.
    original_fit = engine._fit_centerline
    def fit_centerline_clean(g, max_w, max_h):
        out = original_fit(g, max_w, max_h)
        try:
            out = engine._se._prune_short_terminal_spurs(out, max_spur_mm=1.35)
            out = engine._se._remove_tiny_centerline_parts(out, min_length_mm=.24)
            out = engine._se._smooth_text_centerlines(out)
            out = engine._se._prune_short_terminal_spurs(out, max_spur_mm=1.15)
        except Exception:
            engine.logger.exception("v2.3.5 serif-tail cleanup fallback")
        return out
    engine._fit_centerline = fit_centerline_clean
