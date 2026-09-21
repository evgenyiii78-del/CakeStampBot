"""CakeStampBot v2.3.6 stamp-only geometry/centerline fixes. Topper untouched."""
from __future__ import annotations
import math
import numpy as np
from shapely.geometry import LineString, Point
from shapely.ops import unary_union


def _shortened_segment(a,b,trim_a=0.0,trim_b=0.0):
    ax,ay=a;bx,by=b;dx,dy=bx-ax,by-ay;ln=max(1e-9,math.hypot(dx,dy));ux,uy=dx/ln,dy/ln
    return LineString([(ax+ux*trim_a,ay+uy*trim_a),(bx-ux*trim_b,by-uy*trim_b)])


def _points(width,height,yoff=0.0):
    # Reference: tall elegant crown, centre jewel clearly above side jewels,
    # shallow inner valleys and tapered sides.
    w=float(width);h=float(height);y=float(yoff)
    return {"BL":(-w*.405,y-h*.36),"L":(-w*.305,y+h*.27),"VL":(-w*.135,y+h*.015),
            "C":(0.0,y+h*.52),"VR":(w*.135,y+h*.015),"R":(w*.305,y+h*.27),"BR":(w*.405,y-h*.36)}


def crown_geometry(width=28.0,height_mm=18.2,line_width=.35):
    w=float(width);h=float(height_mm);lw=float(line_width);r=max(1.15,w*.043)
    p=_points(w,h);BL,L,VL,C,VR,R,BR=(p[k] for k in ("BL","L","VL","C","VR","R","BR"));trim=max(0.0,r-lw*.42)
    segs=[_shortened_segment(BL,L,0,trim),_shortened_segment(L,VL,trim,0),_shortened_segment(VL,C,0,trim),
          _shortened_segment(C,VR,trim,0),_shortened_segment(VR,R,0,trim),_shortened_segment(R,BR,trim,0)]
    xs=np.linspace(BL[0],BR[0],180);arch=max(.22,min(.48,w*.014));ys=BL[1]+arch*(1-(xs/(w*.405))**2);segs.append(LineString(np.c_[xs,ys]))
    parts=[s.buffer(lw/2,cap_style=1,join_style=1,resolution=96) for s in segs]
    for x,y in (L,C,R):
        outer=Point(x,y).buffer(r,resolution=128);inner=Point(x,y).buffer(max(.20,r-lw),resolution=128);parts.append(outer.difference(inner))
    return unary_union(parts).buffer(0)


def crown_preview_paths(nominal,base_shape):
    w=min(31.5,float(nominal)*.30);h=w*.65;y=float(nominal)*(.305 if base_shape!="rect" else .25);lw=.35;r=max(1.15,w*.043)
    p=_points(w,h,y);BL,L,VL,C,VR,R,BR=(p[k] for k in ("BL","L","VL","C","VR","R","BR"));trim=max(0.0,r-lw*.42);paths=[]
    for a,b,ta,tb in ((BL,L,0,trim),(L,VL,trim,0),(VL,C,0,trim),(C,VR,trim,0),(VR,R,0,trim),(R,BR,trim,0)):
        paths.append(list(_shortened_segment(a,b,ta,tb).coords))
    xs=np.linspace(BL[0],BR[0],180);arch=max(.22,min(.48,w*.014));ys=BL[1]+arch*(1-(xs/(w*.405))**2);paths.append(list(zip(xs,ys)))
    for x,yy in (L,C,R):
        t=np.linspace(0,2*np.pi,192);paths.append([(x+r*math.cos(a),yy+r*math.sin(a)) for a in t])
    return paths


def apply_fixes(engine):
    engine._crown_geometry=crown_geometry;engine._crown_preview_paths=crown_preview_paths
    original_mesh=engine._crown_mesh
    def crown_mesh(line_width,height,y,width=28.0,height_mm=15.0):
        return original_mesh(line_width,height,y,width=width,height_mm=float(width)*.65)
    engine._crown_mesh=crown_mesh

    # The previous 96 px/mm skeleton raster was unnecessarily expensive and
    # caused Bothost jobs to hit their time limit. 56 px/mm is still far finer
    # than a 0.25 mm printable stroke while substantially reducing work.
    original_outline=engine._outline_to_centerline
    def outline_fast(outline_shape,ppm=None):
        return original_outline(outline_shape,ppm=56 if ppm is None else min(int(ppm),64))
    engine._outline_to_centerline=outline_fast

    # Do not aggressively prune serif/comic glyph skeletons. Large pruning was
    # responsible for damaged terminals and artificial tails. Keep only tiny
    # raster branches, then smooth once in real millimetres.
    original_fit=engine._fit_centerline
    def fit_centerline_clean(g,max_w,max_h):
        out=original_fit(g,max_w,max_h)
        try:
            out=engine._se._remove_tiny_centerline_parts(out,min_length_mm=.18)
            out=engine._se._prune_short_terminal_spurs(out,max_spur_mm=.42)
            out=engine._se._smooth_text_centerlines(out)
        except Exception:
            engine.logger.exception("v2.3.6 centerline cleanup fallback")
        return out
    engine._fit_centerline=fit_centerline_clean
