import os, json, zipfile, logging
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
import trimesh
from skimage.morphology import skeletonize, remove_small_objects
from skimage.filters import threshold_otsu
from shapely.geometry import LineString, Polygon, MultiPolygon, box
from shapely.ops import unary_union, triangulate

logger=logging.getLogger('CakeStampEngine')
@dataclass
class ModelResult:
    project_3mf:str; preview_png:str; bundle_zip:str; output_dir:str

def find_font_path(font_choice='classic'):
    choice=(font_choice or 'classic').lower()
    env={'classic':'CAKESTAMP_FONT_CLASSIC','comic':'CAKESTAMP_FONT_COMIC','gost':'CAKESTAMP_FONT_GOST'}
    p=os.getenv(env.get(choice,'CAKESTAMP_FONT_CLASSIC')) or os.getenv('CAKESTAMP_FONT')
    if p and os.path.exists(p): return p
    bundled={'classic':['fonts/Classic.ttf','/app/fonts/Classic.ttf'], 'comic':['fonts/Comic.ttf','/app/fonts/Comic.ttf'], 'gost':['fonts/GOST.ttf','/app/fonts/GOST.ttf','fonts/GOST-type-AU.ttf','/app/fonts/GOST-type-AU.ttf']}
    for p in bundled.get(choice,[])+bundled['classic']:
        if os.path.exists(p): return p
    candidates={
        'classic':['/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',r'C:\Windows\Fonts\times.ttf',r'C:\Windows\Fonts\arial.ttf'],
        'comic':[r'C:\Windows\Fonts\comic.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'],
        'gost':[r'C:\Windows\Fonts\GOST type AU.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']}
    for p in candidates.get(choice,[])+candidates['classic']:
        if os.path.exists(p): return p
    for base in ['/usr/share/fonts','/usr/local/share/fonts','/app/fonts']:
        if os.path.isdir(base):
            for root,_,files in os.walk(base):
                for fn in files:
                    if fn.lower().endswith(('.ttf','.otf')): return os.path.join(root,fn)
    raise FileNotFoundError('Не найден TTF-шрифт. Используйте Dockerfile с fonts-dejavu-core или CAKESTAMP_FONT_CLASSIC.')

def safe_name(s, fallback='model'):
    out=''.join(c if c.isalnum() or c in '_-' else '_' for c in str(s))
    out='_'.join(x for x in out.split('_') if x)
    return out[:48] or fallback

def render_text_mask(text, canvas_mm=90, px_per_mm=24, font_choice='classic'):
    margin=90; n=int(canvas_mm*px_per_mm)+2*margin
    img=Image.new('L',(n,n),0); d=ImageDraw.Draw(img); lines=str(text).split('\n')
    font_path=find_font_path(font_choice); fs=int(n*.17)
    while fs>20:
        font=ImageFont.truetype(font_path,fs); b=[d.textbbox((0,0),ln,font=font) for ln in lines]
        widths=[x[2]-x[0] for x in b]; heights=[x[3]-x[1] for x in b]; gap=int(fs*.16)
        if max(widths or [0])<n*.80 and sum(heights)+gap*(len(lines)-1)<n*.65: break
        fs-=3
    font=ImageFont.truetype(font_path,fs); b=[d.textbbox((0,0),ln,font=font) for ln in lines]
    heights=[x[3]-x[1] for x in b]; gap=int(fs*.16); y=(n-(sum(heights)+gap*(len(lines)-1)))//2-20
    for ln,bb,h in zip(lines,b,heights):
        x=(n-(bb[2]-bb[0]))//2; d.text((x,y-bb[1]),ln,fill=255,font=font); y+=h+gap
    return np.array(img)>40

