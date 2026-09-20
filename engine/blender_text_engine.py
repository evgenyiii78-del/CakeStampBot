"""CakeStampBot v2.1.1 Blender Stamp Engine: text + optional heart/crown."""
from __future__ import annotations
import json, logging, math, os, shutil, subprocess
from pathlib import Path
import numpy as np, trimesh
from PIL import Image, ImageDraw
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, GeometryCollection
from .common import export_bundle, heart_mesh, crown_mesh, mask_to_centerline_line, parse_size
from . import stamp_engine as _se
from .ttf_vector_engine import text_to_ttf_geometry
logger=logging.getLogger("CakeStampEngine.BlenderText")
BASE_H=0.6; RELIEF_H=6.5; SAFE_MARGIN_MM=15.0; LINE_WIDTH_MM=0.25; CENTERLINE_PPM=96; RESAMPLE_STEP_MM=0.025; PREVIEW_SIZE=1400; PREVIEW_SS=3

def blender_binary():
    configured=os.getenv("BLENDER_BIN","").strip()
    if configured and Path(configured).exists(): return configured
    return shutil.which("blender")
def blender_available(): return bool(blender_binary())
def _line_parts(geom):
    if geom is None or geom.is_empty:return []
    if isinstance(geom,LineString):return [geom]
    if isinstance(geom,MultiLineString):return [g for g in geom.geoms if not g.is_empty]
    out=[]
    for g in getattr(geom,"geoms",[]):
        if isinstance(g,LineString) and not g.is_empty:out.append(g)
        elif isinstance(g,MultiLineString):out.extend(x for x in g.geoms if not x.is_empty)
    return out
def _outline_to_centerline(outline_shape,ppm=CENTERLINE_PPM):
    if outline_shape is None or outline_shape.is_empty:raise RuntimeError("Пустая TTF-геометрия.")
    minx,miny,maxx,maxy=outline_shape.bounds; pad=2.0; ppm=int(max(72,min(120,ppm))); W=max(128,int(round((maxx-minx+2*pad)*ppm))); H=max(128,int(round((maxy-miny+2*pad)*ppm))); mask=Image.new("L",(W,H),0); d=ImageDraw.Draw(mask)
    def xy(x,y):return ((x-minx+pad)*ppm,(maxy-y+pad)*ppm)
    polys=[outline_shape] if outline_shape.geom_type=="Polygon" else list(outline_shape.geoms) if outline_shape.geom_type=="MultiPolygon" else [g for g in getattr(outline_shape,"geoms",[]) if g.geom_type=="Polygon"]
    for p in polys:
        d.polygon([xy(x,y) for x,y in p.exterior.coords],fill=255)
        for ring in p.interiors:d.polygon([xy(x,y) for x,y in ring.coords],fill=0)
    c=mask_to_centerline_line(mask,ppm)
    if c is None or c.is_empty:raise RuntimeError("Не удалось получить centerline.")
    x0,y0,x1,y1=c.bounds;c=affinity.translate(c,xoff=-(x0+x1)/2,yoff=-(y0+y1)/2);c=_se._remove_tiny_centerline_parts(c,min_length_mm=.18);c=_se._prune_short_terminal_spurs(c,max_spur_mm=.48);c=_se._smooth_text_centerlines(c);c=_se._remove_tiny_centerline_parts(c,min_length_mm=.18);return _se._prune_short_terminal_spurs(c,max_spur_mm=.34)
def _fit_centerline(g,max_w,max_h):
    x0,y0,x1,y1=g.bounds;f=min(float(max_w)/max(x1-x0,1e-9),float(max_h)/max(y1-y0,1e-9));g=affinity.scale(g,xfact=f,yfact=f,origin=(0,0))
    try:g=_se._smooth_text_centerlines(g)
    except Exception:pass
    x0,y0,x1,y1=g.bounds;return affinity.translate(g,xoff=-(x0+x1)/2,yoff=-(y0+y1)/2)
