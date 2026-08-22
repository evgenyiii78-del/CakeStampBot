
import math
from dataclasses import dataclass
from shapely.geometry import LineString, MultiLineString
from shapely.ops import unary_union
from shapely import affinity

def _arc(cx,cy,rx,ry,a0,a1,n=22):
    return [(cx+rx*math.cos(a0+(a1-a0)*i/(n-1)),cy+ry*math.sin(a0+(a1-a0)*i/(n-1))) for i in range(n)]
def _oval(cx=.5,cy=.48,rx=.36,ry=.38): return _arc(cx,cy,rx,ry,0,2*math.pi,30)

G={}
G["о"]=[_oval()]
G["а"]=[_oval(.44,.46,.30,.34),[(.74,.10),(.74,.80)]]
G["е"]=[_arc(.49,.46,.34,.35,.18*math.pi,1.82*math.pi),[(.17,.46),(.76,.46)]]
G["с"]=[_arc(.50,.46,.34,.35,.25*math.pi,1.75*math.pi)]
G["р"]=[[(.18,-.24),(.18,.80)],_oval(.45,.56,.27,.25)]
G["в"]=[[(.18,.10),(.18,.82)],_arc(.40,.65,.22,.17,-math.pi/2,math.pi/2,14),_arc(.41,.30,.24,.20,-math.pi/2,math.pi/2,14)]
G["н"]=[[(.17,.10),(.17,.82)],[(.76,.10),(.76,.82)],[(.17,.45),(.76,.45)]]
G["т"]=[[(.08,.82),(.86,.82)],[(.47,.82),(.47,.10)]]
G["л"]=[[(.08,.10),(.29,.82),(.52,.82),(.80,.10)]]
G["м"]=[[(.08,.10),(.08,.82),(.45,.27),(.82,.82),(.82,.10)]]
G["и"]=[[(.15,.82),(.15,.10),(.76,.82),(.76,.10)]]
G["й"]=[[(.15,.82),(.15,.10),(.76,.82),(.76,.10)],_arc(.46,.98,.17,.09,math.pi,2*math.pi,10)]
G["ы"]=[[(.13,.82),(.13,.10)],_arc(.34,.30,.21,.19,-math.pi/2,math.pi/2,14),[(.74,.82),(.74,.10)]]
G["д"]=[[(.08,.10),(.24,.10),(.36,.82),(.62,.82),(.80,.10)],[(.03,.10),(.86,.10)],[(.09,.10),(.09,-.06)],[(.81,.10),(.81,-.06)]]
G["ж"]=[[(.07,.82),(.46,.45),(.07,.10)],[(.46,.82),(.46,.10)],[(.85,.82),(.46,.45),(.85,.10)]]
G["ю"]=[[(.12,.82),(.12,.10)],[(.12,.46),(.30,.46)],_oval(.58,.46,.27,.35)]
G["я"]=[_arc(.48,.59,.30,.24,math.pi/2,3*math.pi/2,16),[(.18,.59),(.75,.59)],[(.47,.59),(.18,.10)],[(.47,.59),(.76,.10)]]
G["б"]=[[(.20,.10),(.20,.74),(.70,.91)],_oval(.46,.34,.27,.24)]
G["г"]=[[(.18,.10),(.18,.82),(.75,.82)]]
G["к"]=[[(.16,.10),(.16,.82)],[(.78,.82),(.16,.45),(.80,.10)]]
G["п"]=[[(.16,.10),(.16,.82),(.76,.82),(.76,.10)]]
G["у"]=[[(.08,.82),(.42,.23)],[(.79,.82),(.40,.00),(.27,-.19)]]
G["з"]=[_arc(.37,.64,.28,.18,-math.pi/2,math.pi/2,14),_arc(.37,.29,.31,.21,-math.pi/2,math.pi/2,14)]
G["ч"]=[[(.13,.82),(.13,.52),(.70,.44),(.70,.82),(.70,.10)]]
G["ш"]=[[(.11,.82),(.11,.10),(.43,.10),(.43,.82)],[(.43,.10),(.76,.10),(.76,.82)]]
G["щ"]=[[(.09,.82),(.09,.10),(.38,.10),(.38,.82)],[(.38,.10),(.67,.10),(.67,.82)],[(.67,.10),(.81,-.07)]]
G["х"]=[[(.10,.82),(.78,.10)],[(.78,.82),(.10,.10)]]
G["ф"]=[[(.45,.96),(.45,-.10)],_oval(.45,.47,.36,.23)]
G["ц"]=[[(.13,.82),(.13,.10),(.67,.10),(.67,.82)],[(.67,.10),(.81,-.07)]]
G["э"]=[_arc(.47,.46,.34,.35,-.75*math.pi,.75*math.pi),[(.23,.46),(.75,.46)]]
G["ь"]=[[(.17,.82),(.17,.10)],_arc(.39,.29,.23,.19,-math.pi/2,math.pi/2,14)]
G["ъ"]=[[(.05,.82),(.28,.82),(.28,.10)],_arc(.50,.29,.23,.19,-math.pi/2,math.pi/2,14)]
G["ё"]=G["е"]+[[(.34,.98),(.345,.985)],[(.60,.98),(.605,.985)]]
G["К"]=[[(.13,.04),(.13,.96)],[(.82,.96),(.13,.48),(.84,.04)]]
for lo in list(G):
    up=lo.upper()
    if up!=lo and up not in G: G[up]=G[lo]

