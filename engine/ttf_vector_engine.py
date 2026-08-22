from dataclasses import dataclass
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from shapely.geometry import Polygon, GeometryCollection
from shapely.ops import unary_union
from shapely import affinity

@dataclass
class TTFTextResult:
    geometry: object
    width_mm: float
    height_mm: float
    font_path: str
    line_spacing: float

class FlattenPen(BasePen):
    def __init__(self,gs,steps=22):
        super().__init__(gs); self.steps=steps; self.cs=[]; self.cur=[]; self.last=None
    def _moveTo(self,p): self._finish(); self.cur=[tuple(p)]; self.last=tuple(p)
    def _lineTo(self,p): self.cur.append(tuple(p)); self.last=tuple(p)
    def _qCurveToOne(self,p1,p2):
        p0=self.last
        for i in range(1,self.steps+1):
            t=i/self.steps; u=1-t
            self.cur.append((u*u*p0[0]+2*u*t*p1[0]+t*t*p2[0],u*u*p0[1]+2*u*t*p1[1]+t*t*p2[1]))
        self.last=tuple(p2)
    def _curveToOne(self,p1,p2,p3):
        p0=self.last
        for i in range(1,self.steps+1):
            t=i/self.steps;u=1-t
            self.cur.append((u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0],u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1]))
        self.last=tuple(p3)
    def _closePath(self): self._finish()
    def _endPath(self): self._finish()
    def _finish(self):
        if len(self.cur)>=3:
            if self.cur[0]!=self.cur[-1]:self.cur.append(self.cur[0])
            self.cs.append(self.cur)
        self.cur=[];self.last=None

def resolve_font(choice,folder):
    fs=list(Path(folder).glob("*.ttf"))+list(Path(folder).glob("*.otf"))
    if not fs: raise FileNotFoundError("fonts directory contains no TTF/OTF")
    d={p.name.lower():p for p in fs}; c=(choice or "classic").lower()
    prefs={"classic":["dejavuserif.ttf","dejavusans.ttf"],"comic":["comic.ttf","comic_sans.ttf","comicsans.ttf","comic sans ms.ttf","dejavusans.ttf"],"gost":["gost-type-au.ttf","gost.ttf","dejavusans.ttf"]}
    for n in prefs.get(c,prefs["classic"]):
        if n in d:return d[n]
    token={"comic":"comic","gost":"gost","classic":"serif"}.get(c,"")
    for p in fs:
        if token and token in p.name.lower():return p
    return fs[0]

def glyph_geom(gs,name,steps):
    pen=FlattenPen(gs,steps);gs[name].draw(pen);pen._finish()
    polys=[]
    for pts in pen.cs:
        try:
            p=Polygon(pts)
            if not p.is_valid:p=p.buffer(0)
            if not p.is_empty:polys.append(p)
        except:pass
    if not polys:return GeometryCollection()
    g=polys[0]
    for p in polys[1:]:g=g.symmetric_difference(p)
    return g.buffer(0) if not g.is_valid else g

def text_to_ttf_geometry(text,fonts_dir,font_choice,target_width_mm,target_height_mm,line_spacing=.90,curve_steps=22):
    fp=resolve_font(font_choice,fonts_dir);font=TTFont(str(fp));gs=font.getGlyphSet();cm=font.getBestCmap() or {};hm=font["hmtx"].metrics
    hh=font["hhea"]; step=max(1,float(hh.ascent-hh.descent))*line_spacing
    rows=[];y=0.
    for line in str(text or "").splitlines() or [""]:
        parts=[];x=0.
        for ch in line:
            gn=cm.get(ord(ch)) or cm.get(ord("?"))
            if gn is None:continue
            adv=hm.get(gn,(font["head"].unitsPerEm*.6,0))[0]
            if not ch.isspace():
                g=glyph_geom(gs,gn,curve_steps)
                if not g.is_empty:parts.append(affinity.translate(g,xoff=x,yoff=-y))
            x+=adv
        if parts:
            g=unary_union(parts);a,b,c,d=g.bounds
            rows.append(affinity.translate(g,xoff=-(a+c)/2))
        y+=step
    font.close()
    if not rows:raise ValueError("no TTF glyph geometry")
    g=unary_union(rows);a,b,c,d=g.bounds
    s=min(target_width_mm/max(c-a,1e-6),target_height_mm/max(d-b,1e-6))
    g=affinity.scale(g,xfact=s,yfact=s,origin=(0,0));a,b,c,d=g.bounds
    g=affinity.translate(g,xoff=-(a+c)/2,yoff=-(b+d)/2);a,b,c,d=g.bounds
    return TTFTextResult(g,c-a,d-b,str(fp),line_spacing)
