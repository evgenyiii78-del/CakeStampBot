"""Blender headless mesh generator for CakeStampBot v2.0.0-alpha."""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--job", required=True)
    return p.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def create_base(job):
    h = float(job["base_height"])
    if job["base_shape"] == "rect":
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, h / 2.0))
        obj = bpy.context.object
        obj.name = "Base"
        obj.dimensions = (float(job["rect_w"]), float(job["rect_h"]), h)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    else:
        bpy.ops.mesh.primitive_cylinder_add(vertices=256, radius=float(job["nominal"]) / 2.0, depth=h, location=(0, 0, h / 2.0))
        obj = bpy.context.object
        obj.name = "Base"
    return obj


def seg_normal(a, b):
    dx = float(b[0] - a[0])
    dy = float(b[1] - a[1])
    ln = math.hypot(dx, dy)
    if ln < 1e-12:
        return (0.0, 1.0)
    return (-dy / ln, dx / ln)


def offsets(points, half_width):
    n = len(points)
    normals = [seg_normal(points[i], points[i + 1]) for i in range(n - 1)]
    out = []
    for i in range(n):
        if i == 0:
            nx, ny = normals[0]
            out.append((nx * half_width, ny * half_width))
            continue
        if i == n - 1:
            nx, ny = normals[-1]
            out.append((nx * half_width, ny * half_width))
            continue
        n0 = normals[i - 1]
        n1 = normals[i]
        mx = n0[0] + n1[0]
        my = n0[1] + n1[1]
        ml = math.hypot(mx, my)
        if ml < 1e-9:
            nx, ny = n1
            out.append((nx * half_width, ny * half_width))
            continue
        mx /= ml
        my /= ml
        denom = mx * n1[0] + my * n1[1]
        if abs(denom) < 0.25:
            denom = 0.25 if denom >= 0 else -0.25
        miter = max(-half_width * 2.5, min(half_width * 2.5, half_width / denom))
        out.append((mx * miter, my * miter))
    return out


def create_ribbon(path_points, width, height, index):
    points = [(float(x), float(y)) for x, y in path_points]
    if len(points) < 2:
        return None
    half = float(width) / 2.0
    offs = offsets(points, half)
    verts = []
    for (x, y), (ox, oy) in zip(points, offs):
        verts.extend([(x + ox, y + oy, 0.0), (x - ox, y - oy, 0.0), (x + ox, y + oy, float(height)), (x - ox, y - oy, float(height))])
    faces = []
    for i in range(len(points) - 1):
        a = i * 4
        b = (i + 1) * 4
        faces.extend([(a, b, b + 1, a + 1), (a + 2, a + 3, b + 3, b + 2), (a, a + 2, b + 2, b), (a + 1, b + 1, b + 3, a + 3)])
    faces.append((0, 1, 3, 2))
    e = (len(points) - 1) * 4
    faces.append((e, e + 2, e + 3, e + 1))
    mesh = bpy.data.meshes.new(f"RibbonMesh_{index}")
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(f"Relief_{index}", mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def write_ascii_stl(path, objects, solid_name):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", errors="ignore") as f:
        f.write(f"solid {solid_name}\n")
        for obj in objects:
            mesh = obj.data
            mesh.calc_loop_triangles()
            matrix = obj.matrix_world
            for tri in mesh.loop_triangles:
                vs = [matrix @ mesh.vertices[i].co for i in tri.vertices]
                n = (vs[1] - vs[0]).cross(vs[2] - vs[0])
                if n.length > 1e-12:
                    n.normalize()
                else:
                    n = Vector((0.0, 0.0, 1.0))
                f.write(f"  facet normal {n.x:.9g} {n.y:.9g} {n.z:.9g}\n")
                f.write("    outer loop\n")
                for v in vs:
                    f.write(f"      vertex {v.x:.9g} {v.y:.9g} {v.z:.9g}\n")
                f.write("    endloop\n  endfacet\n")
        f.write(f"endsolid {solid_name}\n")


def main():
    args = parse_args()
    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    clear_scene()
    base = create_base(job)
    relief = []
    for i, path in enumerate(job.get("paths", [])):
        obj = create_ribbon(path, float(job["line_width"]), float(job["relief_height"]), i)
        if obj is not None:
            relief.append(obj)
    if not relief:
        raise RuntimeError("No relief ribbons were generated")
    write_ascii_stl(job["base_stl"], [base], "CakeStampBase")
    write_ascii_stl(job["relief_stl"], relief, "CakeStampRelief")
    print(f"CakeStamp Blender alpha: {len(relief)} relief ribbons generated")


if __name__ == "__main__":
    main()
