"""CakeStampBot v2.4.0 stamp-only local engine fixes. Topper untouched."""
from __future__ import annotations
import math
import numpy as np
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import unary_union


def _shortened_segment(a,b,trim_a=0.0,trim_b=0.0):
    ax,ay=a; bx,by=b; dx,dy=bx-ax,by-ay; ln=max(1e-9,math.hypot(dx,dy)); ux,uy=dx/ln,dy/ln
    return LineString([(ax+ux*trim_a,ay+uy*trim_a),(bx-ux*trim_b,by-uy*trim_b)])


def _points(width,height,yoff=0.0):
    """Geometry matched to the supplied reference crown.

    Lower corners sit inside the two outer jewels, matching the approved reference.
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


def crown_geometry(width=34.0,height_mm=17.0,line_width=.45):
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
    # v2.4.0: about 13% larger than the approved v2.3.9 crown.
    w=min(34.0,float(nominal)*.35); h=w*.50; y=float(nominal)*(.315 if base_shape!="rect" else .25); lw=.45; r=max(1.18,w*.043)
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
        # build_stamp_from_text_blender still passes the old 30 mm cap; enlarge it here
        # so preview and exported 3MF use the same v2.4.0 crown scale.
        effective_width=min(34.0,float(width)*1.1333333333)
        return original_mesh(max(.45,line_width),height,y,width=effective_width,height_mm=effective_width*.50)
    engine._crown_mesh=crown_mesh

    # The old 0.025 mm path sampling creates enormous Blender meshes/ASCII STL files.
    # 0.08 mm is still far below the 0.25 mm stamp line width, but cuts point count
    # by roughly 3x and prevents the worker timeout on long 16 mm Comic text.
    original_resample=engine._resample_path
    def resample_fast(line,step=None):
        return original_resample(line,step=.08)
    engine._resample_path=resample_fast

    # Junction-safe TTF centerline. Do not trim LineString endpoints: skeleton junctions
    # are represented by multiple LineStrings meeting at those endpoints.
    def outline_clean(outline_shape,ppm=None):
        if outline_shape is None or outline_shape.is_empty:
            raise RuntimeError("Пустая TTF-геометрия.")
        minx,miny,maxx,maxy=outline_shape.bounds
        pad=2.0
        # v2.4.0: 84 px/mm was needlessly expensive for a physical 0.25 mm stroke.
        # 52 px/mm gives ~13 raster pixels across that stroke and is substantially faster.
        px=int(max(48,min(64,52 if ppm is None else int(ppm))))
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
        parts=[]
        for ln in _line_parts(c):
            if ln.length < .055: continue
            sm=engine._se._smooth_line(ln,refinements=3,simplify_mm=.012)
            if sm is not None and not sm.is_empty: parts.append(sm)
        if not parts: raise RuntimeError("Centerline текста пуст после очистки.")
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
