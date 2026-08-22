from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine import build_stamp_from_text, build_topper_from_text

def main():
    out=ROOT/'data'/'outputs'/'smoke_test'; out.mkdir(parents=True,exist_ok=True)
    stamp=build_stamp_from_text('С Днём\nРождения!',str(out/'stamp'),base_size='105',base_shape='round',line_width=.45,font_choice='classic',add_heart=False,layout_mode='assembled')
    topper=build_topper_from_text('С Днём Рождения!',str(out/'topper'),width_mm=120,font_choice='classic',text_height=3.0,backing_height=1.2,legs='auto')
    print('Smoke test PASS v1.6.1')
    print('Stamp 3MF:',stamp.project_3mf)
    print('Topper 3MF:',topper.project_3mf)
if __name__=='__main__': main()
