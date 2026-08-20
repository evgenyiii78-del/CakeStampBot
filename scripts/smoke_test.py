from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import generate_text_project


def main():
    out = ROOT / "data" / "outputs" / "smoke_test"
    out.mkdir(parents=True, exist_ok=True)

    result_round = generate_text_project(
        text="С Днём\nРождения\nТанечка!",
        output_dir=str(out / "round"),
        product_mode="stamp",
        base_diameter=105,
        line_width=0.45,
        add_heart=True,
        font_choice="classic",
        base_shape="round",
    )

    result_rect = generate_text_project(
        text="С Днём\nРождения\nТанечка!",
        output_dir=str(out / "rect"),
        product_mode="stamp",
        base_diameter=105,
        line_width=0.45,
        add_heart=True,
        font_choice="classic",
        base_shape="rect",
        layout_mode="assembled",
    )

    print("Smoke test PASS v0.7 v0.6.1")
    print("Round 3MF:", result_round.project_3mf)
    print("Rect 3MF:", result_rect.project_3mf)
    print("Preview:", result_rect.preview_png)
    print("Bundle:", result_rect.bundle_zip)


if __name__ == "__main__":
    main()