def _warp_centerline(g,diameter,mode):
    if mode=="normal" or g is None or g.is_empty:return g
    x0,y0,x1,y1=g.bounds;width=max(x1-x0,1e-6);radius=max(10.0,float(diameter)*.39);span=math.radians(330) if mode=="full" else min(math.radians(160),max(math.radians(80),width/radius));cx=(x0+x1)/2;cy=(y0+y1)/2;warped=[]
    for line in _line_parts(g):
        pts=[]
        for x,y in line.coords:
            t=(x-cx)/width
            if mode=="bottom":a=-math.pi/2+t*span;rr=radius-(y-cy)
            else:a=math.pi/2-t*span;rr=radius+(y-cy)
            pts.append((rr*math.cos(a),rr*math.sin(a)))
        if len(pts)>=2:warped.append(LineString(pts))
    return GeometryCollection() if not warped else warped[0] if len(warped)==1 else MultiLineString(warped)
def _resample_path(line,step=RESAMPLE_STEP_MM):
    if line.length<=step:return [(float(x),float(y)) for x,y in line.coords]
    n=max(8,int(math.ceil(line.length/step))+1);return [(float(p.x),float(p.y)) for p in (line.interpolate(float(d)) for d in np.linspace(0,float(line.length),n))]
def _crown_preview_paths(nominal,base_shape):
    w=min(28.0,nominal*.30);h=w*.54;y=(nominal*.31 if base_shape!="rect" else nominal*.25); pts=[(-w/2,y-h/2),(-w*.38,y+h*.28),(-w*.16,y-h*.02),(0,y+h/2),(w*.16,y-h*.02),(w*.38,y+h*.28),(w/2,y-h/2),(-w/2,y-h/2)]; paths=[pts]
    for x,yy in [(-w*.38,y+h*.28),(0,y+h/2),(w*.38,y+h*.28)]:
        r=max(1.2,LINE_WIDTH_MM*2.8);t=np.linspace(0,2*np.pi,80);paths.append([(x+r*math.cos(a),yy+r*math.sin(a)) for a in t])
    return paths
def _make_preview(path,base_shape,nominal,rw,rh,paths,note,add_crown=False):
    out=PREVIEW_SIZE;ss=PREVIEW_SS;W=H=out*ss;pad=95*ss;img=Image.new("RGB",(W,H),(246,243,235));d=ImageDraw.Draw(img);sx=nominal if base_shape!="rect" else rw;sy=nominal if base_shape!="rect" else rh;scale=min((W-2*pad)/sx,(H-2*pad)/sy)
    def xy(x,y):return(W/2+x*scale,H/2-y*scale)
    ow=5*ss
    if base_shape=="rect":x0,y0=xy(-rw/2,rh/2);x1,y1=xy(rw/2,-rh/2);d.rounded_rectangle((x0,y0,x1,y1),radius=24*ss,fill=(232,195,121),outline=(135,91,38),width=ow)
    else:x0,y0=xy(-nominal/2,nominal/2);x1,y1=xy(nominal/2,-nominal/2);d.ellipse((x0,y0,x1,y1),fill=(232,195,121),outline=(135,91,38),width=ow)
    pw=max(3*ss,int(round(LINE_WIDTH_MM*scale)))
    for pts in paths+(_crown_preview_paths(nominal,base_shape) if add_crown else []):
        if len(pts)<2:continue
        q=[xy(x,y) for x,y in pts];d.line(q,fill=(25,92,58),width=pw,joint="curve")
    d.text((100*ss,45*ss),f"CakeStampBot v2.1.1 · Blender Stamp · {note}",fill=(35,35,35));img.resize((out,out),Image.Resampling.LANCZOS).save(path,optimize=True)
