import os
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

import trimesh
from skimage.morphology import skeletonize, remove_small_objects
from skimage.filters import threshold_otsu
from scipy.ndimage import binary_erosion, binary_dilation

from shapely.geometry import LineString, Polygon, MultiPolygon
from shapely.ops import unary_union, triangulate


class ProductMode(str, Enum):
    STAMP = "stamp"
    TOPPER = "topper"
    CUTTER = "cutter"


class FontChoice(str, Enum):
    CLASSIC = "classic"
    COMIC = "comic"
    GOST = "gost"


@dataclass
class StampResult:
    project_3mf: str
    preview_png: str
    bundle_zip: str
    output_dir: str


DEFAULTS = {
    "base_thickness": 0.7,
    "stamp_relief_height": 6.5,
    "topper_height": 2.2,
    "cutter_height": 12.0,
    "px_per_mm": 18,
}


def _env_path(name: str) -> str | None:
    value = os.getenv(name, "").strip().strip('"')
    if value and os.path.exists(value):
        return value
    return None


def _first_existing(paths: list[str]) -> str | None:
    for path in paths:
        if path and os.path.exists(path):
            return path
    return None



def _find_font_path(font_choice: str = "classic") -> str:
    """
    Find a usable TTF font. Works on Windows, Linux Docker and common hosting images.

    Priority:
    1. Explicit .env variable:
       CAKESTAMP_FONT_CLASSIC / CAKESTAMP_FONT_COMIC / CAKESTAMP_FONT_GOST
    2. Common Windows/Linux font locations
    3. Recursive scan of /usr/share/fonts, /usr/local/share/fonts, /app/fonts
    """
    choice = (font_choice or "classic").lower()

    env_map = {
        "classic": "CAKESTAMP_FONT_CLASSIC",
        "comic": "CAKESTAMP_FONT_COMIC",
        "gost": "CAKESTAMP_FONT_GOST",
    }

    env_name = env_map.get(choice, "CAKESTAMP_FONT_CLASSIC")
    env_font = os.getenv(env_name) or os.getenv("CAKESTAMP_FONT")
    if env_font and os.path.exists(env_font):
        return env_font

    candidates_by_choice = {
        "classic": [
            # Linux / Docker
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSerif-Italic.ttf",
            "/usr/share/fonts/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            # Windows
            r"C:\Windows\Fonts\timesi.ttf",
            r"C:\Windows\Fonts\times.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\ariali.ttf",
        ],
        "comic": [
            r"C:\Windows\Fonts\comic.ttf",
            r"C:\Windows\Fonts\comicbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        ],
        "gost": [
            r"C:\Windows\Fonts\GOST type AU.ttf",
            r"C:\Windows\Fonts\gost type au.ttf",
            "/app/fonts/GOST-type-AU.ttf",
            "/app/fonts/GOST type AU.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        ],
    }

    candidates = candidates_by_choice.get(choice, []) + candidates_by_choice["classic"]

    for path in candidates:
        if path and os.path.exists(path):
            return path

    # Recursive fallback scan. Prefer DejaVu because it supports Cyrillic.
    search_dirs = [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        "/app/fonts",
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/.local/share/fonts"),
    ]

    preferred_keywords = ["dejavuserif", "dejavusans", "liberationserif", "liberationsans", "arial"]
    found = []

    for base in search_dirs:
        if not base or not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if fn.lower().endswith((".ttf", ".otf")):
                    full = os.path.join(root, fn)
                    found.append(full)
                    low = fn.lower().replace(" ", "")
                    if any(key in low for key in preferred_keywords):
                        return full

    if found:
        return found[0]

    raise FileNotFoundError(
        "Не найден TTF-шрифт в контейнере. "
        "Для Docker добавьте fonts-dejavu-core или укажите путь в .env: "
        "CAKESTAMP_FONT_CLASSIC=/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    )



def _safe_name(value: str, default: str = "project") -> str:
    good = []
    for ch in value:
        if ch.isalnum() or ch in ("_", "-"):
            good.append(ch)
        elif ch.isspace():
            good.append("_")
    name = "".join(good).strip("_")
    return name[:40] or default




def _parse_base_size(base_diameter, base_shape: str = "round"):
    """
    base_diameter can be:
    - number: 105
    - string preset: "105"
    - rectangle string: "105x75"
    Returns: (nominal_size, rect_width, rect_height)
    """
    if isinstance(base_diameter, str):
        value = base_diameter.lower().replace("×", "x").replace(" ", "")
        if "x" in value:
            a, b = value.split("x", 1)
            w = float(a)
            h = float(b)
            return max(w, h), w, h
        nominal = float(value)
    else:
        nominal = float(base_diameter)

    if base_shape == "rect":
        return nominal, nominal, round(nominal * 0.75, 1)

    return nominal, nominal, nominal


def _make_cylinder_base(diameter: float, height: float) -> trimesh.Trimesh:
    mesh = trimesh.creation.cylinder(
        radius=diameter / 2,
        height=height,
        sections=256,
    )
    mesh.apply_translation([0, 0, height / 2])
    mesh.metadata["name"] = f"Base_{int(diameter)}mm_round_{height}mm"
    return mesh


def _make_rect_base(width: float, height_xy: float, thickness: float) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=[width, height_xy, thickness])
    mesh.apply_translation([0, 0, thickness / 2])
    mesh.metadata["name"] = f"Base_{int(width)}x{int(height_xy)}mm_rect_{thickness}mm"
    return mesh



def _render_text_mask(
    text: str,
    canvas_mm: float,
    px_per_mm: int,
    font_choice: str,
) -> np.ndarray:
    margin_px = 80
    img_size = int(canvas_mm * px_per_mm) + 2 * margin_px

    img = Image.new("L", (img_size, img_size), 0)
    draw = ImageDraw.Draw(img)
    lines = text.split("\n")
    font_path = _find_font_path(font_choice)

    font_size = int(img_size * 0.18)
    while font_size > 20:
        font = ImageFont.truetype(font_path, font_size)
        bbs = [draw.textbbox((0, 0), line, font=font) for line in lines]
        widths = [bb[2] - bb[0] for bb in bbs]
        heights = [bb[3] - bb[1] for bb in bbs]
        gap = int(font_size * 0.17)
        total_h = sum(heights) + gap * (len(lines) - 1)
        max_w = max(widths)

        if max_w < img_size * 0.80 and total_h < img_size * 0.66:
            break
        font_size -= 3

    font = ImageFont.truetype(font_path, font_size)
    bbs = [draw.textbbox((0, 0), line, font=font) for line in lines]
    heights = [bb[3] - bb[1] for bb in bbs]
    gap = int(font_size * 0.17)
    total_h = sum(heights) + gap * (len(lines) - 1)
    y = (img_size - total_h) // 2 - 20

    for line, bb, h in zip(lines, bbs, heights):
        w = bb[2] - bb[0]
        x = (img_size - w) // 2
        draw.text((x, y - bb[1]), line, fill=255, font=font)
        y += h + gap

    return np.array(img) > 40


def _render_image_mask(
    image_path: str,
    canvas_mm: float,
    px_per_mm: int,
) -> np.ndarray:
    margin_px = 80
    img_size = int(canvas_mm * px_per_mm) + 2 * margin_px

    src = Image.open(image_path).convert("L")
    src = ImageOps.autocontrast(src)
    src.thumbnail((img_size - 2 * margin_px, img_size - 2 * margin_px))

    img = Image.new("L", (img_size, img_size), 255)
    x = (img_size - src.width) // 2
    y = (img_size - src.height) // 2
    img.paste(src, (x, y))
    img = img.filter(ImageFilter.GaussianBlur(radius=0.6))

    arr = np.array(img)
    try:
        th = threshold_otsu(arr)
    except Exception:
        th = 180

    mask = arr < th
    if mask.mean() > 0.45:
        mask = arr > th

    mask = remove_small_objects(mask.astype(bool), min_size=20)
    return mask


NEIGHBORS = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]


def _skeleton_to_polylines(skel: np.ndarray):
    coords = set(map(tuple, np.argwhere(skel)))

    def neighs(p):
        y, x = p
        out = []
        for dy, dx in NEIGHBORS:
            q = (y + dy, x + dx)
            if q in coords:
                out.append(q)
        return out

    def edge_key(a, b):
        return tuple(sorted([a, b]))

    degree = {p: len(neighs(p)) for p in coords}
    nodes = {p for p, deg in degree.items() if deg != 2}
    visited = set()
    lines = []

    for start in list(nodes):
        for nb in neighs(start):
            ek = edge_key(start, nb)
            if ek in visited:
                continue

            path = [start, nb]
            visited.add(ek)
            prev, cur = start, nb

            while cur not in nodes:
                ns = [q for q in neighs(cur) if q != prev]
                if not ns:
                    break
                nxt = ns[0]
                ek = edge_key(cur, nxt)
                if ek in visited:
                    break
                visited.add(ek)
                path.append(nxt)
                prev, cur = cur, nxt

            if len(path) >= 2:
                lines.append(path)

    all_edges = []
    for p in coords:
        for q in neighs(p):
            if p < q:
                all_edges.append((p, q))

    for a, b in all_edges:
        if edge_key(a, b) in visited:
            continue

        path = [a, b]
        visited.add(edge_key(a, b))
        prev, cur = a, b

        while True:
            ns = [
                q for q in neighs(cur)
                if q != prev and edge_key(cur, q) not in visited
            ]
            if not ns:
                break
            nxt = ns[0]
            visited.add(edge_key(cur, nxt))
            path.append(nxt)
            prev, cur = cur, nxt
            if cur == a:
                break

        if len(path) >= 3:
            lines.append(path)

    return lines




def _chaikin_smooth(points, refinements: int = 2):
    """
    Smooth a polyline using Chaikin corner cutting.
    Keeps endpoints for open lines.
    """
    if len(points) < 3:
        return points

    pts = [tuple(map(float, pt)) for pt in points]
    for _ in range(max(0, refinements)):
        if len(pts) < 3:
            break
        new_pts = [pts[0]]
        for i in range(len(pts) - 1):
            p0 = np.array(pts[i], dtype=float)
            p1 = np.array(pts[i + 1], dtype=float)
            q = 0.75 * p0 + 0.25 * p1
            r = 0.25 * p0 + 0.75 * p1
            new_pts.append(tuple(q))
            new_pts.append(tuple(r))
        new_pts.append(pts[-1])
        pts = new_pts
    return pts


def _polylines_to_shape(
    lines,
    mask_shape,
    px_per_mm: int,
    line_width: float,
    smooth: float = 0.22,
):
    h, w = mask_shape
    mm_per_px = 1 / px_per_mm
    geoms = []

    for path in lines:
        pts = []
        for y, x in path:
            X = x * mm_per_px
            Y = (h - y) * mm_per_px
            pts.append((X, Y))

        if len(pts) < 2:
            continue

        # First pass: remove the pixel staircase by corner-cut smoothing.
        pts = _chaikin_smooth(pts, refinements=2)

        line = LineString(pts)
        if line.length < 0.65:
            continue

        # Second pass: simplify tiny jitters while preserving overall letter shape.
        line = line.simplify(smooth, preserve_topology=False)
        if line.length < 0.65:
            continue

        # Final vector stroke with a higher circular resolution for smoother arcs.
        geoms.append(
            line.buffer(
                line_width / 2,
                cap_style=1,
                join_style=1,
                resolution=16,
            )
        )

    if not geoms:
        return None

    merged = unary_union(geoms).buffer(0)

    # Small outward/inward micro-buffer pair rounds rough joints a little more
    # without noticeably changing the requested line width.
    eps = max(0.01, line_width * 0.08)
    merged = merged.buffer(eps, resolution=16).buffer(-eps, resolution=16).buffer(0)
    return merged


def _mask_to_centerline_shape(mask: np.ndarray, px_per_mm: int, line_width: float):
    skel = skeletonize(mask)
    lines = _skeleton_to_polylines(skel)
    return _polylines_to_shape(lines, mask.shape, px_per_mm, line_width, smooth=0.22)


def _mask_to_boundary_shape(mask: np.ndarray, px_per_mm: int, line_width: float):
    # For cutter: take silhouette boundary, skeletonize it, and buffer into a wall.
    eroded = binary_erosion(mask)
    boundary = mask ^ eroded
    boundary = binary_dilation(boundary, iterations=1)
    skel = skeletonize(boundary)
    lines = _skeleton_to_polylines(skel)
    return _polylines_to_shape(lines, mask.shape, px_per_mm, line_width, smooth=0.18)


def _extrude_polygon_custom(poly: Polygon, height: float, z0: float = 0.0):
    if poly.is_empty or poly.area <= 0:
        return None

    vertices = []
    faces = []
    vmap = {}

    def add_v(x, y, z):
        key = (round(float(x), 5), round(float(y), 5), round(float(z), 5))
        if key not in vmap:
            vmap[key] = len(vertices)
            vertices.append((float(x), float(y), float(z)))
        return vmap[key]

    def add_quad(a, b, c, d):
        faces.append([a, b, c])
        faces.append([a, c, d])

    def add_side_ring(coords):
        for i in range(len(coords) - 1):
            x1, y1 = coords[i]
            x2, y2 = coords[i + 1]
            a = add_v(x1, y1, z0)
            b = add_v(x2, y2, z0)
            c = add_v(x2, y2, z0 + height)
            d = add_v(x1, y1, z0 + height)
            add_quad(a, b, c, d)

    for tri in triangulate(poly):
        rp = tri.representative_point()
        if not poly.contains(rp) and not poly.touches(rp):
            continue

        coords = list(tri.exterior.coords)[:3]
        top = [add_v(x, y, z0 + height) for x, y in coords]
        bot = [add_v(x, y, z0) for x, y in coords]
        faces.append(top)
        faces.append(bot[::-1])

    add_side_ring(list(poly.exterior.coords))

    for interior in poly.interiors:
        add_side_ring(list(interior.coords))

    if not vertices or not faces:
        return None

    return trimesh.Trimesh(
        vertices=np.asarray(vertices),
        faces=np.asarray(faces),
        process=True,
    )


def _extrude_shape(shape, height: float, name: str) -> trimesh.Trimesh:
    if shape is None:
        raise RuntimeError("Пустая геометрия после обработки.")

    if isinstance(shape, Polygon):
        polys = [shape]
    elif isinstance(shape, MultiPolygon):
        polys = list(shape.geoms)
    else:
        polys = list(getattr(shape, "geoms", []))

    meshes = []
    for p in polys:
        if p.area < 0.02:
            continue
        m = _extrude_polygon_custom(p.buffer(0), height)
        if m is not None and len(m.faces) > 0:
            meshes.append(m)

    if not meshes:
        raise RuntimeError(f"Не удалось построить mesh: {name}")

    mesh = trimesh.util.concatenate(meshes)
    mesh.metadata["name"] = name
    return mesh


def _center_and_fit(
    mesh: trimesh.Trimesh,
    max_w: float,
    max_h: float,
    y_shift: float = 0.0,
) -> trimesh.Trimesh:
    bounds = mesh.bounds
    w = max(bounds[1, 0] - bounds[0, 0], 0.001)
    h = max(bounds[1, 1] - bounds[0, 1], 0.001)
    scale = min(max_w / w, max_h / h, 1.0)
    mesh.apply_scale([scale, scale, 1.0])

    bounds = mesh.bounds
    cx = (bounds[0, 0] + bounds[1, 0]) / 2
    cy = (bounds[0, 1] + bounds[1, 1]) / 2
    mesh.apply_translation([-cx, -cy + y_shift, 0])
    return mesh


def _make_heart_mesh(
    line_width: float,
    height: float,
    y: float = -31.0,
) -> trimesh.Trimesh:
    t = np.linspace(0, 2 * np.pi, 260)
    x = 16 * np.sin(t) ** 3
    yy = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)

    x = (x - x.min()) / (x.max() - x.min()) * 12.0
    yy = (yy - yy.min()) / (yy.max() - yy.min()) * 10.0
    x -= (x.max() + x.min()) / 2
    yy -= (yy.max() + yy.min()) / 2

    line = LineString(np.column_stack([x, yy]))
    shape = line.buffer(
        line_width / 2,
        cap_style=1,
        join_style=1,
        resolution=8,
    )

    mesh = _extrude_shape(shape, height, "Heart")
    mesh.apply_translation([0, y, 0])
    return mesh