@dataclass
class StrokeTextResult:
    geometry: object
    width_mm: float
    height_mm: float

def supports(text):
    return all(ch in G or ch.isspace() or ch in "-–—" for ch in str(text or ""))

def _glyph(ch):
    paths=G.get(ch)
    if not paths:return None
    ls=[LineString(p) for p in paths if len(p)>=2]
    return ls[0] if len(ls)==1 else MultiLineString(ls)

ADVANCE={"ж":1.18,"м":1.10,"ш":1.10,"щ":1.16,"ю":1.08,"и":.92,"н":.92,"п":.92,"л":.94,"к":.92,"т":.88,"о":.90,"с":.86,"е":.86,"р":.88,"в":.86,"а":.86,"б":.88,"я":.90,"ы":.98,"ь":.80,"ъ":.88,"й":.92,"у":.88,"ч":.86,"з":.82,"х":.86,"ф":1.0,"ц":.92,"э":.86,"д":.98}
for _k,_v in list(ADVANCE.items()): ADVANCE[_k.upper()]=_v
def _advance(ch): return .43 if ch.isspace() else ADVANCE.get(ch,.90)

def _style_glyph(g, style, glyph_index=0):
    style=(style or "classic").lower()
    if style=="comic":
        g=affinity.skew(g,xs=10.0,ys=0.0,origin=(0,0))
        g=affinity.scale(g,xfact=1.08,yfact=.94,origin=(0,0))
        g=affinity.rotate(g,(-1.8 if glyph_index%2==0 else 1.2),origin="center")
        return g
    if style=="gost":
        return affinity.scale(g,xfact=.82,yfact=1.08,origin=(0,0))
    return g

STYLE_METRICS={
 "classic":{"tracking":.075,"line_spacing":1.04,"width_factor":.90},
 "comic":{"tracking":.035,"line_spacing":1.00,"width_factor":.96},
 "gost":{"tracking":.105,"line_spacing":1.07,"width_factor":.82},
}

def text_to_single_lines(text,target_width_mm,target_height_mm,line_spacing=None,tracking=None,font_choice="classic"):
    style=(font_choice or "classic").lower()
    if style not in STYLE_METRICS: style="classic"
    m=STYLE_METRICS[style]
    if line_spacing is None: line_spacing=m["line_spacing"]
    if tracking is None: tracking=m["tracking"]
    lines=str(text or "").splitlines() or [""]
    geoms=[]; y=0.0; glyph_index=0
    for line in lines:
        widths=[_advance(c) for c in line]
        if style=="comic": widths=[w*1.04 for w in widths]
        elif style=="gost": widths=[w*.88 for w in widths]
        total=sum(widths)+tracking*max(0,len(widths)-1); x=-total/2.0
        for c,w in zip(line,widths):
            if not c.isspace():
                g=_glyph(c)
                if g is not None:
                    g=_style_glyph(g,style,glyph_index)
                    x0,y0,x1,y1=g.bounds; gw=max(x1-x0,1e-6)
                    gs=min(1.0,(w*m["width_factor"])/gw)
                    g=affinity.scale(g,xfact=gs,yfact=1.0,origin=(0,0))
                    x0,y0,x1,y1=g.bounds
                    g=affinity.translate(g,xoff=x+(w-(x1-x0))/2-x0,yoff=-y)
                    geoms.append(g); glyph_index+=1
            x+=w+tracking
        y+=1.18*line_spacing
    if not geoms: raise ValueError("No supported glyph geometry")
    geom=unary_union(geoms); x0,y0,x1,y1=geom.bounds
    scale=min(target_width_mm/max(x1-x0,1e-6),target_height_mm/max(y1-y0,1e-6))
    geom=affinity.scale(geom,xfact=scale,yfact=scale,origin=(0,0))
    x0,y0,x1,y1=geom.bounds
    geom=affinity.translate(geom,xoff=-(x0+x1)/2,yoff=-(y0+y1)/2)
    x0,y0,x1,y1=geom.bounds
    return StrokeTextResult(geom,x1-x0,y1-y0)