def render_image_mask(path, canvas_mm=82, px_per_mm=24):
    margin=90; n=int(canvas_mm*px_per_mm)+2*margin
    src=Image.open(path).convert('L'); src=ImageOps.autocontrast(src); src.thumbnail((n-2*margin,n-2*margin))
    img=Image.new('L',(n,n),255); img.paste(src,((n-src.width)//2,(n-src.height)//2)); img=img.filter(ImageFilter.GaussianBlur(.6))
    a=np.array(img); th=threshold_otsu(a) if a.size else 180; mask=a<th
    if mask.mean()>.45: mask=a>th
    return remove_small_objects(mask.astype(bool),min_size=20)

NEI=[(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
def skeleton_to_polylines(skel):
    coords=set(map(tuple,np.argwhere(skel)))
    def ns(p):
        y,x=p; return [(y+dy,x+dx) for dy,dx in NEI if (y+dy,x+dx) in coords]
    def ek(a,b): return tuple(sorted([a,b]))
    degree={p:len(ns(p)) for p in coords}; nodes={p for p,d in degree.items() if d!=2}; vis=set(); lines=[]
    for start in list(nodes):
        for nb in ns(start):
            if ek(start,nb) in vis: continue
            path=[start,nb]; vis.add(ek(start,nb)); prev,cur=start,nb
            while cur not in nodes:
                nxts=[q for q in ns(cur) if q!=prev]
                if not nxts: break
                nxt=nxts[0]
                if ek(cur,nxt) in vis: break
                vis.add(ek(cur,nxt)); path.append(nxt); prev,cur=cur,nxt
            if len(path)>=2: lines.append(path)
    for p in coords:
        for q in ns(p):
            if p<q and ek(p,q) not in vis:
                path=[p,q]; vis.add(ek(p,q)); prev,cur=p,q
                while True:
                    nxts=[r for r in ns(cur) if r!=prev and ek(cur,r) not in vis]
                    if not nxts: break
                    nxt=nxts[0]; vis.add(ek(cur,nxt)); path.append(nxt); prev,cur=cur,nxt
                    if cur==p: break
                if len(path)>=3: lines.append(path)
    return lines

def chaikin(points, n=4):
    pts=[tuple(map(float,p)) for p in points]
    for _ in range(n):
        if len(pts)<3: break
        out=[pts[0]]
        for a,b in zip(pts[:-1],pts[1:]):
            a=np.array(a); b=np.array(b); out.append(tuple(.75*a+.25*b)); out.append(tuple(.25*a+.75*b))
        out.append(pts[-1]); pts=out
    return pts

def resample(line, step=.16):
    if line.length<=step: return line
    ds=np.linspace(0,line.length,max(3,int(line.length/step)))
    ps=[line.interpolate(d) for d in ds]
    return LineString([(p.x,p.y) for p in ps])

def mask_to_centerline_shape(mask, px_per_mm=24, line_width=.45, smooth=.30):
    skel=skeletonize(mask); lines=skeleton_to_polylines(skel); h,w=mask.shape; mm=1/px_per_mm; geoms=[]
    for path in lines:
        pts=[(x*mm,(h-y)*mm) for y,x in path]
        if len(pts)<2: continue
        line=LineString(chaikin(pts,4))
        if line.length<.65: continue
        line=line.simplify(smooth,preserve_topology=False)
        if line.length<.65: continue
        line=resample(line,.16)
        geoms.append(line.buffer(line_width/2,cap_style=1,join_style=1,resolution=64))
    if not geoms: return None
    merged=unary_union(geoms).buffer(0); eps=max(.018,line_width*.10)
    return merged.buffer(eps,resolution=64).buffer(-eps,resolution=64).buffer(0).simplify(.015,preserve_topology=True).buffer(0)

def extrude_poly(poly,height,z0=0):
    if poly.is_empty or poly.area<=0: return None
    verts=[]; faces=[]; vmap={}
    def v(x,y,z):
        k=(round(float(x),5),round(float(y),5),round(float(z),5))
        if k not in vmap: vmap[k]=len(verts); verts.append((float(x),float(y),float(z)))
        return vmap[k]
    def side(coords):
        for (x1,y1),(x2,y2) in zip(coords[:-1],coords[1:]):
            a,b,c,d=v(x1,y1,z0),v(x2,y2,z0),v(x2,y2,z0+height),v(x1,y1,z0+height)
            faces.extend([[a,b,c],[a,c,d]])
    for tri in triangulate(poly):
        rp=tri.representative_point()
        if not (poly.contains(rp) or poly.touches(rp)): continue
        cs=list(tri.exterior.coords)[:3]; top=[v(x,y,z0+height) for x,y in cs]; bot=[v(x,y,z0) for x,y in cs]
        faces.append(top); faces.append(bot[::-1])
    side(list(poly.exterior.coords))
    for inn in poly.interiors: side(list(inn.coords))
    if not verts or not faces: return None
    return trimesh.Trimesh(vertices=np.asarray(verts),faces=np.asarray(faces),process=True)

def extrude_shape(shape,height,name):
    if shape is None: raise RuntimeError('Пустая геометрия после обработки.')
    polys=[shape] if isinstance(shape,Polygon) else list(shape.geoms if isinstance(shape,MultiPolygon) else getattr(shape,'geoms',[]))
    meshes=[]
    for p in polys:
        if p.area>=.02:
            m=extrude_poly(p.buffer(0),height)
            if m is not None and len(m.faces): meshes.append(m)
    if not meshes: raise RuntimeError(f'Не удалось построить mesh: {name}')
    mesh=trimesh.util.concatenate(meshes); mesh.metadata['name']=name; return mesh

def center_and_fit(mesh,max_w,max_h,y_shift=0):
    b=mesh.bounds; w=b[1,0]-b[0,0]; h=b[1,1]-b[0,1]; s=min(max_w/w,max_h/h,1.0); mesh.apply_scale([s,s,1])
    b=mesh.bounds; mesh.apply_translation([-(b[0,0]+b[1,0])/2, -(b[0,1]+b[1,1])/2 + y_shift, 0]); return mesh

def make_cylinder(d,h):
    m=trimesh.creation.cylinder(radius=d/2,height=h,sections=256); m.apply_translation([0,0,h/2]); return m

def make_box(name,w,d,h,x,y,z0=0):
    m=trimesh.creation.box(extents=[w,d,h]); m.apply_translation([x,y,z0+h/2]); m.metadata['name']=name; return m

def make_rect_base(w,d,h): return make_box(f'Base_Rect_{int(w)}x{int(d)}mm',w,d,h,0,0,0)
def parse_size(val, shape='round'):
    if isinstance(val,str):
        s=val.lower().replace('×','x').replace(' ','')
        if 'x' in s:
            a,b=s.split('x',1); return max(float(a),float(b)),float(a),float(b)
        n=float(s)
    else: n=float(val)
    return (n,n,round(n*.75,1)) if shape=='rect' else (n,n,n)

def heart_mesh(line_width,height,y=-31):
    t=np.linspace(0,2*np.pi,320); x=16*np.sin(t)**3; yy=13*np.cos(t)-5*np.cos(2*t)-2*np.cos(3*t)-np.cos(4*t)
    x=(x-x.min())/(x.max()-x.min())*12; yy=(yy-yy.min())/(yy.max()-yy.min())*10; x-= (x.max()+x.min())/2; yy-= (yy.max()+yy.min())/2
    m=extrude_shape(LineString(np.c_[x,yy]).buffer(line_width/2,cap_style=1,join_style=1,resolution=64),height,'Heart'); m.apply_translation([0,y,0]); return m

def preview(path,title,mode,mask=None,note=''):
    img=Image.new('RGB',(1000,1000),(246,243,235))
    d=ImageDraw.Draw(img)

    if mode=='stamp':
        d.ellipse((70,70,930,930),fill=(228,192,120),outline=(130,95,45),width=6)
        text_box=(680,430)
        text_y=285
    else:
        # v0.8.4: real topper preview.
        # No big plaque. Only a narrow letter backing strip and insertion leg(s).
        leg_count = 2 if ('legs 2' in str(note).lower() or 'legs:2' in str(note).lower()) else 1
        strip=(115,360,885,470)
        d.rounded_rectangle(strip,radius=10,fill=(205,205,198),outline=(105,105,100),width=3)

        if leg_count==2:
            leg_xs=[405,595]
        else:
            leg_xs=[500]

        for x in leg_xs:
            d.rounded_rectangle((x-25,458,x+25,860),radius=10,fill=(205,205,198),outline=(105,105,100),width=3)

        text_box=(760,150)
        text_y=335

    if mask is not None:
        mi=Image.fromarray((mask.astype(np.uint8)*255),mode='L')
        bb=mi.getbbox()
        if bb:
            cr=mi.crop(bb)
            cr.thumbnail(text_box,Image.Resampling.LANCZOS)
            col=Image.new('RGB',cr.size,(55,92,205) if mode=='topper' else (105,70,25))
            img.paste(col,((1000-cr.width)//2,text_y),cr)

    d.text((120,70),f'CakeStampBot v0.8.4 — {mode.upper()}',fill=(30,30,30))
    d.text((120,910),note or title[:70],fill=(30,30,30))
    img.save(path)



def make_rounded_box_mesh(
    name: str,
    width: float,
    depth: float,
    height: float,
    center_x: float,
    center_y: float,
    z0: float = 0.0,
    radius: float = 2.2,
):
    """
    Rounded rectangular prism built from a 2D rounded rectangle.
    Used for topper legs/rails so they are not sharp boxy rectangles.
    """
    radius = max(0.1, min(radius, width / 2 - 0.05, depth / 2 - 0.05))
    base = box(
        center_x - width / 2 + radius,
        center_y - depth / 2,
        center_x + width / 2 - radius,
        center_y + depth / 2,
    )
    side = box(
        center_x - width / 2,
        center_y - depth / 2 + radius,
        center_x + width / 2,
        center_y + depth / 2 - radius,
    )
    shape = unary_union([base, side]).buffer(radius, resolution=64, cap_style=1, join_style=1).buffer(0)
    mesh = extrude_shape(shape, height, name)
    mesh.apply_translation([0, 0, z0])
    return mesh


def export_bundle(output,name,scene,preview_png,stls,meta,suffix):
    output=Path(output); project=str(output/f'{name}_{suffix}.3mf'); scene.export(project)
    meta_path=str(output/f'{name}_project.json'); Path(meta_path).write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    bundle=str(output/f'{name}_bundle.zip')
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for p in [project,preview_png,meta_path]+stls:
            if p and os.path.exists(p): z.write(p,arcname=os.path.basename(p))
    return ModelResult(project,preview_png,bundle,str(output))
