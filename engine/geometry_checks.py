
import logging
import trimesh

logger = logging.getLogger("CakeStampEngine.GeometryChecks")


def mesh_summary(mesh: trimesh.Trimesh) -> dict:
    return {
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "is_watertight": bool(mesh.is_watertight),
        "is_winding_consistent": bool(mesh.is_winding_consistent),
        "euler_number": int(mesh.euler_number) if mesh.euler_number is not None else None,
        "bounds": mesh.bounds.tolist() if mesh.bounds is not None else None,
    }


def log_mesh_summary(name: str, mesh: trimesh.Trimesh):
    try:
        logger.info("MESH SUMMARY | %s | %s", name, mesh_summary(mesh))
    except Exception:
        logger.exception("Failed to summarize mesh %s", name)
