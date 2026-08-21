from pathlib import Path
import logging, trimesh
from .common import *
logger=logging.getLogger('CakeStampEngine.Stamp')
PX=28; RELIEF_H=6.5; BASE_H=.7

def build_stamp_from_text(text, output_dir, base_size='105', base_shape='round', line_width=.45, font_choice='classic', add_heart=False, layout_mode='assembled'):
    mask=render_text_mask(text,82,PX,font_choice); return _build(mask,output_dir,'text_stamp',base_size,base_shape,line_width,add_heart,layout_mode)

def build_stamp_from_image(image_path, output_dir, base_size='105', base_shape='round', line_width=.45, add_heart=False, layout_mode='assembled'):
    mask=render_image_mask(image_path,82,PX); return _build(mask,output_dir,safe_name(Path(image_path).stem,'image_stamp'),base_size,base_shape,line_width,add_heart,layout_mode)

def _build(mask, output_dir, name, base_size, base_shape, line_width, add_heart, layout_mode):
    logger.info('STAMP BUILD START | %s', name); output=Path(output_dir); output.mkdir(parents=True,exist_ok=True)
    nominal, rw, rh=parse_size(base_size,base_shape); shape=mask_to_centerline_shape(mask,PX,line_width); relief=extrude_shape(shape,RELIEF_H,'Relief'); center_and_fit(relief,nominal*.72,nominal*.52,5)
    if base_shape=='rect': base=make_rect_base(rw,rh,BASE_H); base_name=f'Base_Rect_{int(rw)}x{int(rh)}mm'
    else: base=make_cylinder(nominal,BASE_H); base_name=f'Base_Round_{int(nominal)}mm'
    heart=heart_mesh(max(line_width,.45),RELIEF_H,-nominal*.30) if add_heart else None
    stls=[]; base_stl=str(output/f'{name}_{base_name}.stl'); relief_stl=str(output/f'{name}_Relief.stl'); base.export(base_stl); relief.export(relief_stl); stls += [base_stl,relief_stl]
    if heart is not None:
        hp=str(output/f'{name}_Heart.stl'); heart.export(hp); stls.append(hp)
    scene=trimesh.Scene()
    if layout_mode=='separate':
        b=base.copy(); b.apply_translation([-nominal*.90,0,0]); scene.add_geometry(b,geom_name=base_name,node_name=base_name)
        r=relief.copy(); r.apply_translation([nominal*.25,8,0]); scene.add_geometry(r,geom_name='Relief',node_name='Relief')
        if heart is not None:
            h=heart.copy(); h.apply_translation([nominal*.85,0,0]); scene.add_geometry(h,geom_name='Heart',node_name='Heart')
        suffix='stamp_SEPARATE'
    else:
        scene.add_geometry(base.copy(),geom_name=base_name,node_name=base_name); r=relief.copy(); r.apply_translation([0,0,BASE_H]); scene.add_geometry(r,geom_name='Relief',node_name='Relief')
        if heart is not None:
            h=heart.copy(); h.apply_translation([0,0,BASE_H]); scene.add_geometry(h,geom_name='Heart',node_name='Heart')
        suffix='stamp_ASSEMBLED'
    pp=str(output/f'{name}_preview.png'); preview(pp,name,'stamp',mask,note=f'Stamp line {line_width} mm')
    meta={'version':'0.8.0','mode':'stamp','base_shape':base_shape,'base_size':str(base_size),'line_width_mm':line_width,'relief_height_mm':RELIEF_H,'base_thickness_mm':BASE_H,'add_heart':add_heart,'layout_mode':layout_mode,'objects':[base_name,'Relief']+(['Heart'] if add_heart else [])}
    return export_bundle(output,name,scene,pp,stls,meta,suffix)
