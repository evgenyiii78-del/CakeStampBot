"""CakeStampBot v2.3.8 stamp-only local engine fixes. Topper untouched."""
from __future__ import annotations
import math
import numpy as np
from shapely.geometry import LineString, Point
from shapely.ops import unary_union


def _shortened_segment(a,b,trim_a=0.0,trim_b=0.0):
    ax,ay=a; bx,by=b; dx,dy=bx-ax,by-ay; ln=max(1e-9,math.hypot(dx,dy)); ux,uy=dx/ln,dy/ln
    return LineString([(ax+ux*trim_a,ay+uy*trim_a),(bx-ux*trim_b,by-uy*trim_b)])


def _points(width,height,yoff=0.0):
    # Reference crown: compact three-point silhouette, tall centre point,
    # shallow inner valleys, slightly tapered sides and almost straight base.
    w=float(width); h=float(height); y=float(yoff)
    return {
        "BL":(-w*.43,y-h*.34),
        "L":(-w*.325,y+h*.25),
        "VL":(-w*.145,y+h*.015),
        "C":(0.0,y+h*.49),
        "VR":(w*.145,y+h*.015),
        "R":(w*.325,y+h*.25),
        "BR":(w*.43,y-h*.34),
    }


def crown_geometry(width=29.0,height_mm=15.0,line_width=.45):
    w=float(width); h=float(height_mm); lw=max(.40,float(line_width)); r=max(1.10,w*.041)
    p=_points(w,h); BL,L,VL,C,VR,R,BR=(p[k] for k in ("BL","L","VL","C","VR","R","BR")); trim=max(0.0,r-lw*.48)
    segs=[_shortened_segment(BL,L,0,trim),_shortened_segment(L,VL,trim,0),_shortened_segment(VL,C,0,trim),
          _shortened_segment(C,VR,trim,0),_shortened_segment(VR,R,0,trim),_shortened_segment(R,BR,trim,0)]
    xs=np.linspace(BL[0],BR[0],180)
    # Very small upward bow, visually matching the supplied reference.
    ys=BL[1]+.10*(1-(xs/(w*.43))**2)
    segs.append(LineString(np.c_[xs,ys]))
    parts=[s.buffer(lw/2,cap_style=1,join_style=1,resolution=64) for s in segs]
    for x,y in (L,C,R):
        outer=Point(x,y).buffer(r,resolution=96); inner=Point(x,y).buffer(max(.20,r-lw),resolution=96)
        parts.append(outer.difference(inner))
    return unary_union(parts).buffer(0)


def crown_preview_paths(nominal,base_shape):
    w=min(29.0,float(nominal)*.30); h=w*.52; y=float(nominal)*(.315 if base_shape!="rect" else .25); lw=.45; r=max(1.10,w*.041)
    p=_points(w,h,y); BL,L,VL,C,VR,R,BR=(p[k] for k in ("BL","L","VL","C","VR","R","BR")); trim=max(0.0,r-lw*.48); paths=[]
    for a,b,ta,tb in ((BL,L,0,trim),(L,VL,trim,0),(VL,C,0,trim),(C,VR,trim,0),(VR,R,0,trim),(R,BR,trim,0)):
        paths.append(list(_shortened_segment(a,b,ta,tb).coords))
    xs=np.linspace(BL[0],BR[0],180); ys=BL[1]+.10*(1-(xs/(w*.43))**2); paths.append(list(zip(xs,ys)))
    for x,yy in (L,C,R):
        t=np.linspace(0,2*np.pi,180); paths.append([(x+r*math.cos(a),yy+r*math.sin(a)) for a in t])
    return paths


def apply_fixes(engine):
    engine._crown_geometry=crown_geometry
    engine._crown_preview_paths=crown_preview_paths

    # Do not alter stamp_engine globals: topper must remain completely untouched.
    original_mesh=engine._crown_mesh
    def crown_mesh(line_width,height,y,width=29.0,height_mm=15.0):
        # old mesh helper calls engine._crown_geometry dynamically, so geometry above is used
        return original_mesh(max(.45,line_width),height,y,width=width,height_mm=float(width)*.52)
    engine._crown_mesh=crown_mesh

    original_outline=engine._outline_to_centerline
    original_prune=engine._se._prune_short_terminal_spurs
    def outline_clean(outline_shape,ppm=None):
        # Higher sampling keeps Comic Neue curves continuous. Then remove only short
        # skeleton branches responsible for the visible hooks on я/ц/а.
        g=original_outline(outline_shape,ppm=72 if ppm is None else min(max(int(ppm),68),84))
        try:
            g=original_prune(g,max_spur_mm=.34)
            g=engine._se._remove_tiny_centerline_parts(g,min_length_mm=.18)
            g=engine._se._smooth_text_centerlines(g)
            g=original_prune(g,max_spur_mm=.28)
        except Exception:
            engine.logger.exception("v2.3.8 outline cleanup fallback")
        return g
    engine._outline_to_centerline=outline_clean

    original_fit=engine._fit_centerline
    def fit_centerline_clean(g,max_w,max_h):
        out=original_fit(g,max_w,max_h)
        try:
            out=original_prune(out,max_spur_mm=.30)
            out=engine._se._remove_tiny_centerline_parts(out,min_length_mm=.18)
            out=engine._se._smooth_text_centerlines(out)
        except Exception:
            engine.logger.exception("v2.3.8 centerline cleanup fallback")
        return out
    engine._fit_centerline=fit_centerline_clean