def build_stamp_from_text_blender(*,text,output_dir,base_size="105",base_shape="round",line_width=.25,font_choice="classic",text_path="normal",text_size_mm=12.0,add_heart=False,add_crown=False,layout_mode="assembled"):
    blender=blender_binary()
    if not blender:raise RuntimeError("Blender executable not found")
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True);nominal,rw,rh=parse_size(base_size,base_shape);mode=str(text_path or "normal").lower();mode=mode if mode in {"normal","top","bottom","full"} else "normal";mode="normal" if base_shape!="round" else mode;safe_w=max(10,float(rw if base_shape=="rect" else nominal)-2*SAFE_MARGIN_MM);safe_h=max(10,float(rh if base_shape=="rect" else nominal)-2*SAFE_MARGIN_MM)
    # Reserve upper area for crown so text never overlaps it.
    if add_crown and mode=="normal":safe_h=max(10,safe_h-min(18.0,nominal*.20))
    ttf=text_to_ttf_geometry(text,fonts_dir=Path(__file__).resolve().parent.parent/"fonts",font_choice=font_choice,target_width_mm=max(8,safe_w),target_height_mm=max(8,safe_h),line_spacing=.86,curve_steps=48);c=_fit_centerline(_outline_to_centerline(ttf.geometry),safe_w,safe_h)
    if add_crown and mode=="normal":c=affinity.translate(c,yoff=-min(6.0,nominal*.055))
    if mode!="normal":c=_warp_centerline(c,nominal,mode)
    paths=[]
    for line in _line_parts(c):
        pts=_resample_path(line)
        if len(pts)>=2:paths.append(pts)
    if not paths:raise RuntimeError("Blender engine: centerline paths are empty")
    safe_name=_se._safe_text_filename(text);job_path=output/f"{safe_name}_blender_job.json";base_stl=output/f"{safe_name}_Blender_Base.stl";relief_stl=output/f"{safe_name}_Blender_Relief.stl";job={"base_shape":base_shape,"nominal":float(nominal),"rect_w":float(rw),"rect_h":float(rh),"base_height":BASE_H,"relief_height":RELIEF_H,"line_width":LINE_WIDTH_MM,"paths":paths,"base_stl":str(base_stl),"relief_stl":str(relief_stl)};job_path.write_text(json.dumps(job,ensure_ascii=False),encoding="utf-8");script=Path(__file__).resolve().parent.parent/"scripts"/"blender_generate_stamp.py";proc=subprocess.run([blender,"-b","--python",str(script),"--","--job",str(job_path)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
    if proc.returncode!=0:logger.error("Blender failed:\n%s",proc.stdout[-6000:]);raise RuntimeError(f"Blender завершился с кодом {proc.returncode}")
    if not base_stl.exists() or not relief_stl.exists():raise RuntimeError("Blender не создал STL-файлы")
    base=trimesh.load(str(base_stl),force="mesh");relief=trimesh.load(str(relief_stl),force="mesh");base.metadata["name"]="BlenderBase";relief.metadata["name"]="BlenderRelief";scene=trimesh.Scene();scene.add_geometry(base.copy(),geom_name="Base",node_name="Base");r=relief.copy();r.apply_translation([0,0,BASE_H]);scene.add_geometry(r,geom_name="Relief_Blender",node_name="Relief_Blender");stls=[str(base_stl),str(relief_stl)]
    if add_heart:
        heart=heart_mesh(.35,RELIEF_H,-nominal*.30);h=heart.copy();h.apply_translation([0,0,BASE_H]);scene.add_geometry(h,geom_name="Heart",node_name="Heart");heart_stl=output/f"{safe_name}_Heart.stl";heart.export(str(heart_stl));stls.append(str(heart_stl))
    if add_crown:
        cw=min(28.0,nominal*.30);cy=nominal*.31 if base_shape!="rect" else rh*.30;crown=crown_mesh(.35,RELIEF_H,cy,width=cw,height_mm=cw*.54);cr=crown.copy();cr.apply_translation([0,0,BASE_H]);scene.add_geometry(cr,geom_name="Crown",node_name="Crown");crown_stl=output/f"{safe_name}_Crown.stl";crown.export(str(crown_stl));stls.append(str(crown_stl))
    preview=output/f"{safe_name}_blender_preview.png";_make_preview(preview,base_shape,nominal,rw,rh,paths,mode,add_crown=add_crown);meta={"version":"2.1.1","engine":"blender_stamp_text","font_choice":font_choice,"font_path":ttf.font_path,"base_shape":base_shape,"base_size":base_size,"base_height_mm":BASE_H,"relief_height_mm":RELIEF_H,"line_width_mm":LINE_WIDTH_MM,"safe_margin_mm":SAFE_MARGIN_MM,"text_path":mode,"add_heart":bool(add_heart),"add_crown":bool(add_crown),"layout_mode":layout_mode};suffix="BLENDER_STAMP_SEPARATE" if layout_mode=="separate" else "BLENDER_STAMP_ASSEMBLED";return export_bundle(output,safe_name,scene,str(preview),stls,meta,suffix)