"""CakeStampBot v1.9.2 automatic text fit for stamp.

Text is scaled on the cleaned unbuffered centerline so the final text block grows
to the available stamp area while keeping approximately 15 mm from the edge.
The final stroke is still exactly 0.25 mm. Topper is intentionally untouched.
"""
from __future__ import annotations

from shapely import affinity
from shapely.geometry import LineString, MultiLineString, GeometryCollection, Polygon, MultiPolygon
from shapely.ops import unary_union
from . import stamp_engine as _se

SAFE_MARGIN_MM = 15.0
LINE_GAP_FACTOR = 0.08
MIN_LINE_MM = 0.12
MIN_POLY_AREA_MM2 = 0.004


def _line_parts(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return [g for g in geom.geoms if not g.is_empty]
    if isinstance(geom, GeometryCollection) or hasattr(geom, "geoms"):
        out=[]
        for g in geom.geoms:
            if isinstance(g, LineString) and not g.is_empty:
                out.append(g)
            elif isinstance(g, MultiLineString):
                out.extend(x for x in g.geoms if not x.is_empty)
        return out
    return []


def _clean_centerline(geom):
    """Drop degenerate/micro line fragments without topology operations on lines."""
    parts=[]
    for line in _line_parts(geom):
        if line.length < MIN_LINE_MM:
            continue
        coords=[]
        last=None
        for x,y in line.coords:
            p=(round(float(x),6), round(float(y),6))
            if p != last:
                coords.append(p)
                last=p
        if len(coords) < 2:
            continue
        try:
            cleaned=LineString(coords)
            if not cleaned.is_empty and cleaned.length >= MIN_LINE_MM and cleaned.is_valid:
                parts.append(cleaned)
        except Exception:
            continue
    if not parts:
        return GeometryCollection()
    if len(parts)==1:
        return parts[0]
    return MultiLineString(parts)


def _fit_centerline_to_safe_area(line_geom, max_width_mm: float, max_height_mm: float):
    """Uniformly enlarge/reduce the whole text block to the 15 mm safe box."""
    line_geom=_clean_centerline(line_geom)
    if line_geom is None or line_geom.is_empty:
        return line_geom

    minx,miny,maxx,maxy=line_geom.bounds
    w=max(maxx-minx,1e-9)
    h=max(maxy-miny,1e-9)

    # AUTO-FIT: use the available safe area itself as the limiting size.
    # This fixes the previous behavior where requested text height capped the
    # scale and left long/multiline text too small in the center of the stamp.
    factor=min(float(max_width_mm)/w, float(max_height_mm)/h)

    scaled=affinity.scale(line_geom,xfact=factor,yfact=factor,origin=(0.0,0.0))
    bx0,by0,bx1,by1=scaled.bounds
    scaled=affinity.translate(
        scaled,
        xoff=-(bx0+bx1)/2.0,
        yoff=-(by0+by1)/2.0,
    )
    return _clean_centerline(scaled)


def _polygon_parts(shape):
    if shape is None or shape.is_empty:
        return []
    if isinstance(shape,Polygon):
        return [shape]
    if isinstance(shape,MultiPolygon):
        return list(shape.geoms)
    if hasattr(shape,"geoms"):
        return [g for g in shape.geoms if isinstance(g,Polygon)]
    return []


def _repair_stroke(shape):
    """Conservative polygon repair; avoids simplify/offset cycles that can lose vertices."""
    if shape is None or shape.is_empty:
        return shape
    try:
        repaired=shape.buffer(0)
    except Exception:
        repaired=shape

    parts=[]
    for poly in _polygon_parts(repaired):
        if poly.is_empty or poly.area < MIN_POLY_AREA_MM2:
            continue
        try:
            p=poly.buffer(0)
            if not p.is_empty and p.area >= MIN_POLY_AREA_MM2:
                parts.extend(_polygon_parts(p))
        except Exception:
            continue

    if not parts:
        return repaired
    try:
        return unary_union(parts).buffer(0)
    except Exception:
        return MultiPolygon(parts) if len(parts)>1 else parts[0]


def build_stamp_from_text(*, text, output_dir, base_size="105", base_shape="round",
                          line_width=0.25, font_choice="classic", text_path="normal",
                          text_size_mm=12.0, add_heart=False, layout_mode="assembled"):
    requested_size=max(10.0,min(16.0,float(text_size_mm)))
    exact_width=0.25
    line_count=max(1,len(str(text).splitlines()))

    nominal,rw,rh=_se.parse_size(base_size,base_shape)
    if base_shape=="rect":
        safe_w=max(10.0,float(rw)-2.0*SAFE_MARGIN_MM)
        safe_h=max(10.0,float(rh)-2.0*SAFE_MARGIN_MM)
    else:
        safe_w=max(10.0,float(nominal)-2.0*SAFE_MARGIN_MM)
        safe_h=safe_w

    original_stroke=_se._stroke_clean_single_line
    original_scene=_se._build_scene

    def sized_exact_stroke(centerline,_line_width):
        centerline=_fit_centerline_to_safe_area(centerline,safe_w,safe_h)
        if centerline is None or centerline.is_empty:
            raise RuntimeError("После масштабирования не осталось корректного centerline текста.")

        buffered=[]
        for ln in _line_parts(centerline):
            try:
                poly=ln.buffer(
                    exact_width/2.0,
                    cap_style=1,
                    join_style=1,
                    resolution=16,
                )
                if poly is not None and not poly.is_empty:
                    buffered.append(poly)
            except Exception:
                continue

        if not buffered:
            raise RuntimeError("Не удалось построить 0.25 мм stroke текста.")

        try:
            shape=unary_union(buffered)
        except Exception:
            polys=[]
            for item in buffered:
                polys.extend(_polygon_parts(_repair_stroke(item)))
            if not polys:
                raise RuntimeError("Не удалось восстановить геометрию stroke текста.")
            shape=MultiPolygon(polys) if len(polys)>1 else polys[0]

        return _repair_stroke(shape)

    def exact_preview_scene(*args,**kwargs):
        relief=kwargs.get("relief_shape")
        if relief is not None:
            kwargs["preview_shape"]=relief

        meta=kwargs.get("meta_extra") or {}
        meta.update({
            "requested_text_height_mm":requested_size,
            "requested_stroke_width_mm":exact_width,
            "text_line_count":line_count,
            "safe_margin_mm":SAFE_MARGIN_MM,
            "safe_text_width_mm":safe_w,
            "safe_text_height_mm":safe_h,
            "line_gap_factor":LINE_GAP_FACTOR,
            "text_fit_mode":"auto_fill_safe_box_15mm",
            "stroke_width_mode":"independent_exact_0.25mm_line_buffers",
            "geometry_stability":"v1.9.2",
        })
        kwargs["meta_extra"]=meta
        return original_scene(*args,**kwargs)

    _se._stroke_clean_single_line=sized_exact_stroke
    _se._build_scene=exact_preview_scene
    try:
        return _se.build_stamp_from_text(
            text=text,
            output_dir=output_dir,
            base_size=base_size,
            base_shape=base_shape,
            line_width=exact_width,
            font_choice=font_choice,
            text_path=text_path,
            add_heart=add_heart,
            layout_mode=layout_mode,
        )
    finally:
        _se._stroke_clean_single_line=original_stroke
        _se._build_scene=original_scene
