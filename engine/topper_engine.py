from pathlib import Path
import logging, trimesh
from .common import *
logger=logging.getLogger('CakeStampEngine.Topper')
PX=28; DEFAULT_LINE_WIDTH=.85; LEG_H=45; LEG_W=7

def build_topper_from_text(text, output_dir, width_mm=120, font_choice='classic', text_height=3.0, backing_height=1.2, line_width=DEFAULT_LINE_WIDTH, legs='auto'):
    logger.info('TOPPER BUILD START | width=%s legs=%s', width_mm, legs); output=Path(output_dir); output.mkdir(parents=True,exist_ok=True)
    mask=render_text_mask(text,100,PX,font_choice); shape=mask_to_centerline_shape(mask,PX,line_width,.28); text_mesh=extrude_shape(shape,text_height,'Topper_Text'); center_and_fit(text_mesh,width_mm*.90,width_mm*.38,10)
    b=text_mesh.bounds; minx,miny,maxx,maxy=b[0,0],b[0,1],b[1,0],b[1,1]; tw=maxx-minx; th=maxy-miny
    backing_w=min(width_mm*.96,tw+12); backing_d=max(9,min(20,th*.24)); backing_y=miny+backing_d*.38
    backing=make_box('Topper_Letter_Backing',backing_w,backing_d,backing_height,0,backing_y,0)
    leg_count=1 if legs=='one' else 2 if legs=='two' else (2 if width_mm>=120 else 1)
    leg_y=miny-LEG_H/2+1.5; spread=min(width_mm*.32,max(34,backing_w*.30)); xs=[0] if leg_count==1 else [-spread/2,spread/2]
    leg_meshes=[make_box(f'Topper_Leg_{i+1}',LEG_W,LEG_H,max(backing_height,text_height*.75),x,leg_y,0) for i,x in enumerate(xs)]
    stls=[]; tp=str(output/'topper_Text.stl'); bp=str(output/'topper_Backing.stl'); text_mesh.export(tp); backing.export(bp); stls += [tp,bp]
    for i,leg in enumerate(leg_meshes,1):
        p=str(output/f'topper_Leg_{i}.stl'); leg.export(p); stls.append(p)
    scene=trimesh.Scene(); scene.add_geometry(backing.copy(),geom_name='Topper_Letter_Backing',node_name='Topper_Letter_Backing')
    for i,leg in enumerate(leg_meshes,1): scene.add_geometry(leg.copy(),geom_name=f'Topper_Leg_{i}',node_name=f'Topper_Leg_{i}')
    txt=text_mesh.copy(); txt.apply_translation([0,0,backing_height]); scene.add_geometry(txt,geom_name='Topper_Text',node_name='Topper_Text')
    pp=str(output/'topper_preview.png'); preview(pp,'topper','topper',mask,note=f'Topper text {text_height} mm, backing {backing_height} mm, legs {leg_count}')
    meta={'version':'0.8.0','mode':'topper','width_mm':width_mm,'text_height_mm':text_height,'backing_height_mm':backing_height,'line_width_mm':line_width,'legs':leg_count,'objects':['Topper_Letter_Backing','Topper_Text']+[f'Topper_Leg_{i}' for i in range(1,leg_count+1)]}
    return export_bundle(output,'topper',scene,pp,stls,meta,'topper_ASSEMBLED')
