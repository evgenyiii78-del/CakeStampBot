"""CakeStampBot v2.3.9 stamp-only local engine fixes. Topper untouched."""
from __future__ import annotations
import math
import numpy as np
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, GeometryCollection, Point
from shapely.ops import unary_union


def _shortened_segment(a,b,trim_a=0.0,trim_b=0.0):
    ax,ay=a; bx,by=b; dx,dy=bx-ax,by-ay; ln=max(1e-9,math.hypot(dx,dy)); ux,uy=dx/ln,dy/ln
    return LineString([(ax+ux*trim_a,ay+uy*trim_a),(bx-ux*trim_b,by-uy*trim_b)])


def _points(width,height,yoff=0.0):
    """Geometry matched to the supplied reference crown.

    Important visual feature: the lower corners sit INSIDE the two outer jewels.
    The old crown did the opposite, which is why it looked wide/trapezoidal.
    """
    w=float(width); h=float(height); y=float(yoff)
    return {
        "BL":(-w*.285,y-h*.38),
        "L": (-w*.355,y+h*.23),
        "VL":(-w*.145,y-h*.015),
        "C": (0.0,y+h*.50),
        "VR":(w*.145,y-h*.015),
        "R": (w*.355,y+h*.23),
        "BR":(w*.285,y-h*.38),
    }


def crown_geometry(width=30.0,height_mm=15.0,line_width=.45):
    w=float(width); h=float(height_mm); lw=max(.40,float(line_width)); r=max(1.18,w*.043)
    p=_points(w,h); BL,L,VL,C,VR,R,BR=(p[k] for k in ("BL","L","VL","C","VR","R","BR")); trim=max(0.0,r-lw*.48)
    segs=[
        _shortened_segment(BL,L,0,trim),
        _shortened_segment(L,VL,trim,0),
        _shortened_segment(VL,C,0,trim),
        _shortened_segment(C,VR,trim,0),
        _shortened_segment(VR,R,0,trim),
        _shortened_segment(R,BR,trim,0),
    ]
    # Reference base is shallow and almost horizontal.
    xs=np.linspace(BL[0],BR[0],180)
    ys=BL[1]+.12*(1-(xs/(w*.285))**2)
    segs.append(LineString(np.c_[xs,ys]))
    parts=[s.buffer(lw/2,cap_style=1,join_style=1,resolution=64) for s in segs]
    for x,y in (L,C,R):
        outer=Point(x,y).buffer(r,resolution=96)
        inner=Point(x,y).buffer(max(.22,r-lw),resolution=96)
        parts.append(outer.difference(inner))
    return unary_union(parts).buffer(0)


def crown_preview_paths(nominal,base_shape):
    w=min(30.0,float(nominal)*.31); h=w*.50; y=float(nominal)*(.315 if base_shape!="rect" else .25); lw=.45; r=max(1.18,w*.043)
    p=_points(w,h,y); BL,L,VL,C,VR,R,BR=(p[k] for k in ("BL","L","VL","C","VR","R","BR")); trim=max(0.0,r-lw*.48); paths=[]
    for a,b,ta,tb in ((BL,L,0,trim),(L,VL,trim,0),(VL,C,0,trim),(C,VR,trim,0),(VR,R,0,trim),(R,BR,trim,0)):
        paths.append(list(_shortened_segment(a,b,ta,tb).coords))
    xs=np.linspace(BL[0],BR[0],180); ys=BL[1]+.12*(1-(xs/(w*.285))**2); paths.append(list(zip(xs,ys)))
    for x,yy in (L,C,R):
        t=np.linspace(0,2*np.pi,180); paths.append([(x+r*math.cos(a),yy+r*math.sin(a)) for a in t])
    return paths