def _make_preview_png(
    output_path: str,
    base_diameter: float,
    relief_mask: np.ndarray | None,
    title: str,
    product_mode: str,
    line_width: float,
    add_heart: bool,
):
    img = Image.new("RGB", (1000, 1000), (246, 243, 235))
    d = ImageDraw.Draw(img)

    # Background card
    d.rounded_rectangle((60, 50, 940, 950), radius=28, fill=(255, 252, 245), outline=(190, 160, 110), width=3)

    if product_mode == ProductMode.STAMP.value:
        cx, cy, r = 500, 480, 370
        d.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            fill=(228, 192, 120),
            outline=(130, 95, 45),
            width=6,
        )
    else:
        d.rounded_rectangle((150, 150, 850, 800), radius=24, fill=(235, 210, 160), outline=(130, 95, 45), width=5)

    if relief_mask is not None:
        mask_img = Image.fromarray((relief_mask.astype(np.uint8) * 255), mode="L")
        bbox = mask_img.getbbox()
        if bbox:
            crop = mask_img.crop(bbox)
            crop.thumbnail((650, 440), Image.Resampling.LANCZOS)
            gold = Image.new("RGB", crop.size, (105, 70, 25))
            img.paste(gold, ((1000 - crop.width) // 2, 250), crop)

    d.text((100, 88), "CakeStampBot v0.7.1", fill=(50, 35, 20))
    d.text((100, 840), f"Режим: {product_mode}   Линия: {line_width} мм   Сердце: {'да' if add_heart else 'нет'}", fill=(50, 35, 20))
    d.text((100, 885), title[:70], fill=(50, 35, 20))

    img.save(output_path)


def _build_from_mask(
    mask: np.ndarray,
    output_dir: str,
    name: str,
    product_mode: str,
    base_diameter: float,
    line_width: float,
    add_heart: bool,
    font_choice: str = "classic",
    base_shape: str = "round",
    layout_mode: str = "separate",
) -> StampResult:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    base_size_nominal, rect_w, rect_h = _parse_base_size(base_diameter, base_shape)
    base_diameter = float(base_size_nominal)

    product_mode = ProductMode(product_mode).value
    base_shape = "rect" if str(base_shape).lower() in ("rect", "rectangle", "прямоугольная") else "round"

    base_thickness = DEFAULTS["base_thickness"]
    px_per_mm = DEFAULTS["px_per_mm"]

    if product_mode == ProductMode.CUTTER.value:
        actual_line_width = max(float(line_width), 0.80)
        height = DEFAULTS["cutter_height"]
        shape = _mask_to_boundary_shape(mask, px_per_mm, actual_line_width)
        object_name = "Cutter_Wall"
    elif product_mode == ProductMode.TOPPER.value:
        actual_line_width = max(float(line_width), 0.50)
        height = DEFAULTS["topper_height"]
        shape = _mask_to_centerline_shape(mask, px_per_mm, actual_line_width)
        object_name = "Topper"
    else:
        actual_line_width = float(line_width)
        height = DEFAULTS["stamp_relief_height"]
        shape = _mask_to_centerline_shape(mask, px_per_mm, actual_line_width)
        object_name = "Relief"

    model = _extrude_shape(
        shape,
        height,
        f"{object_name}_{name}",
    )

    if product_mode == ProductMode.STAMP.value:
        _center_and_fit(
            model,
            max_w=base_diameter * 0.72,
            max_h=base_diameter * 0.52,
            y_shift=5,
        )
    else:
        _center_and_fit(
            model,
            max_w=base_diameter * 0.80,
            max_h=base_diameter * 0.58,
            y_shift=0,
        )

    base = None
    if product_mode == ProductMode.STAMP.value:
        if base_shape == "rect":
            base = _make_rect_base(
                width=rect_w,
                height_xy=rect_h,
                thickness=base_thickness,
            )
        else:
            base = _make_cylinder_base(
                diameter=base_diameter,
                height=base_thickness,
            )

    heart = None
    if add_heart and product_mode in (ProductMode.STAMP.value, ProductMode.TOPPER.value):
        heart = _make_heart_mesh(
            line_width=max(actual_line_width, 0.45),
            height=height,
            y=-base_diameter * 0.30,
        )

    # Export STLs.
    project_stls = []
    if base is not None:
        shape_label = "rect" if base_shape == "rect" else "round"
        base_stl = str(output / f"{name}_Base_{shape_label}_{int(base_diameter)}mm.stl")
        base.export(base_stl)
        project_stls.append(base_stl)

    model_stl = str(output / f"{name}_{object_name}.stl")
    model.export(model_stl)
    project_stls.append(model_stl)

    if heart is not None:
        heart_stl = str(output / f"{name}_Heart.stl")
        heart.export(heart_stl)
        project_stls.append(heart_stl)

    # 3MF layout.
    scene = trimesh.Scene()

    if layout_mode == "assembled" and base is not None:
        base_node_name = (
            f"Base_Rect_{int(rect_w)}x{int(rect_h)}mm"
            if base_shape == "rect"
            else f"Base_Round_{int(base_diameter)}mm"
        )
        scene.add_geometry(
            base.copy(),
            geom_name=base_node_name,
            node_name=base_node_name,
        )

        m = model.copy()
        m.apply_translation([0, 0, base_thickness])
        scene.add_geometry(
            m,
            geom_name=object_name,
            node_name=object_name,
        )

        if heart is not None:
            h = heart.copy()
            h.apply_translation([0, 0, base_thickness])
            scene.add_geometry(
                h,
                geom_name="Heart",
                node_name="Heart",
            )

        project_3mf = str(output / f"{name}_{product_mode}_project_ASSEMBLED.3mf")
    else:
        if base is not None:
            b = base.copy()
            b.apply_translation([-base_diameter * 0.90, 0, 0])
            base_node_name = (
                f"Base_Rect_{int(rect_w)}x{int(rect_h)}mm"
                if base_shape == "rect"
                else f"Base_Round_{int(base_diameter)}mm"
            )
            scene.add_geometry(
                b,
                geom_name=base_node_name,
                node_name=base_node_name,
            )

            m = model.copy()
            m.apply_translation([base_diameter * 0.25, 8, 0])
        else:
            m = model.copy()
            m.apply_translation([0, 0, 0])

        scene.add_geometry(
            m,
            geom_name=object_name,
            node_name=object_name,
        )

        if heart is not None:
            h = heart.copy()
            h.apply_translation([base_diameter * 0.85, 0, 0])
            scene.add_geometry(
                h,
                geom_name="Heart",
                node_name="Heart",
            )

        project_3mf = str(output / f"{name}_{product_mode}_project_SEPARATE.3mf")

    scene.export(project_3mf)

    preview_png = str(output / f"{name}_{product_mode}_preview.png")
    _make_preview_png(
        output_path=preview_png,
        base_diameter=base_diameter,
        relief_mask=mask,
        title=name,
        product_mode=product_mode,
        line_width=actual_line_width,
        add_heart=bool(heart is not None),
    )

    meta = {
        "name": name,
        "product_mode": product_mode,
        "base_diameter_mm": base_diameter,
        "base_shape": base_shape if base is not None else None,
        "base_rect_width_mm": rect_w if base_shape == "rect" and base is not None else None,
        "base_rect_height_mm": rect_h if base_shape == "rect" and base is not None else None,
        "layout_mode": layout_mode,
        "base_rect_size_mm": [base_diameter, rect_h] if base_shape == "rect" and base is not None else None,
        "base_thickness_mm": base_thickness if base is not None else None,
        "height_mm": height,
        "line_width_mm": actual_line_width,
        "font_choice": font_choice,
        "objects": (
            (["Base"] if base is not None else [])
            + [object_name]
            + (["Heart"] if heart is not None else [])
        ),
        "note": "3MF содержит отдельные объекты. Можно двигать и масштабировать в слайсере.",
    }
    meta_path = str(output / f"{name}_{product_mode}_project.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    bundle_zip = str(output / f"{name}_{product_mode}_bundle.zip")
    with zipfile.ZipFile(bundle_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(project_3mf, arcname=os.path.basename(project_3mf))
        z.write(preview_png, arcname=os.path.basename(preview_png))
        z.write(meta_path, arcname=os.path.basename(meta_path))
        for p in project_stls:
            z.write(p, arcname=os.path.basename(p))

    return StampResult(
        project_3mf=project_3mf,
        preview_png=preview_png,
        bundle_zip=bundle_zip,
        output_dir=str(output),
    )


def generate_text_project(
    text: str,
    output_dir: str,
    product_mode: str = "stamp",
    base_diameter: float = 105.0,
    line_width: float = 0.45,
    add_heart: bool = True,
    font_choice: str = "classic",
    base_shape: str = "round",
    layout_mode: str = "separate",
) -> StampResult:
    mask = _render_text_mask(
        text=text,
        canvas_mm=82,
        px_per_mm=DEFAULTS["px_per_mm"],
        font_choice=font_choice,
    )
    name = "text_stamp"
    return _build_from_mask(
        mask=mask,
        output_dir=output_dir,
        name=name,
        product_mode=product_mode,
        base_diameter=base_diameter,
        line_width=line_width,
        add_heart=add_heart,
        font_choice=font_choice,
        base_shape=base_shape,
        layout_mode=layout_mode,
    )


def generate_image_project(
    image_path: str,
    output_dir: str,
    product_mode: str = "stamp",
    base_diameter: float = 105.0,
    line_width: float = 0.45,
    add_heart: bool = False,
    base_shape: str = "round",
    layout_mode: str = "separate",
) -> StampResult:
    mask = _render_image_mask(
        image_path=image_path,
        canvas_mm=82,
        px_per_mm=DEFAULTS["px_per_mm"],
    )
    name = _safe_name(Path(image_path).stem, "image_stamp")
    return _build_from_mask(
        mask=mask,
        output_dir=output_dir,
        name=name,
        product_mode=product_mode,
        base_diameter=base_diameter,
        line_width=line_width,
        add_heart=add_heart,
        font_choice="image",
        base_shape=base_shape,
        layout_mode=layout_mode,
    )