def _line_parts(g):
    if g is None or g.is_empty: return []
    if isinstance(g,LineString): return [g]
    if isinstance(g,MultiLineString): return [x for x in g.geoms if not x.is_empty]
    out=[]
    for x in getattr(g,"geoms",[]):
        if isinstance(x,LineString) and not x.is_empty: out.append(x)
        elif isinstance(x,MultiLineString): out.extend(y for y in x.geoms if not y.is_empty)
    return out


def apply_fixes(engine):
    engine._crown_geometry=crown_geometry
    engine._crown_preview_paths=crown_preview_paths

    original_mesh=engine._crown_mesh
    def crown_mesh(line_width,height,y,width=30.0,height_mm=15.0):
        return original_mesh(max(.45,line_width),height,y,width=width,height_mm=float(width)*.50)
    engine._crown_mesh=crown_mesh

    # v2.3.9: DO NOT use the old cubic smoother/pruner for TTF stamp text.
    # The cubic routine trims every LineString end. Skeleton junctions are represented
    # by several LineStrings meeting at one point, so trimming those ends creates the
    # visible breaks in я/а/ц. Pruning then makes the breaks larger.
    # Build the centerline locally and use endpoint-preserving Chaikin smoothing only.
    def outline_clean(outline_shape,ppm=None):
        if outline_shape is None or outline_shape.is_empty:
            raise RuntimeError("Пустая TTF-геометрия.")
        minx,miny,maxx,maxy=outline_shape.bounds
        pad=2.0; px=int(max(76,min(104,84 if ppm is None else int(ppm))))
        W=max(128,int(round((maxx-minx+2*pad)*px))); H=max(128,int(round((maxy-miny+2*pad)*px)))
        mask=engine.Image.new("L",(W,H),0); d=engine.ImageDraw.Draw(mask)
        def xy(x,y): return ((x-minx+pad)*px,(maxy-y+pad)*px)
        polys=[outline_shape] if outline_shape.geom_type=="Polygon" else list(outline_shape.geoms) if outline_shape.geom_type=="MultiPolygon" else [g for g in getattr(outline_shape,"geoms",[]) if g.geom_type=="Polygon"]
        for poly in polys:
            d.polygon([xy(x,y) for x,y in poly.exterior.coords],fill=255)
            for ring in poly.interiors: d.polygon([xy(x,y) for x,y in ring.coords],fill=0)
        c=engine.mask_to_centerline_line(mask,px)
        if c is None or c.is_empty: raise RuntimeError("Не удалось получить centerline.")
        x0,y0,x1,y1=c.bounds
        c=affinity.translate(c,xoff=-(x0+x1)/2,yoff=-(y0+y1)/2)
        # Chaikin implementation in stamp_engine explicitly preserves first/last point.
        # That keeps all glyph junctions connected.
        parts=[]
        for ln in _line_parts(c):
            if ln.length < .055: continue
            sm=engine._se._smooth_line(ln,refinements=3,simplify_mm=.012)
            if sm is not None and not sm.is_empty: parts.append(sm)
        if not parts: raise RuntimeError("Centerline текста пуст после очистки.")
        # Snap tiny raster discrepancies back together, but never trim endpoints.
        return unary_union(parts)
    engine._outline_to_centerline=outline_clean

    def fit_centerline_clean(g,max_w,max_h):
        if g is None or g.is_empty: return g
        x0,y0,x1,y1=g.bounds
        f=min(float(max_w)/max(x1-x0,1e-9),float(max_h)/max(y1-y0,1e-9))
        out=affinity.scale(g,xfact=f,yfact=f,origin=(0,0))
        parts=[]
        for ln in _line_parts(out):
            sm=engine._se._smooth_line(ln,refinements=2,simplify_mm=.010)
            if sm is not None and not sm.is_empty: parts.append(sm)
        out=unary_union(parts) if parts else out
        x0,y0,x1,y1=out.bounds
        return affinity.translate(out,xoff=-(x0+x1)/2,yoff=-(y0+y1)/2)
    engine._fit_centerline=fit_centerline_clean
